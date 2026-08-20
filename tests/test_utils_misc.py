from enum import Enum

from stt.utils import (
    is_transient_error,
    last_timestamp,
    normalized_content,
    normalized_timestamp,
    sleep_before_retry,
    timestamp_seconds,
)


def test_normalized_timestamp_match():
    assert normalized_timestamp('[00:12] hi') == '00:12'


def test_normalized_timestamp_no_match():
    assert normalized_timestamp('  abc ') == 'abc'


def test_timestamp_seconds_none_input():
    assert timestamp_seconds(None) is None


def test_timestamp_seconds_empty_string():
    assert timestamp_seconds('') is None


def test_timestamp_seconds_single_part():
    assert timestamp_seconds('12') is None


def test_timestamp_seconds_four_parts():
    assert timestamp_seconds('a:b:c:d') is None


def test_timestamp_seconds_value_error():
    assert timestamp_seconds('ab:cd') is None


def test_timestamp_seconds_mm_ss():
    assert timestamp_seconds('01:30') == 90.0


def test_timestamp_seconds_hh_mm_ss():
    assert timestamp_seconds('1:00:30') == 3630.0


def test_timestamp_seconds_fractional():
    assert timestamp_seconds('00:01.5') == 1.5


def test_normalized_content_collapses_and_lowercases():
    assert normalized_content('  Hello   WORLD \n') == 'hello world'


def test_last_timestamp_empty_list():
    assert last_timestamp([]) is None


def test_last_timestamp_returns_last_segment_timestamp(segment):
    segments = [segment(timestamp='00:01'), segment(timestamp='00:02')]
    assert last_timestamp(segments) == '00:02'


class SampleEnum(Enum):
    FOO = 'foo'


def test_is_transient_error_true_codes():
    for code in ('429', '500', '502', '503', '504', 'UNAVAILABLE'):
        assert is_transient_error(Exception(f'error {code} occurred')) is True


def test_is_transient_error_false():
    assert is_transient_error(Exception('400 bad request')) is False


def test_sleep_before_retry_records_seconds(no_sleep):
    sleep_before_retry(2, 10)
    assert no_sleep == [20]
