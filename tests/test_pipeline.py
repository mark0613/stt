from __future__ import annotations

import json
from pathlib import Path

import pytest

from stt.audio import Chunk
from stt.config import Settings
from stt.models import TranscriptResult
from stt.pipeline import (
    ProgressHooks,
    TokenUsage,
    _fmt_ts,
    _last_ts,
    _offset_segments,
    _to_local_ts,
    _transcribe_chunk,
    _upload_chunks_parallel,
    _upload_one,
    _write_output,
    transcribe,
)
from tests.conftest import FakeClient, FakeFinishReason, FakeResponse, FakeUsage


@pytest.fixture
def settings2(settings: Settings) -> Settings:
    """premature-stop retry 關閉，讓主迴圈測試不受重試邏輯影響。"""
    return settings.model_copy(update={'premature_stop_retries': 0})


def make_chunk(idx: int = 1, start: float = 0.0, end: float = 5.0) -> Chunk:
    return Chunk(idx=idx, path=Path(f'chunk_{idx}.wav'), start_sec=start, end_sec=end)


# --- ProgressHooks ---


def test_progress_hooks_all_none_are_noops():
    hooks = ProgressHooks()
    hooks.chunks_ready(3)
    hooks.upload_done()
    hooks.chunk_done()


def test_progress_hooks_all_set_invoke_callbacks():
    calls: dict = {'ready': None, 'upload': 0, 'chunk': 0}

    def on_ready(n: int) -> None:
        calls['ready'] = n

    def on_upload() -> None:
        calls['upload'] += 1

    def on_chunk() -> None:
        calls['chunk'] += 1

    hooks = ProgressHooks(
        on_chunks_ready=on_ready, on_upload_done=on_upload, on_chunk_done=on_chunk
    )
    hooks.chunks_ready(3)
    hooks.upload_done()
    hooks.chunk_done()

    assert calls == {'ready': 3, 'upload': 1, 'chunk': 1}


# --- TokenUsage ---


def test_token_usage_add_none_is_noop():
    usage = TokenUsage()
    usage.add(None)
    assert usage.prompt_tokens == 0
    assert usage.output_tokens == 0
    assert usage.thinking_tokens == 0
    assert usage._calls == 0


def test_token_usage_add_accumulates():
    usage = TokenUsage()
    usage.add(FakeUsage(prompt_token_count=100, candidates_token_count=50, thoughts_token_count=10))
    usage.add(FakeUsage(prompt_token_count=20, candidates_token_count=5, thoughts_token_count=1))

    assert usage.prompt_tokens == 120
    assert usage.output_tokens == 55
    assert usage.thinking_tokens == 11
    assert usage._calls == 2


def test_token_usage_add_missing_attributes_treated_as_zero():
    class Empty:
        pass

    usage = TokenUsage()
    usage.add(Empty())

    assert usage.prompt_tokens == 0
    assert usage.output_tokens == 0
    assert usage.thinking_tokens == 0
    assert usage._calls == 1


def test_token_usage_add_none_attributes_treated_as_zero():
    usage = TokenUsage()
    usage.add(
        FakeUsage(prompt_token_count=None, candidates_token_count=None, thoughts_token_count=None)
    )

    assert usage.prompt_tokens == 0
    assert usage.output_tokens == 0
    assert usage.thinking_tokens == 0
    assert usage._calls == 1


def test_token_usage_summary_computes_expected_cost(settings: Settings):
    usage = TokenUsage()
    usage.add(
        FakeUsage(
            prompt_token_count=1_000_000,
            candidates_token_count=500_000,
            thoughts_token_count=100_000,
        )
    )

    result = usage.summary(settings)

    expected_cost_usd = (
        1_000_000 / 1_000_000 * settings.audio_input_price_per_m
        + 600_000 / 1_000_000 * settings.output_price_per_m
    )
    assert result == {
        'calls': 1,
        'prompt_tokens': 1_000_000,
        'output_tokens': 500_000,
        'thinking_tokens': 100_000,
        'estimated_usd': round(expected_cost_usd, 4),
        'estimated_twd': round(expected_cost_usd * settings.usd_to_twd, 2),
    }


def test_token_usage_log_emits_record(caplog, settings: Settings):
    usage = TokenUsage()
    usage.add(FakeUsage(prompt_token_count=10, candidates_token_count=5, thoughts_token_count=1))

    with caplog.at_level('INFO', logger='stt.stt'):
        usage.log(settings)

    assert 'token usage' in caplog.text


# --- small helpers ---


def test_fmt_ts_zero():
    assert _fmt_ts(0) == '00:00'


