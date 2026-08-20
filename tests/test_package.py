import logging

import stt


def test_all_names_are_importable():
    for name in stt.__all__:
        assert hasattr(stt, name)


def test_null_handler_attached_to_stt_logger():
    logger = logging.getLogger('stt')
    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)
