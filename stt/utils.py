import json
import re
import time
from collections import Counter
from difflib import SequenceMatcher
from enum import Enum
from typing import Any

from pydantic import ValidationError

from .models import TranscriptSegment

TIMESTAMP_RE = re.compile(r'\d+(?::\d{1,2}){1,2}(?:\.\d+)?')
FILLER_PUNCTUATION_RE = re.compile(r'[\s,，.。、!?！？;；:：…~～"\'「」『』（）()\\-]+')


def response_text(response: Any) -> str:
    try:
        return response.text or ''
    except ValueError:
        pass

    candidates = getattr(response, 'candidates', None) or []
    if not candidates:
        return ''

    content = getattr(candidates[0], 'content', None)
    parts = getattr(content, 'parts', None) or []
    return ''.join(str(text) for part in parts if (text := getattr(part, 'text', None)))


def finish_reason_name(response: Any) -> str | None:
    candidates = getattr(response, 'candidates', None) or []
    if not candidates:
        return None

    finish_reason = getattr(candidates[0], 'finish_reason', None)
    if finish_reason is None:
        return None
    if isinstance(finish_reason, Enum):
        return finish_reason.name
    return str(finish_reason).rsplit('.', maxsplit=1)[-1]


def parse_segments(response_text: str) -> tuple[list[TranscriptSegment], bool]:
    text = strip_code_fence(response_text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return extract_complete_segment_objects(text), False

    if not isinstance(data, dict):
        return [], True
    return validate_segments(data.get('segments', [])), True


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith('```'):
        return text

    lines = text.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == '```':
        return '\n'.join(lines[1:-1]).strip()
    return text


def extract_complete_segment_objects(text: str) -> list[TranscriptSegment]:
    array_start = segments_array_start(text)
    if array_start is None:
        return extract_segment_objects_anywhere(text)

    segments: list[TranscriptSegment] = []
    depth = 0
    object_start: int | None = None
    in_string = False
    escaping = False

    for index in range(array_start + 1, len(text)):
        char = text[index]

        if in_string:
            if escaping:
                escaping = False
            elif char == '\\':
                escaping = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == '{':
            if depth == 0:
                object_start = index
            depth += 1
        elif char == '}':
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and object_start is not None:
                segment = parse_segment_object(text[object_start : index + 1])
                if segment:
                    segments.append(segment)
                object_start = None
        elif char == ']' and depth == 0:
            break

    return segments


def extract_segment_objects_anywhere(text: str) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    starts: list[int] = []
    in_string = False
    escaping = False

    for index, char in enumerate(text):
        if in_string:
            if escaping:
                escaping = False
            elif char == '\\':
                escaping = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == '{':
            starts.append(index)
        elif char == '}' and starts:
            object_start = starts.pop()
            segment = parse_segment_object(text[object_start : index + 1])
            if segment:
                segments.append(segment)

    return segments


def segments_array_start(text: str) -> int | None:
    segments_key = text.find('"segments"')
    search_start = segments_key if segments_key != -1 else 0

    array_start = text.find('[', search_start)
    if array_start == -1:
        return None
    return array_start


def parse_segment_object(text: str) -> TranscriptSegment | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None

    segments = validate_segments([value])
    return segments[0] if segments else None


def validate_segments(value: Any) -> list[TranscriptSegment]:
    if not isinstance(value, list):
        return []

    segments = []
    for segment in value:
        try:
            parsed_segment = TranscriptSegment.model_validate(segment)
        except ValidationError:
            continue
        if is_pathological_repetition(parsed_segment.content):
            continue
        segments.append(parsed_segment)

    return segments


def merge_segments(
    saved_segments: list[TranscriptSegment],
    new_segments: list[TranscriptSegment],
) -> tuple[list[TranscriptSegment], int]:
    if not saved_segments:
        return new_segments, len(new_segments)

    merged = list(saved_segments)
    saved_keys = {segment_key(segment) for segment in saved_segments}
    recent_segments = saved_segments[-20:]
    last_saved_seconds = timestamp_seconds(last_timestamp(saved_segments))

    for segment in new_segments:
        if is_pathological_repetition(segment.content):
            continue

        segment_seconds = timestamp_seconds(segment.timestamp)
        if (
            segment_seconds is not None
            and last_saved_seconds is not None
            and segment_seconds < last_saved_seconds
        ):
            continue

        if is_duplicate_segment(segment, recent_segments, saved_keys):
            continue

        merged.append(segment)
        saved_keys.add(segment_key(segment))
        recent_segments.append(segment)
        recent_segments = recent_segments[-20:]

    return merged, len(merged) - len(saved_segments)


def is_pathological_repetition(content: str) -> bool:
    compact = FILLER_PUNCTUATION_RE.sub('', content)
    if len(compact) < 200:
        return False

    most_common_count = Counter(compact).most_common(1)[0][1]
    return most_common_count / len(compact) >= 0.9


def is_duplicate_segment(
    segment: TranscriptSegment,
    recent_segments: list[TranscriptSegment],
    saved_keys: set[tuple[str, str, str]],
) -> bool:
    if segment_key(segment) in saved_keys:
        return True

    content = normalized_content(segment.content)
    timestamp = normalized_timestamp(segment.timestamp)
    seconds = timestamp_seconds(segment.timestamp)

    for old_segment in recent_segments:
        old_content = normalized_content(old_segment.content)
        old_timestamp = normalized_timestamp(old_segment.timestamp)
        old_seconds = timestamp_seconds(old_segment.timestamp)
        if not content or not old_content:
            continue

        same_timestamp = timestamp == old_timestamp
        close_timestamp = (
            seconds is not None and old_seconds is not None and abs(seconds - old_seconds) <= 2
        )
        similarity = SequenceMatcher(None, content, old_content).ratio()
        if same_timestamp and similarity >= 0.85:
            return True
        if close_timestamp and len(content) >= 30 and similarity >= 0.96:
            return True

    return False


def segment_key(segment: TranscriptSegment) -> tuple[str, str, str]:
    return (
        segment.speaker.strip().lower(),
        normalized_timestamp(segment.timestamp),
        normalized_content(segment.content),
    )


def last_timestamp(segments: list[TranscriptSegment]) -> str | None:
    if not segments:
        return None
    return segments[-1].timestamp


def normalized_timestamp(timestamp: str) -> str:
    match = TIMESTAMP_RE.search(timestamp)
    return match.group(0) if match else timestamp.strip()


def timestamp_seconds(timestamp: str | None) -> float | None:
    if not timestamp:
        return None

    normalized = normalized_timestamp(timestamp)
    parts = normalized.split(':')
    if len(parts) not in (2, 3):
        return None

    try:
        values = [float(part) for part in parts]
    except ValueError:
        return None

    if len(values) == 2:
        minutes, seconds = values
        return minutes * 60 + seconds

    hours, minutes, seconds = values
    return hours * 3600 + minutes * 60 + seconds


def normalized_content(content: str) -> str:
    return ' '.join(content.strip().lower().split())


def is_transient_error(error: Exception) -> bool:
    message = str(error)
    return any(code in message for code in ('429', '500', '502', '503', '504', 'UNAVAILABLE'))


def sleep_before_retry(attempt: int, base_seconds: int) -> None:
    time.sleep(base_seconds * attempt)
