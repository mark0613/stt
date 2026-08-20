import logging
from pathlib import Path

from stt.logging_setup import get_logger, setup_logging


def test_setup_logging_creates_log_file_under_logs_dir(tmp_path):
    log_path = setup_logging(Path('a/b.mp3'), logs_dir=tmp_path)

    assert log_path.parent == tmp_path
    assert log_path.name.endswith('-b.log')

    logger = logging.getLogger('stt')
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.FileHandler)
    assert logger.propagate is False
    assert logger.level == logging.INFO


def test_setup_logging_defaults_to_cwd_logs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    log_path = setup_logging(Path('audio.mp3'))

    assert log_path.parent == tmp_path / 'logs'
    assert log_path.name.endswith('-audio.log')


def test_setup_logging_twice_leaves_one_handler(tmp_path):
    setup_logging(Path('a/b.mp3'), logs_dir=tmp_path)
    setup_logging(Path('a/c.mp3'), logs_dir=tmp_path)

    logger = logging.getLogger('stt')
    assert len(logger.handlers) == 1


def test_get_logger_default_name():
    logger = get_logger()
    assert logger.name == 'stt'


def test_get_logger_with_suffix():
    logger = get_logger('audio')
    assert logger.name == 'stt.audio'
