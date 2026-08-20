import string

from stt.utils import (
    is_duplicate_segment,
    is_pathological_repetition,
    merge_segments,
    segment_key,
)


class _ExplodingList(list):
    """用來證明 is_duplicate_segment 在 key 已存在 saved_keys 時，不會去迭代 recent_segments。"""

    def __iter__(self):
        raise AssertionError('recent_segments should not be consulted')


# ---------------------------------------------------------------------------
# is_pathological_repetition
# ---------------------------------------------------------------------------


def test_is_pathological_repetition_short_content_is_false():
    assert is_pathological_repetition('hello world') is False


def test_is_pathological_repetition_repeated_cjk_char_is_true():
    content = '你' * 250
    assert is_pathological_repetition(content) is True


def test_is_pathological_repetition_varied_content_is_false():
    content = (string.ascii_lowercase * 10)[:250]
    assert len(content) == 250
    assert is_pathological_repetition(content) is False


def test_is_pathological_repetition_pure_punctuation_does_not_raise():
    filler = " ,，.。、!?！？;；:：…~～'「」『』（）()-"
    content = (filler * 30)[:250]
    assert len(content) == 250
    assert is_pathological_repetition(content) is False


# ---------------------------------------------------------------------------
# segment_key
# ---------------------------------------------------------------------------


def test_segment_key_normalizes_speaker_timestamp_and_content(segment):
    cosmetic = segment(
        speaker=' Speaker 1 ',
        timestamp='00:01 (approx)',
        content='  Hello   World  ',
    )
    clean = segment(
        speaker='SPEAKER 1',
        timestamp='00:01',
        content='hello world',
    )

    key = segment_key(cosmetic)

    assert key == ('speaker 1', '00:01', 'hello world')
    assert segment_key(cosmetic) == segment_key(clean)


# ---------------------------------------------------------------------------
# is_duplicate_segment
# ---------------------------------------------------------------------------


def test_is_duplicate_segment_key_in_saved_keys_returns_true_without_scanning_recent(segment):
    seg = segment(timestamp='00:01', content='hello world')
    saved_keys = {segment_key(seg)}

    result = is_duplicate_segment(seg, _ExplodingList(), saved_keys)

    assert result is True


def test_is_duplicate_segment_new_content_blank_continues_and_returns_false(segment):
    new_segment = segment(content='   ')
    old_segment = segment(timestamp='00:01', content='some unrelated content here')

    result = is_duplicate_segment(new_segment, [old_segment], set())

    assert result is False


def test_is_duplicate_segment_skips_old_blank_content_then_finds_later_duplicate(segment):
    old_blank = segment(content='')
    old_duplicate = segment(timestamp='00:01', content='hello world this is a duplicate test')
    new_segment = segment(timestamp='00:01', content='hello world this is a duplicate test')

    result = is_duplicate_segment(new_segment, [old_blank, old_duplicate], set())

    assert result is True


def test_is_duplicate_segment_same_timestamp_high_ratio_is_true(segment):
    old_segment = segment(timestamp='00:01', content='the fox runs fast')
    new_segment = segment(timestamp='00:01', content='the fox runs fast!')

    result = is_duplicate_segment(new_segment, [old_segment], set())

    assert result is True


def test_is_duplicate_segment_close_timestamp_long_content_high_ratio_is_true(segment):
    old_segment = segment(timestamp='00:10', content='a' * 35)
    new_segment = segment(timestamp='00:11', content='a' * 34 + 'b')

    result = is_duplicate_segment(new_segment, [old_segment], set())

    assert result is True


def test_is_duplicate_segment_close_timestamp_short_content_length_guard_false(segment):
    old_segment = segment(timestamp='00:10', content='a' * 20)
    new_segment = segment(timestamp='00:11', content='a' * 20)

    result = is_duplicate_segment(new_segment, [old_segment], set())

    assert result is False


def test_is_duplicate_segment_same_timestamp_low_ratio_short_content_false(segment):
    old_segment = segment(timestamp='00:05', content='completely different text here')
    new_segment = segment(timestamp='00:05', content='xyz')

    result = is_duplicate_segment(new_segment, [old_segment], set())

    assert result is False


def test_is_duplicate_segment_recent_segments_empty_is_false(segment):
    new_segment = segment(timestamp='00:01', content='some content here')

    result = is_duplicate_segment(new_segment, [], set())

    assert result is False


def test_is_duplicate_segment_unparseable_timestamp_close_timestamp_is_false(segment):
    old_segment = segment(timestamp='00:05', content='a' * 35)
    new_segment = segment(timestamp='not-a-timestamp', content='a' * 35)

    result = is_duplicate_segment(new_segment, [old_segment], set())

    assert result is False


# ---------------------------------------------------------------------------
# merge_segments
# ---------------------------------------------------------------------------


def test_merge_segments_empty_saved_returns_new_segments_unchanged(segment):
    new_segments = [
        segment(timestamp='00:01', content='first new content'),
        segment(timestamp='00:02', content='second new content'),
    ]

    merged, added = merge_segments([], new_segments)

    assert merged is new_segments
    assert added == 2


def test_merge_segments_skips_pathological_new_segment(segment):
    saved = [segment(timestamp='00:01', content='normal saved content')]
    new_segments = [segment(timestamp='00:01', content='x' * 250)]

    merged, added = merge_segments(saved, new_segments)

    assert merged == saved
    assert added == 0


def test_merge_segments_skips_earlier_timestamp(segment):
    saved = [segment(timestamp='05:00', content='saved important content')]
    new_segments = [segment(timestamp='01:00', content='brand new distinct content here')]

    merged, added = merge_segments(saved, new_segments)

    assert merged == saved
    assert added == 0


def test_merge_segments_skips_duplicate_of_saved(segment):
    saved = [segment(timestamp='01:00', content='saved base content one')]
    new_segments = [segment(timestamp='01:00', content='saved base content one')]

    merged, added = merge_segments(saved, new_segments)

    assert merged == saved
    assert added == 0


def test_merge_segments_appends_normal_segment(segment):
    saved = [segment(timestamp='01:00', content='saved base content one')]
    new_segment = segment(timestamp='02:00', content='brand new distinct content two')

    merged, added = merge_segments(saved, [new_segment])

    assert added == 1
    assert merged == [*saved, new_segment]


def test_merge_segments_unparseable_new_timestamp_is_not_time_filtered(segment):
    saved = [segment(timestamp='05:00', content='saved base content one')]
    new_segment = segment(timestamp='not-a-timestamp', content='brand new distinct content two')

    merged, added = merge_segments(saved, [new_segment])

    assert added == 1
    assert merged == [*saved, new_segment]


def test_merge_segments_same_second_is_not_filtered_by_time_check(segment):
    saved = [segment(timestamp='01:00', content='saved unique content abc')]
    new_segment = segment(timestamp='01:00', content='completely different unrelated text')

    merged, added = merge_segments(saved, [new_segment])

    assert added == 1
    assert merged == [*saved, new_segment]


def test_merge_segments_handles_recent_window_trimming(segment):
    saved = [segment(timestamp=f'00:{i:02d}', content=f'saved segment {i}') for i in range(1, 26)]
    new_segments = [
        segment(timestamp=f'01:{i:02d}', content=f'new segment {i}') for i in range(1, 26)
    ]

    merged, added = merge_segments(saved, new_segments)

    assert added == 25
    assert len(merged) == 50
    assert merged == [*saved, *new_segments]