def test_fmt_ts_minutes_seconds():
    assert _fmt_ts(90) == '01:30'


def test_fmt_ts_hours():
    assert _fmt_ts(3661) == '1:01:01'


def test_last_ts_empty():
    assert _last_ts([]) is None


def test_last_ts_non_empty(segment):
    segments = [segment(timestamp='00:01'), segment(timestamp='00:02')]
    assert _last_ts(segments) == '00:02'


def test_offset_segments_parseable_timestamp(segment):
    seg = segment(timestamp='00:01')
    result = _offset_segments([seg], start_sec=10.0)
    assert result[0].timestamp == '00:11'


def test_offset_segments_unparseable_timestamp_passthrough(segment):
    seg = segment(timestamp='n/a')
    result = _offset_segments([seg], start_sec=10.0)
    assert result[0] is seg
    assert result[0].timestamp == 'n/a'


def test_to_local_ts_parseable_subtracts_offset(segment):
    seg = segment(timestamp='00:20')
    result = _to_local_ts([seg], chunk_start_sec=5.0)
    assert result[0].timestamp == '00:15'


def test_to_local_ts_clamped_at_zero(segment):
    seg = segment(timestamp='00:05')
    result = _to_local_ts([seg], chunk_start_sec=100.0)
    assert result[0].timestamp == '00:00'


def test_to_local_ts_unparseable_timestamp_passthrough(segment):
    seg = segment(timestamp='n/a')
    result = _to_local_ts([seg], chunk_start_sec=5.0)
    assert result[0] is seg
    assert result[0].timestamp == 'n/a'


def test_write_output_creates_nested_dirs_and_content(tmp_path: Path, segment):
    output_path = tmp_path / 'a' / 'b' / 'out.json'
    result = TranscriptResult(segments=[segment(timestamp='00:05', content='hi')])
    usage = TokenUsage()
    usage.add(FakeUsage(prompt_token_count=10, candidates_token_count=5, thoughts_token_count=1))

    _write_output(output_path, result, usage, Settings())

    assert output_path.exists()
    data = json.loads(output_path.read_text(encoding='utf-8'))
    assert 'segments' in data
    assert len(data['segments']) == 1
    assert 'token_usage' in data
    assert data['token_usage']['calls'] == 1


# --- _upload_chunks_parallel / _upload_one ---


def test_upload_chunks_parallel_maps_uris_and_calls_hooks(fake_client):
    client = fake_client()
    chunks = [make_chunk(idx=i, start=0.0, end=1.0) for i in (1, 2, 3)]
    upload_calls: list[int] = []
    hooks = ProgressHooks(on_upload_done=lambda: upload_calls.append(1))

    uris = _upload_chunks_parallel(client, chunks, hooks)

    assert set(uris.keys()) == {1, 2, 3}
    assert set(uris.values()) == {f'files/fake/{n}' for n in (1, 2, 3)}
    assert len(upload_calls) == 3


def test_upload_one_returns_uri(fake_client):
    client = fake_client()
    chunk = make_chunk(idx=1)

    uri = _upload_one(client, chunk)

    assert uri == 'files/fake/1'
    assert client.files.uploaded == [str(chunk.path)]


# --- _transcribe_chunk: main loop ---


def test_transcribe_chunk_stop_immediately(fake_client, segment, segments_json, settings2):
    resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    client = fake_client([resp])
    chunk = make_chunk()

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings2)

    assert [s.timestamp for s in result] == ['00:01']
    assert len(client.models.calls) == 1


def test_transcribe_chunk_max_tokens_then_stop(fake_client, segment, segments_json, settings2):
    resp1 = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.MAX_TOKENS
    )
    resp2 = FakeResponse(
        text=segments_json([segment(timestamp='00:02')]), finish_reason=FakeFinishReason.STOP
    )
    client = fake_client([resp1, resp2])
    chunk = make_chunk()

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings2)

    assert [s.timestamp for s in result] == ['00:01', '00:02']
    assert len(client.models.calls) == 2


def test_transcribe_chunk_max_tokens_no_new_segments_stops(fake_client, settings2):
    resp = FakeResponse(text='{"segments": []}', finish_reason=FakeFinishReason.MAX_TOKENS)
    client = fake_client([resp])
    chunk = make_chunk()

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings2)

    assert result == []
    assert len(client.models.calls) == 1


def test_transcribe_chunk_unexpected_finish_stops(fake_client, segment, segments_json, settings2):
    resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.SAFETY
    )
    client = fake_client([resp])
    chunk = make_chunk()

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings2)

    assert [s.timestamp for s in result] == ['00:01']
    assert len(client.models.calls) == 1


