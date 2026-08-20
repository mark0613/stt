from __future__ import annotations

import pytest

from stt.config import Settings
from stt.gemini import BASE_PROMPT, _augment_base_prompt, build_prompt, call_gemini, upload_audio
from tests.conftest import FakeResponse


def test_build_prompt_no_context_no_continuation_returns_base_prompt():
    result = build_prompt(tail_context=[], cursor=None, is_continuation=False)

    assert result == BASE_PROMPT


def test_build_prompt_continuation_with_cursor(segment):
    tail_context = [segment(), segment()]

    result = build_prompt(tail_context=tail_context, cursor='05:00', is_continuation=True)

    assert '05:00' in result
    assert '2 segments have already been transcribed up to timestamp 05:00' in result
    assert 'Continue transcribing from timestamp 05:00' in result


def test_build_prompt_continuation_without_cursor_falls_through():
    result = build_prompt(tail_context=[], cursor=None, is_continuation=True)

    assert 'This audio chunk continues from a previous section.' in result
    assert 'Do NOT restart speaker numbering' in result


def test_build_prompt_tail_context_without_continuation(segment):
    tail_context = [segment(content='hello there')]

    result = build_prompt(tail_context=tail_context, cursor=None, is_continuation=False)

    assert 'This audio chunk continues from a previous section.' in result
    assert 'hello there' in result


def test_augment_base_prompt_speaker_count_none():
    result = _augment_base_prompt(None, None)

    assert result is BASE_PROMPT
    assert '7.' not in result


def test_augment_base_prompt_speaker_count_zero():
    result = _augment_base_prompt(0, None)

    assert result is BASE_PROMPT
    assert '7.' not in result


def test_augment_base_prompt_speaker_count_three():
    result = _augment_base_prompt(3, None)

    assert 'Speaker 1 through Speaker 3' in result


def test_augment_base_prompt_extra_instructions():
    result = _augment_base_prompt(None, 'please be careful with names')

    assert 'Additional context from the user' in result
    assert 'please be careful with names' in result


def test_augment_base_prompt_both():
    result = _augment_base_prompt(2, 'watch for jargon')

    assert 'Speaker 1 through Speaker 2' in result
    assert 'Additional context from the user' in result
    assert 'watch for jargon' in result


def test_augment_base_prompt_neither_is_base_prompt():
    result = _augment_base_prompt(None, None)

    assert result is BASE_PROMPT


def test_call_gemini_succeeds_first_call(fake_client, settings: Settings):
    response = FakeResponse(text='{"segments": []}')
    client = fake_client(responses=[response])

    result = call_gemini(client, 'files/fake/1', 'transcribe this', settings)

    assert result is response
    calls = client.models.calls
    assert len(calls) == 1
    call = calls[0]
    assert call['model'] == settings.gemini_model
    parts = call['contents'][0].parts
    assert parts[0].file_data.file_uri == 'files/fake/1'
    assert parts[1].text == 'transcribe this'
    config = call['config']
    assert config.max_output_tokens == settings.gemini_max_output_tokens
    assert config.response_mime_type == 'application/json'
    assert config.temperature == 0


def test_call_gemini_retries_on_transient_error_then_succeeds(fake_client, settings, no_sleep):
    response = FakeResponse(text='{"segments": []}')
    client = fake_client(responses=[Exception('503 Service Unavailable'), response])

    result = call_gemini(client, 'files/fake/1', 'prompt', settings)

    assert result is response
    assert len(client.models.calls) == 2
    assert no_sleep == [settings.gemini_transient_retry_delay * 1]


def test_call_gemini_non_transient_error_propagates_without_retry(fake_client, settings):
    client = fake_client(responses=[ValueError('400 invalid request')])

    with pytest.raises(ValueError, match='400 invalid request'):
        call_gemini(client, 'files/fake/1', 'prompt', settings)

    assert len(client.models.calls) == 1


def test_call_gemini_all_attempts_transient_raises_final_error(fake_client, settings, no_sleep):
    errors = [
        Exception('503 Service Unavailable') for _ in range(settings.gemini_transient_retries + 1)
    ]
    client = fake_client(responses=list(errors))

    with pytest.raises(Exception, match='503 Service Unavailable'):
        call_gemini(client, 'files/fake/1', 'prompt', settings)

    assert len(client.models.calls) == settings.gemini_transient_retries + 1
    assert len(no_sleep) == settings.gemini_transient_retries


def test_upload_audio_returns_uri_and_passes_path(fake_client):
    client = fake_client(uri_prefix='files/fake')

    result = upload_audio(client, 'path/to/file.wav')

    assert result == 'files/fake/1'
    assert client.files.uploaded == ['path/to/file.wav']
