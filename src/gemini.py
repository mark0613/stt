from __future__ import annotations

import json

from google import genai
from google.genai import types

import src.config as cfg
from src.logging_setup import get_logger
from src.models import TranscriptResult, TranscriptSegment
from src.utils import is_transient_error, sleep_before_retry

client = genai.Client()
log = get_logger('gemini')

BASE_PROMPT = """
Process the audio file and generate a detailed transcription.

Requirements:
1. Identify distinct speakers (e.g., Speaker 1, Speaker 2, or names if context allows).
2. Provide accurate timestamps for each segment (Format: MM:SS).
3. Detect the primary language code of each segment (e.g., zh, en, ja).
4. Do not be lazy. Transcribe verbatim word-for-word, do not summarize.
5. Return only JSON matching this shape: {"segments": [...]}.
6. If a speaker repeats a short filler such as "那", "呃", or "嗯", transcribe the
   natural utterance briefly and then continue; never repeat the same filler endlessly.
"""


def build_prompt(
    tail_context: list[TranscriptSegment],
    cursor: str | None = None,
    is_continuation: bool = False,
    speaker_count: int | None = None,
    extra_instructions: str | None = None,
) -> str:
    base_prompt = _augment_base_prompt(speaker_count, extra_instructions)

    if not tail_context and not is_continuation:
        return base_prompt

    context_json = json.dumps(
        [seg.model_dump(mode='json') for seg in tail_context],
        ensure_ascii=False,
        indent=2,
    )

    if is_continuation and cursor:
        return f"""
{base_prompt}

Continuation instructions:
- This is a continuation of the SAME audio chunk.
- {len(tail_context)} segments have already been transcribed up to timestamp {cursor}.
- Continue transcribing from timestamp {cursor} — do NOT restart from the beginning.
- Return only NEW segments after {cursor}. A small overlap around {cursor} is acceptable.
- Keep speaker labels consistent with the prior context below.

Prior context (last {len(tail_context)} segments):
{context_json}
"""

    return f"""
{base_prompt}

Continuation instructions:
- This audio chunk continues from a previous section.
- Keep speaker labels consistent with the prior context shown below.
- Do NOT restart speaker numbering; continue the same speaker labels.

Prior context (last {len(tail_context)} segments of previous chunk):
{context_json}
"""


def _augment_base_prompt(speaker_count: int | None, extra_instructions: str | None) -> str:
    extras: list[str] = []
    if speaker_count and speaker_count > 0:
        extras.append(
            f'7. There are {speaker_count} distinct speakers in this audio. '
            f'Label them as Speaker 1 through Speaker {speaker_count}.'
        )
    if extra_instructions:
        extras.append(f'Additional context from the user:\n{extra_instructions}')

    if not extras:
        return BASE_PROMPT
    return BASE_PROMPT + '\n' + '\n'.join(extras) + '\n'


def call_gemini(audio_file_uri: str, prompt: str) -> object:
    for attempt in range(cfg.GEMINI_TRANSIENT_RETRIES + 1):
        try:
            return client.models.generate_content(
                model=cfg.GEMINI_MODEL,
                contents=[
                    types.Content(
                        parts=[
                            types.Part(file_data=types.FileData(file_uri=audio_file_uri)),
                            types.Part(text=prompt),
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=cfg.GEMINI_MAX_OUTPUT_TOKENS,
                    response_mime_type='application/json',
                    response_schema=TranscriptResult,
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=False,
                        thinking_budget=cfg.GEMINI_THINKING_BUDGET,
                    ),
                    temperature=0,
                ),
            )
        except Exception as error:
            will_retry = attempt < cfg.GEMINI_TRANSIENT_RETRIES and is_transient_error(error)
            log.info(f'error attempt={attempt} type={type(error).__name__} will_retry={will_retry}')
            if not will_retry:
                raise
            sleep_before_retry(attempt + 1, cfg.GEMINI_TRANSIENT_RETRY_DELAY)
    raise RuntimeError('unreachable')


def upload_audio(path: str) -> str:
    audio_file = client.files.upload(file=path)
    return audio_file.uri