def test_transcribe_chunk_exhausts_max_continuations(
    fake_client, segment, segments_json, settings2
):
    responses = [
        FakeResponse(
            text=segments_json([segment(timestamp=ts)]), finish_reason=FakeFinishReason.MAX_TOKENS
        )
        for ts in ('00:01', '00:02', '00:03')
    ]
    client = fake_client(responses)
    chunk = make_chunk()

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings2)

    assert [s.timestamp for s in result] == ['00:01', '00:02', '00:03']
    assert len(client.models.calls) == settings2.max_chunk_continuations


# --- _transcribe_chunk: premature-stop retry ---


def test_premature_retry_no_segments_breaks_immediately(fake_client, settings: Settings):
    resp = FakeResponse(text='{"segments": []}', finish_reason=FakeFinishReason.STOP)
    client = fake_client([resp])
    chunk = make_chunk(start=0.0, end=1000.0)

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings)

    assert result == []
    assert len(client.models.calls) == 1


def test_premature_retry_within_gap_breaks(fake_client, segment, segments_json, settings: Settings):
    resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    client = fake_client([resp])
    chunk = make_chunk(start=0.0, end=5.0)

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings)

    assert [s.timestamp for s in result] == ['00:01']
    assert len(client.models.calls) == 1


def test_premature_retry_far_from_duration_inner_stop_breaks(
    fake_client, segment, segments_json, settings: Settings
):
    main_resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    inner_resp = FakeResponse(
        text=segments_json([segment(timestamp='00:02')]), finish_reason=FakeFinishReason.STOP
    )
    client = fake_client([main_resp, inner_resp])
    chunk = make_chunk(start=0.0, end=1000.0)

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings)

    assert [s.timestamp for s in result] == ['00:01', '00:02']
    assert len(client.models.calls) == 2


def test_premature_retry_inner_added_zero_breaks(
    fake_client, segment, segments_json, settings: Settings
):
    main_resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    inner_resp = FakeResponse(text='{"segments": []}', finish_reason=FakeFinishReason.MAX_TOKENS)
    client = fake_client([main_resp, inner_resp])
    chunk = make_chunk(start=0.0, end=1000.0)

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings)

    assert [s.timestamp for s in result] == ['00:01']
    assert len(client.models.calls) == 2


def test_premature_retry_inner_continues_then_terminates(
    fake_client, segment, segments_json, settings: Settings
):
    main_resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    inner_resp1 = FakeResponse(
        text=segments_json([segment(timestamp='00:02')]), finish_reason=FakeFinishReason.MAX_TOKENS
    )
    inner_resp2 = FakeResponse(
        text=segments_json([segment(timestamp='00:03')]), finish_reason=FakeFinishReason.STOP
    )
    client = fake_client([main_resp, inner_resp1, inner_resp2])
    chunk = make_chunk(start=0.0, end=1000.0)

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings)

    assert [s.timestamp for s in result] == ['00:01', '00:02', '00:03']
    assert len(client.models.calls) == 3


def test_premature_retry_inner_unexpected_finish_breaks(
    fake_client, segment, segments_json, settings: Settings
):
    main_resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    inner_resp = FakeResponse(
        text=segments_json([segment(timestamp='00:02')]), finish_reason=FakeFinishReason.SAFETY
    )
    client = fake_client([main_resp, inner_resp])
    chunk = make_chunk(start=0.0, end=1000.0)

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings)

    assert [s.timestamp for s in result] == ['00:01', '00:02']
    assert len(client.models.calls) == 2


def test_premature_retry_inner_loop_exhausts_max_continuations(
    fake_client, segment, segments_json, settings: Settings
):
    main_resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    inner_responses = [
        FakeResponse(
            text=segments_json([segment(timestamp=ts)]), finish_reason=FakeFinishReason.MAX_TOKENS
        )
        for ts in ('00:02', '00:03', '00:04')
    ]
    client = fake_client([main_resp, *inner_responses])
    chunk = make_chunk(start=0.0, end=1000.0)

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings)

    assert [s.timestamp for s in result] == ['00:01', '00:02', '00:03', '00:04']
    assert len(client.models.calls) == 1 + settings.max_chunk_continuations


def test_premature_retry_disabled_never_runs(fake_client, segment, segments_json, settings2):
    resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    client = fake_client([resp])
    chunk = make_chunk(start=0.0, end=1000.0)

    result = _transcribe_chunk(client, chunk, 'uri', [], TokenUsage(), settings2)

    assert [s.timestamp for s in result] == ['00:01']
    assert len(client.models.calls) == 1


