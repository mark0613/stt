from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console
from rich.progress import Progress as RichProgress

from stt.cli import _run_with_progress, main
from stt.config import Settings


def _clean(text: str) -> str:
    """rich 在窄寬度下會把長字串換行折斷，比對前先去除換行。"""
    return text.replace('\n', '')


def _install_common(monkeypatch, tmp_path: Path, log_path: Path | None = None) -> Path:
    """安裝 load_dotenv/genai.Client/setup_logging 的安全 no-op，回傳 log_path。"""
    monkeypatch.setattr('stt.cli.load_dotenv', lambda *args, **kwargs: None)
    monkeypatch.setattr('stt.cli.genai.Client', lambda **kwargs: object())
    log_path = log_path if log_path is not None else tmp_path / 'log.txt'
    monkeypatch.setattr('stt.cli.setup_logging', lambda *args, **kwargs: log_path)
    return log_path


def test_main_missing_api_key_exits(monkeypatch, capsys):
    monkeypatch.setattr('stt.cli.load_dotenv', lambda *args, **kwargs: None)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    monkeypatch.setattr('sys.argv', ['stt', 'audio.wav'])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert '缺少 GOOGLE_API_KEY' in _clean(captured.out)


def test_main_with_explicit_output_dir(monkeypatch, tmp_path: Path):
    _install_common(monkeypatch, tmp_path)
    monkeypatch.setenv('GOOGLE_API_KEY', 'fake-key')

    recorded: dict = {}

    def fake_transcribe(audio_path, **kwargs):
        recorded['audio_path'] = audio_path
        recorded['kwargs'] = kwargs

    monkeypatch.setattr('stt.cli.transcribe', fake_transcribe)

    audio_file = tmp_path / 'audio.wav'
    output_dir = tmp_path / 'out'
    monkeypatch.setattr('sys.argv', ['stt', str(audio_file), str(output_dir)])

    main()

    assert output_dir.exists()
    assert recorded['kwargs']['output_path'] == output_dir / 'audio.json'


def test_main_without_output_dir_defaults_to_audio_parent(monkeypatch, tmp_path: Path):
    _install_common(monkeypatch, tmp_path)
    monkeypatch.setenv('GOOGLE_API_KEY', 'fake-key')

    recorded: dict = {}

    def fake_transcribe(audio_path, **kwargs):
        recorded['kwargs'] = kwargs

    monkeypatch.setattr('stt.cli.transcribe', fake_transcribe)

    audio_file = tmp_path / 'audio.wav'
    monkeypatch.setattr('sys.argv', ['stt', str(audio_file)])

    main()

    assert recorded['kwargs']['output_path'] == audio_file.parent / 'audio.json'


def test_main_forwards_num_speakers_and_prompt(monkeypatch, tmp_path: Path):
    _install_common(monkeypatch, tmp_path)
    monkeypatch.setenv('GOOGLE_API_KEY', 'fake-key')

    recorded: dict = {}

    def fake_transcribe(audio_path, **kwargs):
        recorded['kwargs'] = kwargs

    monkeypatch.setattr('stt.cli.transcribe', fake_transcribe)

    audio_file = tmp_path / 'audio.wav'
    monkeypatch.setattr('sys.argv', ['stt', str(audio_file), '-n', '3', '-p', 'extra context'])

    main()

    assert recorded['kwargs']['speaker_count'] == 3
    assert recorded['kwargs']['extra_instructions'] == 'extra context'


def test_main_transcribe_failure_exits(monkeypatch, tmp_path: Path, capsys):
    log_path = _install_common(monkeypatch, tmp_path)
    monkeypatch.setenv('GOOGLE_API_KEY', 'fake-key')

    def failing_transcribe(audio_path, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr('stt.cli.transcribe', failing_transcribe)

    audio_file = tmp_path / 'audio.wav'
    monkeypatch.setattr('sys.argv', ['stt', str(audio_file)])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = _clean(capsys.readouterr().out)
    assert '轉錄失敗' in captured
    assert 'boom' in captured
    assert str(log_path) in captured


def test_main_happy_path_prints_completion(monkeypatch, tmp_path: Path, capsys):
    log_path = _install_common(monkeypatch, tmp_path)
    monkeypatch.setenv('GOOGLE_API_KEY', 'fake-key')
    monkeypatch.setattr('stt.cli.transcribe', lambda audio_path, **kwargs: None)

    audio_file = tmp_path / 'audio.wav'
    monkeypatch.setattr('sys.argv', ['stt', str(audio_file)])

    main()

    captured = _clean(capsys.readouterr().out)
    assert '完成' in captured
    assert str(log_path) in captured


def test_run_with_progress_hooks_advance_tasks(monkeypatch, tmp_path: Path):
    created: dict = {}

    class RecordingProgress(RichProgress):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created['progress'] = self

    monkeypatch.setattr('stt.cli.Progress', RecordingProgress)

    captured: dict = {}

    def stub_transcribe(audio_path, **kwargs):
        captured['hooks'] = kwargs['hooks']

    monkeypatch.setattr('stt.cli.transcribe', stub_transcribe)

    console = Console(file=io.StringIO())
    audio_file = tmp_path / 'audio.wav'
    output_path = tmp_path / 'audio.json'

    _run_with_progress(
        console,
        audio_file,
        output_path,
        speaker_count=None,
        extra_instructions=None,
        client=object(),
        settings=Settings(),
    )

    hooks = captured['hooks']
    hooks.chunks_ready(2)
    hooks.upload_done()
    hooks.chunk_done()

    tasks = created['progress'].tasks
    assert tasks[0].total == 2
    assert tasks[1].total == 2
    assert tasks[0].completed == 1
    assert tasks[1].completed == 1
