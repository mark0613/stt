import pytest
from pydantic import ValidationError

from stt.models import (
    TranscriptResult,
    TranscriptSegment,
)


def test_transcript_segment_builds_normally():
    segment = TranscriptSegment(
        speaker='Speaker 1', timestamp='00:01', content='hello', lang_code='zh'
    )
    assert segment.speaker == 'Speaker 1'
    assert segment.timestamp == '00:01'
    assert segment.content == 'hello'
    assert segment.lang_code == 'zh'


def test_coerce_required_string_none_raises():
    with pytest.raises(ValidationError):
        TranscriptSegment(speaker=None, timestamp='00:01', content='hello', lang_code='zh')


def test_coerce_required_string_int_is_coerced():
    segment = TranscriptSegment(speaker=1, timestamp='00:01', content='hello', lang_code='zh')
    assert segment.speaker == '1'
    assert isinstance(segment.speaker, str)


def test_coerce_required_string_float_is_coerced():
    segment = TranscriptSegment(speaker='Speaker 1', timestamp=1.5, content='hello', lang_code='zh')
    assert segment.timestamp == '1.5'
    assert isinstance(segment.timestamp, str)


def test_transcript_segment_ignores_unknown_key():
    segment = TranscriptSegment(
        speaker='Speaker 1',
        timestamp='00:01',
        content='hello',
        lang_code='zh',
        unknown_field='ignored',
    )
    assert not hasattr(segment, 'unknown_field')


def test_transcript_result_defaults_to_empty_segments():
    result = TranscriptResult()
    assert result.segments == []
