import pytest
from pydantic import ValidationError

from stt.config import ENV_ALIASES, Settings, settings_from_env


def test_settings_defaults():
    settings = Settings()
    assert settings.gemini_model == 'gemini-3.5-flash'
    assert settings.gemini_max_output_tokens == 65536
    assert settings.gemini_thinking_budget == 0
    assert settings.gemini_transient_retries == 3
    assert settings.gemini_transient_retry_delay == 60
    assert settings.silence_noise_db == -30.0
    assert settings.silence_min_duration == 0.5
    assert settings.target_chunk_seconds == 720
    assert settings.max_chunk_seconds == 1500
    assert settings.tail_context_segments == 5
    assert settings.max_chunk_continuations == 10
    assert settings.premature_stop_gap_seconds == 60
    assert settings.premature_stop_retries == 2
    assert settings.audio_input_price_per_m == 3.50
    assert settings.output_price_per_m == 9.00
    assert settings.usd_to_twd == 32.0


def test_settings_is_frozen():
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.gemini_model = 'other-model'


def test_settings_forbids_unknown_kwarg():
    with pytest.raises(ValidationError):
        Settings(unknown_field='value')


def test_settings_from_env_reads_os_environ(monkeypatch):
    monkeypatch.setenv('GEMINI_STT_MODEL', 'gemini-env-model')
    settings = settings_from_env(None)
    assert settings.gemini_model == 'gemini-env-model'


def test_settings_from_env_empty_mapping_returns_defaults():
    settings = settings_from_env({})
    assert settings == Settings()


def test_settings_from_env_override_coerces_types():
    settings = settings_from_env({'CHUNKED_TARGET_SECONDS': '300'})
    assert settings.target_chunk_seconds == 300
    assert isinstance(settings.target_chunk_seconds, int)


def test_settings_from_env_empty_string_is_treated_as_unset():
    settings = settings_from_env({'GEMINI_STT_MODEL': ''})
    assert settings.gemini_model == Settings().gemini_model


def test_env_aliases_match_settings_fields():
    field_names = set(Settings.model_fields)
    for field_name in ENV_ALIASES:
        assert field_name in field_names
