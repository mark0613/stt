import json

from conftest import FakeCandidate, FakeContent, FakeFinishReason, FakePart, FakeResponse

from stt.models import TranscriptSegment
from stt.utils import (
    extract_complete_segment_objects,
    extract_segment_objects_anywhere,
    finish_reason_name,
    is_pathological_repetition,
    parse_segment_object,
    parse_segments,
    response_text,
    segments_array_start,
    strip_code_fence,
    validate_segments,
)


def test_response_text_returns_string_as_is():
    response = FakeResponse(text='hello world')
    assert response_text(response) == 'hello world'


def test_response_text_none_returns_empty_string():
    response = FakeResponse(text=None)
    assert response_text(response) == ''


def test_response_text_raises_no_candidates_returns_empty_string():
    response = FakeResponse(text=FakeResponse.RAISE, candidates=None)
    assert response_text(response) == ''


def test_response_text_raises_empty_candidates_returns_empty_string():
    response = FakeResponse(text=FakeResponse.RAISE, candidates=[])
    assert response_text(response) == ''


def test_response_text_raises_falls_back_to_parts_text():
    parts = [FakePart(text='foo'), FakePart(text='bar')]
    candidate = FakeCandidate(content=FakeContent(parts=parts))
    response = FakeResponse(text=FakeResponse.RAISE, candidates=[candidate])
    assert response_text(response) == 'foobar'


def test_response_text_skips_part_with_none_text():
    parts = [FakePart(text='foo'), FakePart(text=None), FakePart(text='bar')]
    candidate = FakeCandidate(content=FakeContent(parts=parts))
    response = FakeResponse(text=FakeResponse.RAISE, candidates=[candidate])
    assert response_text(response) == 'foobar'


def test_response_text_none_content_falls_back_to_empty_string():
    candidate = FakeCandidate(content=None)
    response = FakeResponse(text=FakeResponse.RAISE, candidates=[candidate])
    assert response_text(response) == ''


def test_finish_reason_name_no_candidates_returns_none():
    response = FakeResponse()
    assert finish_reason_name(response) is None


def test_finish_reason_name_none_finish_reason_returns_none():
    response = FakeResponse(candidates=[FakeCandidate(finish_reason=None)])
    assert finish_reason_name(response) is None


def test_finish_reason_name_enum_returns_name():
    response = FakeResponse(finish_reason=FakeFinishReason.STOP)
    assert finish_reason_name(response) == 'STOP'


def test_finish_reason_name_string_with_dot_rsplits():
    response = FakeResponse(finish_reason='FinishReason.MAX_TOKENS')
    assert finish_reason_name(response) == 'MAX_TOKENS'


def test_finish_reason_name_plain_string_returned_as_is():
    response = FakeResponse(finish_reason='STOP')
    assert finish_reason_name(response) == 'STOP'


def test_parse_segments_valid_json_object(segment, segments_json):
    segments = [segment(speaker='A'), segment(speaker='B', timestamp='00:02')]
    text = segments_json(segments)
    result, complete = parse_segments(text)
    assert complete is True
    assert [item.speaker for item in result] == ['A', 'B']


def test_parse_segments_valid_json_list_not_dict():
    result, complete = parse_segments('[]')
    assert result == []
    assert complete is True


def test_parse_segments_valid_json_dict_no_segments_key():
    result, complete = parse_segments('{}')
    assert result == []
    assert complete is True


def test_parse_segments_malformed_json_falls_back(segment):
    seg = segment(speaker='A')
    obj_text = json.dumps(seg.model_dump(mode='json'), ensure_ascii=False)
    text = '{"segments": [' + obj_text + ', {"speaker"'
    result, complete = parse_segments(text)
    assert complete is False
    assert len(result) == 1
    assert result[0].speaker == 'A'


def test_strip_code_fence_no_fence_returns_stripped_text():
    assert strip_code_fence('  hello world  ') == 'hello world'


def test_strip_code_fence_removes_json_fence():
    text = '```json\n{"a": 1}\n```'
    assert strip_code_fence(text) == '{"a": 1}'


def test_strip_code_fence_unclosed_fence_returns_original():
    text = '```json\n{"a": 1}'
    assert strip_code_fence(text) == text


def test_strip_code_fence_single_line_fence_returns_original():
    assert strip_code_fence('```') == '```'


def test_segments_array_start_finds_bracket_after_segments_key():
    text = '[oldarray] "segments": [1, 2]'
    index = segments_array_start(text)
    assert text[index : index + 6] == '[1, 2]'


def test_segments_array_start_no_segments_key_uses_first_bracket():
    text = 'prefix [1, 2] suffix [3, 4]'
    index = segments_array_start(text)
    assert text[index : index + 6] == '[1, 2]'


def test_segments_array_start_no_bracket_returns_none():
    assert segments_array_start('no brackets here') is None


def test_extract_complete_segment_objects_truncated_returns_complete_only(segment):
    seg_a = json.dumps(segment(speaker='A').model_dump(mode='json'), ensure_ascii=False)
    seg_b = json.dumps(segment(speaker='B').model_dump(mode='json'), ensure_ascii=False)
    text = '{"segments": [' + seg_a + ', ' + seg_b + ', {"speaker"'
    result = extract_complete_segment_objects(text)
    assert [item.speaker for item in result] == ['A', 'B']


def test_extract_complete_segment_objects_handles_braces_in_string(segment):
    seg = segment(content='he said "hi {x}" ok')
    obj_text = json.dumps(seg.model_dump(mode='json'), ensure_ascii=False)
    text = '{"segments": [' + obj_text + ']}'
    result = extract_complete_segment_objects(text)
    assert len(result) == 1
    assert result[0].content == 'he said "hi {x}" ok'


