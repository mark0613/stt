from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

BASE_DIR = Path(__file__).parent.parent


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    gemini_model: str = 'gemini-3.5-flash'
    gemini_max_output_tokens: int = 65536
    gemini_thinking_budget: int = 0
    gemini_transient_retries: int = 3
    gemini_transient_retry_delay: int = 60

    silence_noise_db: float = -30.0
    silence_min_duration: float = 0.5
    target_chunk_seconds: int = 720
    max_chunk_seconds: int = 1500

    tail_context_segments: int = 5
    max_chunk_continuations: int = 10
    premature_stop_gap_seconds: int = 60
    premature_stop_retries: int = 2

    audio_input_price_per_m: float = 3.50
    output_price_per_m: float = 9.00
    usd_to_twd: float = 32.0


ENV_ALIASES = {
    'gemini_model': 'GEMINI_STT_MODEL',
    'gemini_max_output_tokens': 'GEMINI_MAX_OUTPUT_TOKENS',
    'gemini_thinking_budget': 'GEMINI_THINKING_BUDGET',
    'gemini_transient_retries': 'GEMINI_STT_TRANSIENT_RETRIES',
    'gemini_transient_retry_delay': 'GEMINI_STT_TRANSIENT_RETRY_DELAY_SECONDS',
    'silence_noise_db': 'CHUNKED_SILENCE_NOISE_DB',
    'silence_min_duration': 'CHUNKED_SILENCE_MIN_DURATION',
    'target_chunk_seconds': 'CHUNKED_TARGET_SECONDS',
    'max_chunk_seconds': 'CHUNKED_MAX_SECONDS',
    'tail_context_segments': 'CHUNKED_TAIL_CONTEXT_SEGMENTS',
    'max_chunk_continuations': 'CHUNKED_MAX_CONTINUATIONS',
    'premature_stop_gap_seconds': 'CHUNKED_PREMATURE_STOP_GAP',
    'premature_stop_retries': 'CHUNKED_PREMATURE_STOP_RETRIES',
}


def settings_from_env(env: Mapping[str, str] | None = None) -> Settings:
    # 空字串視同沒設定，否則 .env 裡留空的變數會讓 pydantic 轉型失敗
    env = os.environ if env is None else env
    overrides = {field: env[key] for field, key in ENV_ALIASES.items() if env.get(key)}
    return Settings(**overrides)
