from __future__ import annotations

import json
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

import src.config as cfg
from src.audio import Chunk, split_audio
from src.gemini import build_prompt, call_gemini, upload_audio
from src.models import TranscriptResult, TranscriptSegment
from src.utils import (
    finish_reason_name,
    merge_segments,
    parse_segments,
    response_text,
    timestamp_seconds,
    utc_now,
)


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    _calls: int = field(default=0, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def add(self, usage_metadata: object | None) -> None:
        if usage_metadata is None:
            return
        with self._lock:
            self.prompt_tokens += getattr(usage_metadata, 'prompt_token_count', 0) or 0
            self.output_tokens += getattr(usage_metadata, 'candidates_token_count', 0) or 0
            self.thinking_tokens += getattr(usage_metadata, 'thoughts_token_count', 0) or 0
            self._calls += 1

    def summary(self) -> dict:
        total_output = self.output_tokens + self.thinking_tokens
        cost_usd = (
            self.prompt_tokens / 1_000_000 * cfg.AUDIO_INPUT_PRICE_PER_M
            + total_output / 1_000_000 * cfg.OUTPUT_PRICE_PER_M
        )
        return {
            'calls': self._calls,
            'prompt_tokens': self.prompt_tokens,
            'output_tokens': self.output_tokens,
            'thinking_tokens': self.thinking_tokens,
            'estimated_usd': round(cost_usd, 4),
            'estimated_twd': round(cost_usd * cfg.USD_TO_TWD, 2),
        }

    def log(self) -> None:
        s = self.summary()
        _log(
            f'[token usage] calls={s["calls"]} '
            f'prompt={s["prompt_tokens"]} output={s["output_tokens"]} '
            f'thinking={s["thinking_tokens"]} '
            f'~${s["estimated_usd"]} USD (~NT${s["estimated_twd"]})'
        )


def transcribe(
    audio_path: str | Path,
    output_path: str | Path | None = None,
) -> TranscriptResult:
    audio_path = Path(audio_path)
    usage = TokenUsage()

    _log(f'start audio={audio_path}')

    with tempfile.TemporaryDirectory(prefix='stt_chunks_') as tmpdir:
        chunks = split_audio(audio_path, Path(tmpdir), log=_log)
        _log(f'split into {len(chunks)} chunks')

        # Upload all chunks in parallel, then transcribe in order
        # (transcription is sequential to preserve tail_context continuity)
        chunk_uris = _upload_chunks_parallel(chunks)

        all_segments: list[TranscriptSegment] = []
        for chunk in chunks:
            _log(
                f'chunk {chunk.idx}/{len(chunks)} '
                f'start={chunk.start_sec:.1f}s end={chunk.end_sec:.1f}s duration={chunk.duration:.1f}s'
            )
            tail_context = (
                _to_local_ts(all_segments[-cfg.TAIL_CONTEXT_SEGMENTS:], chunk.start_sec)
                if all_segments else []
            )
            chunk_segments = _transcribe_chunk(chunk, chunk_uris[chunk.idx], tail_context, usage)
            _log(f'chunk {chunk.idx} got {len(chunk_segments)} segments before merge')

            offset_segments = _offset_segments(chunk_segments, chunk.start_sec)
            all_segments, added = merge_segments(all_segments, offset_segments)
            _log(f'chunk {chunk.idx} added {added} segments total={len(all_segments)}')

    usage.log()

    result = TranscriptResult(segments=all_segments)
    if output_path:
        _write_output(Path(output_path), result, usage)

    return result


def _upload_chunks_parallel(chunks: list[Chunk]) -> dict[int, str]:
    """Upload all chunks concurrently. Returns {chunk.idx: uri}."""
    uris: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        futures = {
            executor.submit(_upload_one, chunk): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            chunk = futures[future]
            uris[chunk.idx] = future.result()
    return uris


def _upload_one(chunk: Chunk) -> str:
    _log(f'chunk {chunk.idx} upload start path={chunk.path}')
    uri = upload_audio(str(chunk.path))
    _log(f'chunk {chunk.idx} upload complete uri={uri}')
    return uri


def _transcribe_chunk(
    chunk: Chunk,
    audio_uri: str,
    tail_context: list[TranscriptSegment],
    usage: TokenUsage,
) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []

    for iteration in range(1, cfg.MAX_CHUNK_CONTINUATIONS + 1):
        cursor_ctx = segments[-8:] if segments else tail_context
        prompt = build_prompt(
            tail_context=cursor_ctx,
            cursor=_last_ts(segments),
            is_continuation=bool(segments),
        )
        response = call_gemini(audio_uri, prompt)
        usage.add(getattr(response, 'usage_metadata', None))

        finish = finish_reason_name(response)
        new_segments, _ = parse_segments(response_text(response))
        segments, added = merge_segments(segments, new_segments)
        _log(
            f'chunk {chunk.idx} iter={iteration} finish={finish} '
            f'returned={len(new_segments)} added={added} total={len(segments)}'
        )

        if finish == 'STOP':
            break
        if finish == 'MAX_TOKENS' and added > 0:
            _log(f'chunk {chunk.idx} MAX_TOKENS with progress, continuing')
            continue
        if finish == 'MAX_TOKENS' and added == 0:
            _log(f'warning: chunk {chunk.idx} MAX_TOKENS no new segments, stopping')
            break
        _log(f'warning: chunk {chunk.idx} unexpected finish={finish}, stopping')
        break
    else:
        _log(f'warning: chunk {chunk.idx} reached MAX_CHUNK_CONTINUATIONS={cfg.MAX_CHUNK_CONTINUATIONS}')

    # Premature-stop retry
    for retry in range(cfg.PREMATURE_STOP_RETRIES):
        last_sec = timestamp_seconds(_last_ts(segments))
        if last_sec is None or last_sec >= chunk.duration - cfg.PREMATURE_STOP_GAP_SECONDS:
            break
        gap = chunk.duration - last_sec
        _log(f'chunk {chunk.idx} premature stop retry={retry+1} last_ts={last_sec:.1f}s gap={gap:.1f}s')

        for iteration in range(1, cfg.MAX_CHUNK_CONTINUATIONS + 1):
            prompt = build_prompt(
                tail_context=segments[-8:],
                cursor=_last_ts(segments),
                is_continuation=True,
            )
            response = call_gemini(audio_uri, prompt)
            usage.add(getattr(response, 'usage_metadata', None))

            finish = finish_reason_name(response)
            new_segments, _ = parse_segments(response_text(response))
            segments, added = merge_segments(segments, new_segments)
            _log(
                f'chunk {chunk.idx} premature-retry iter={iteration} finish={finish} '
                f'returned={len(new_segments)} added={added} total={len(segments)}'
            )
            if finish == 'STOP' or added == 0:
                break
            if finish == 'MAX_TOKENS' and added > 0:
                continue
            break

    return segments


def _offset_segments(segments: list[TranscriptSegment], start_sec: float) -> list[TranscriptSegment]:
    result = []
    for seg in segments:
        local_sec = timestamp_seconds(seg.timestamp)
        if local_sec is None:
            result.append(seg)
            continue
        result.append(seg.model_copy(update={'timestamp': _fmt_ts(local_sec + start_sec)}))
    return result


def _to_local_ts(segments: list[TranscriptSegment], chunk_start_sec: float) -> list[TranscriptSegment]:
    result = []
    for seg in segments:
        global_sec = timestamp_seconds(seg.timestamp)
        if global_sec is None:
            result.append(seg)
            continue
        result.append(seg.model_copy(update={'timestamp': _fmt_ts(max(0.0, global_sec - chunk_start_sec))}))
    return result


def _fmt_ts(seconds: float) -> str:
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'


def _last_ts(segments: list[TranscriptSegment]) -> str | None:
    return segments[-1].timestamp if segments else None


def _write_output(output_path: Path, result: TranscriptResult, usage: TokenUsage) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(
            {**result.model_dump(mode='json'), 'token_usage': usage.summary()},
            f, ensure_ascii=False, indent=2,
        )
    _log(f'saved output={output_path}')


def _log(message: str) -> None:
    print(f'[{utc_now()}] [stt] {message}', flush=True)