def test_extract_complete_segment_objects_nested_object_tracks_depth(segment):
    seg = segment(speaker='Nested')
    data = seg.model_dump(mode='json')
    data['extra'] = {'nested': 'value'}
    obj_text = json.dumps(data, ensure_ascii=False)
    text = '{"segments": [' + obj_text + ']}'
    result = extract_complete_segment_objects(text)
    assert len(result) == 1
    assert result[0].speaker == 'Nested'


def test_extract_complete_segment_objects_stray_closing_brace_skipped(segment):
    obj_text = json.dumps(segment(speaker='A').model_dump(mode='json'), ensure_ascii=False)
    text = '{"segments": [}, ' + obj_text + ']}'
    result = extract_complete_segment_objects(text)
    assert [item.speaker for item in result] == ['A']


def test_extract_complete_segment_objects_stops_at_closing_bracket(segment):
    seg_a = json.dumps(segment(speaker='A').model_dump(mode='json'), ensure_ascii=False)
    seg_b = json.dumps(segment(speaker='B').model_dump(mode='json'), ensure_ascii=False)
    text = '{"segments": [' + seg_a + ']} trailing ' + seg_b
    result = extract_complete_segment_objects(text)
    assert [item.speaker for item in result] == ['A']


def test_extract_complete_segment_objects_falls_back_when_no_array(segment):
    obj_text = json.dumps(segment(speaker='A').model_dump(mode='json'), ensure_ascii=False)
    result = extract_complete_segment_objects(obj_text)
    assert [item.speaker for item in result] == ['A']


def test_extract_complete_segment_objects_skips_object_failing_validation(segment):
    invalid_text = json.dumps({'speaker': 'Invalid'}, ensure_ascii=False)
    valid_text = json.dumps(segment(speaker='A').model_dump(mode='json'), ensure_ascii=False)
    text = '{"segments": [' + invalid_text + ', ' + valid_text + ']}'
    result = extract_complete_segment_objects(text)
    assert [item.speaker for item in result] == ['A']


def test_extract_segment_objects_anywhere_multiple_standalone_objects(segment):
    seg_a = json.dumps(segment(speaker='A').model_dump(mode='json'), ensure_ascii=False)
    seg_b = json.dumps(segment(speaker='B').model_dump(mode='json'), ensure_ascii=False)
    text = f'noise {seg_a} middle {seg_b} end'
    result = extract_segment_objects_anywhere(text)
    assert [item.speaker for item in result] == ['A', 'B']


def test_extract_segment_objects_anywhere_ignores_braces_in_string(segment):
    seg = segment(content='hi {x} "y" done')
    obj_text = json.dumps(seg.model_dump(mode='json'), ensure_ascii=False)
    result = extract_segment_objects_anywhere(obj_text)
    assert len(result) == 1
    assert result[0].content == 'hi {x} "y" done'


def test_extract_segment_objects_anywhere_handles_backslash_escape(segment):
    seg = segment(content='back\\slash "quote"')
    obj_text = json.dumps(seg.model_dump(mode='json'), ensure_ascii=False)
    result = extract_segment_objects_anywhere(obj_text)
    assert len(result) == 1
    assert result[0].content == 'back\\slash "quote"'


def test_extract_segment_objects_anywhere_skips_object_failing_validation(segment):
    invalid_text = json.dumps({'speaker': 'Invalid'}, ensure_ascii=False)
    valid_text = json.dumps(segment(speaker='A').model_dump(mode='json'), ensure_ascii=False)
    text = f'{invalid_text} {valid_text}'
    result = extract_segment_objects_anywhere(text)
    assert [item.speaker for item in result] == ['A']


def test_extract_segment_objects_anywhere_stray_closing_brace_no_raise(segment):
    obj_text = json.dumps(segment(speaker='A').model_dump(mode='json'), ensure_ascii=False)
    text = '} ' + obj_text
    result = extract_segment_objects_anywhere(text)
    assert [item.speaker for item in result] == ['A']


def test_parse_segment_object_invalid_json_returns_none():
    assert parse_segment_object('not json') is None


def test_parse_segment_object_missing_fields_returns_none():
    assert parse_segment_object('{"speaker": "A"}') is None


def test_parse_segment_object_valid_returns_segment(segment):
    seg = segment(speaker='A', timestamp='00:05', content='hi there', lang_code='en')
    text = json.dumps(seg.model_dump(mode='json'), ensure_ascii=False)
    result = parse_segment_object(text)
    assert isinstance(result, TranscriptSegment)
    assert result.speaker == 'A'
    assert result.timestamp == '00:05'
    assert result.content == 'hi there'
    assert result.lang_code == 'en'


def test_validate_segments_non_list_dict_returns_empty():
    assert validate_segments({'not': 'a list'}) == []


def test_validate_segments_non_list_none_returns_empty():
    assert validate_segments(None) == []


def test_validate_segments_skips_invalid_keeps_valid(segment):
    valid = segment(speaker='A').model_dump(mode='json')
    invalid = {'speaker': 'B'}
    result = validate_segments([valid, invalid])
    assert len(result) == 1
    assert result[0].speaker == 'A'


def test_validate_segments_skips_pathological_repetition():
    assert is_pathological_repetition('あ' * 250) is True
    data = {'speaker': 'A', 'timestamp': '00:01', 'content': 'あ' * 250, 'lang_code': 'ja'}
    result = validate_segments([data])
    assert result == []