# --- transcribe (integration) ---


def test_transcribe_single_chunk_no_output_path(
    monkeypatch, fake_client, segment, segments_json, settings2
):
    chunk = make_chunk(idx=1, start=0.0, end=5.0)
    monkeypatch.setattr('stt.pipeline.split_audio', lambda audio_path, tmpdir, settings: [chunk])
    resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    client = fake_client([resp])

    result = transcribe('audio.wav', client=client, settings=settings2)

    assert [s.timestamp for s in result.segments] == ['00:01']
    assert result.segments[0].content == 'hello'


def test_transcribe_two_chunks_writes_output_and_includes_prior_context(
    monkeypatch, fake_client, segment, segments_json, settings2, tmp_path
):
    chunk1 = make_chunk(idx=1, start=0.0, end=100.0)
    chunk2 = make_chunk(idx=2, start=100.0, end=200.0)
    monkeypatch.setattr(
        'stt.pipeline.split_audio', lambda audio_path, tmpdir, settings: [chunk1, chunk2]
    )

    resp1 = FakeResponse(
        text=segments_json([segment(timestamp='00:01', content='first')]),
        finish_reason=FakeFinishReason.STOP,
        usage_metadata=FakeUsage(
            prompt_token_count=10, candidates_token_count=5, thoughts_token_count=1
        ),
    )
    resp2 = FakeResponse(
        text=segments_json([segment(timestamp='00:02', content='second')]),
        finish_reason=FakeFinishReason.STOP,
        usage_metadata=FakeUsage(
            prompt_token_count=20, candidates_token_count=8, thoughts_token_count=2
        ),
    )
    client = fake_client([resp1, resp2])

    output_path = tmp_path / 'out.json'
    result = transcribe('audio.wav', output_path=output_path, client=client, settings=settings2)

    assert [s.timestamp for s in result.segments] == ['00:01', '01:42']
    assert output_path.exists()

    saved = json.loads(output_path.read_text(encoding='utf-8'))
    assert len(saved['segments']) == 2
    assert saved['token_usage']['calls'] == 2

    second_prompt = client.models.calls[1]['contents'][0].parts[1].text
    assert 'Prior context' in second_prompt
    assert 'first' in second_prompt


def test_transcribe_default_client_uses_genai_client(
    monkeypatch, segment, segments_json, settings2
):
    chunk = make_chunk(idx=1, start=0.0, end=5.0)
    monkeypatch.setattr('stt.pipeline.split_audio', lambda audio_path, tmpdir, settings: [chunk])
    resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    created: dict = {}

    def factory() -> FakeClient:
        client = FakeClient([resp])
        created['client'] = client
        return client

    monkeypatch.setattr('stt.pipeline.genai.Client', factory)

    result = transcribe('audio.wav', settings=settings2)

    assert created['client'].files.uploaded == [str(chunk.path)]
    assert len(created['client'].models.calls) == 1
    assert len(result.segments) == 1


def test_transcribe_default_settings(monkeypatch, fake_client, segment, segments_json):
    chunk = make_chunk(idx=1, start=0.0, end=5.0)
    monkeypatch.setattr('stt.pipeline.split_audio', lambda audio_path, tmpdir, settings: [chunk])
    resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    client = fake_client([resp])

    result = transcribe('audio.wav', client=client)

    assert len(result.segments) == 1
    assert len(client.models.calls) == 1


def test_transcribe_hooks_none_uses_default(
    monkeypatch, fake_client, segment, segments_json, settings2
):
    chunk = make_chunk(idx=1, start=0.0, end=5.0)
    monkeypatch.setattr('stt.pipeline.split_audio', lambda audio_path, tmpdir, settings: [chunk])
    resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    client = fake_client([resp])

    result = transcribe('audio.wav', client=client, settings=settings2, hooks=None)

    assert len(result.segments) == 1


def test_transcribe_audio_path_as_plain_str(
    monkeypatch, fake_client, segment, segments_json, settings2
):
    chunk = make_chunk(idx=1, start=0.0, end=5.0)
    seen_paths: list = []

    def fake_split_audio(audio_path, tmpdir, settings):
        seen_paths.append(audio_path)
        return [chunk]

    monkeypatch.setattr('stt.pipeline.split_audio', fake_split_audio)
    resp = FakeResponse(
        text=segments_json([segment(timestamp='00:01')]), finish_reason=FakeFinishReason.STOP
    )
    client = fake_client([resp])

    transcribe('some/audio.wav', client=client, settings=settings2)

    assert seen_paths == [Path('some/audio.wav')]
