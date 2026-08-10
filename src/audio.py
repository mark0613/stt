from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import src.config as cfg
from src.logging_setup import get_logger

log = get_logger('audio')


@dataclass
class Chunk:
    idx: int
    path: Path
    start_sec: float
    end_sec: float

    @property
    def duration(self) -> float:
        return self.end_sec - self.start_sec


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    # ffmpeg/ffprobe 輸出是 UTF-8，Windows 預設用 cp950 解碼會 UnicodeDecodeError
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')


def split_audio(audio_path: Path, tmpdir: Path) -> list[Chunk]:
    total_duration = audio_duration(audio_path)
    midpoints = silence_midpoints(audio_path)
    cut_points = choose_cut_points(midpoints, total_duration)

    starts = [0.0] + cut_points
    ends = cut_points + [total_duration]

    chunks: list[Chunk] = []
    for idx, (start, end) in enumerate(zip(starts, ends), start=1):
        # 沿用來源副檔名，-c copy 才不會遇到 codec 塞不進容器的問題
        chunk_path = tmpdir / f'chunk_{idx:03d}{audio_path.suffix}'
        result = _run(
            ['ffmpeg', '-y', '-ss', str(start), '-to', str(end),
             '-i', str(audio_path), '-c', 'copy', str(chunk_path)]
        )
        if result.returncode != 0:
            raise RuntimeError(f'ffmpeg chunk {idx} failed: {result.stderr[-500:]}')
        chunks.append(Chunk(idx=idx, path=chunk_path, start_sec=start, end_sec=end))

    return chunks


def audio_duration(audio_path: Path) -> float:
    result = _run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', str(audio_path)]
    )
    return float(result.stdout.strip())


def silence_midpoints(audio_path: Path) -> list[float]:
    result = _run(
        ['ffmpeg', '-i', str(audio_path),
         '-af', f'silencedetect=noise={cfg.SILENCE_NOISE_DB}dB:d={cfg.SILENCE_MIN_DURATION}',
         '-f', 'null', '-']
    )
    starts = [float(m) for m in re.findall(r'silence_start:\s*([\d.]+)', result.stderr)]
    ends = [float(m) for m in re.findall(r'silence_end:\s*([\d.]+)', result.stderr)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def choose_cut_points(midpoints: list[float], total_duration: float) -> list[float]:
    if not midpoints or total_duration <= cfg.TARGET_CHUNK_SECONDS:
        return []

    cut_points: list[float] = []
    cursor = 0.0

    while cursor < total_duration - cfg.TARGET_CHUNK_SECONDS * 0.5:
        target = cursor + cfg.TARGET_CHUNK_SECONDS
        if target >= total_duration:
            break

        candidates = [p for p in midpoints if cursor < p <= cursor + cfg.MAX_CHUNK_SECONDS]
        if candidates:
            best = min(candidates, key=lambda p: abs(p - target))
            cut_points.append(best)
            log.info(f'cut at silence={best:.1f}s (target={target:.1f}s, cursor={cursor:.1f}s)')
            cursor = best
        else:
            hard_cut = cursor + cfg.TARGET_CHUNK_SECONDS
            log.info(f'warning: no silence within {cfg.MAX_CHUNK_SECONDS}s of cursor={cursor:.1f}s, hard-cutting at {hard_cut:.1f}s')
            cut_points.append(hard_cut)
            cursor = hard_cut

    return cut_points
