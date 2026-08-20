from __future__ import annotations

from pathlib import Path

import pytest

from stt.audio import Chunk, _run, audio_duration, choose_cut_points, silence_midpoints, split_audio
from stt.config import Settings
from tests.conftest import completed


def test_chunk_duration():
    chunk = Chunk(idx=1, path=Path('chunk_001.wav'), start_sec=10.0, end_sec=42.5)
    assert chunk.duration == 32.5


def test_run_calls_subprocess_with_expected_kwargs(monkeypatch):
    captured: dict = {}

    def fake_subprocess_run(cmd, **kwargs):
        captured['cmd'] = cmd
        captured['kwargs'] = kwargs
        return completed(stdout='ok')

    monkeypatch.setattr('stt.audio.subprocess.run', fake_subprocess_run)

    cmd = ['ffprobe', '-v', 'quiet']
    result = _run(cmd)

    assert captured['cmd'] == cmd
    assert captured['kwargs'] == {
        'capture_output': True,
        'text': True,
        'encoding': 'utf-8',
        'errors': 'replace',
    }
    assert result.stdout == 'ok'


def test_audio_duration(fake_run):
    recorder = fake_run(results=[completed(stdout='123.45\n')])

    result = audio_duration(Path('audio.wav'))

    assert result == 123.45
    assert recorder.commands[0][0] == 'ffprobe'


def test_silence_midpoints_normal(fake_run, settings: Settings):
    stderr = 'silence_start: 10.0\nsilence_end: 12.0\nsilence_start: 40.5\nsilence_end: 41.5\n'
    recorder = fake_run(results=[completed(stderr=stderr)])

    result = silence_midpoints(Path('audio.wav'), settings)

    assert result == [11.0, 41.0]
    assert recorder.commands[0] == [
        'ffmpeg',
        '-i',
        'audio.wav',
        '-af',
        f'silencedetect=noise={settings.silence_noise_db}dB:d={settings.silence_min_duration}',
        '-f',
        'null',
        '-',
    ]


def test_silence_midpoints_unequal_counts_are_truncated(fake_run, settings: Settings):
    stderr = 'silence_start: 1.0\nsilence_start: 5.0\nsilence_end: 3.0\n'
    fake_run(results=[completed(stderr=stderr)])

    result = silence_midpoints(Path('audio.wav'), settings)

    assert result == [2.0]


def test_silence_midpoints_no_silence(fake_run, settings: Settings):
    fake_run(results=[completed(stderr='no relevant lines here')])

    result = silence_midpoints(Path('audio.wav'), settings)

    assert result == []


def test_choose_cut_points_empty_midpoints(settings: Settings):
    assert choose_cut_points([], 5000.0, settings) == []


def test_choose_cut_points_short_duration(settings: Settings):
    custom = settings.model_copy(update={'target_chunk_seconds': 100})
    assert choose_cut_points([50.0], 100.0, custom) == []


def test_choose_cut_points_normal_multiple_and_natural_exit(settings: Settings):
    custom = settings.model_copy(update={'target_chunk_seconds': 100, 'max_chunk_seconds': 150})

    result = choose_cut_points([95.0, 105.0, 200.0], 250.0, custom)

    assert result == [95.0, 200.0]


def test_choose_cut_points_break_when_target_exceeds_duration(settings: Settings):
    custom = settings.model_copy(update={'target_chunk_seconds': 100, 'max_chunk_seconds': 150})

    result = choose_cut_points([90.0], 150.0, custom)

    assert result == [90.0]


def test_choose_cut_points_hard_cut_without_candidate(settings: Settings):
    custom = settings.model_copy(update={'target_chunk_seconds': 100, 'max_chunk_seconds': 120})

    result = choose_cut_points([250.0], 300.0, custom)

    assert result == [100.0, 200.0]


def test_split_audio_no_cut_points(fake_run, settings: Settings, tmp_path: Path):
    fake_run(
        results=[
            completed(stdout='10.0\n'),
            completed(stderr=''),
            completed(returncode=0),
        ]
    )

    chunks = split_audio(Path('source.wav'), tmp_path, settings)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.idx == 1
    assert chunk.start_sec == 0.0
    assert chunk.end_sec == 10.0
    assert chunk.path == tmp_path / 'chunk_001.wav'


def test_split_audio_with_cut_points(fake_run, tmp_path: Path):
    custom = Settings(target_chunk_seconds=100, max_chunk_seconds=150)
    stderr = 'silence_start: 90.0\nsilence_end: 100.0\nsilence_start: 195.0\nsilence_end: 205.0\n'
    fake_run(
        results=[
            completed(stdout='250.0\n'),
            completed(stderr=stderr),
            completed(returncode=0),
            completed(returncode=0),
            completed(returncode=0),
        ]
    )

    chunks = split_audio(Path('source.wav'), tmp_path, custom)

    assert [(c.idx, c.start_sec, c.end_sec) for c in chunks] == [
        (1, 0.0, 95.0),
        (2, 95.0, 200.0),
        (3, 200.0, 250.0),
    ]
    assert [c.path.name for c in chunks] == ['chunk_001.wav', 'chunk_002.wav', 'chunk_003.wav']


def test_split_audio_ffmpeg_failure_raises(fake_run, settings: Settings, tmp_path: Path):
    fake_run(
        results=[
            completed(stdout='10.0\n'),
            completed(stderr=''),
            completed(returncode=1, stderr='boom: disk full'),
        ]
    )

    with pytest.raises(RuntimeError) as exc_info:
        split_audio(Path('source.wav'), tmp_path, settings)

    assert 'chunk 1' in str(exc_info.value)
    assert 'boom: disk full' in str(exc_info.value)
