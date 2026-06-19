from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra='ignore')

    speaker: str = Field(description='Speaker label, such as Speaker 1 or a detected name.')
    timestamp: str = Field(description='Segment timestamp in MM:SS or HH:MM:SS format.')
    content: str = Field(description='Verbatim transcription content.')
    lang_code: str = Field(description='Primary language code for this segment.')

    @field_validator('speaker', 'timestamp', 'content', 'lang_code', mode='before')
    @classmethod
    def coerce_required_string(cls, value: Any) -> str:
        if value is None:
            raise ValueError('field is required')
        return str(value)


class TranscriptResult(BaseModel):
    model_config = ConfigDict(extra='ignore')

    segments: list[TranscriptSegment] = Field(
        default_factory=list,
        description='List of transcribed segments with speaker, timestamp, content, and language.',
    )


class TranscriptStateEvent(BaseModel):
    model_config = ConfigDict(extra='ignore')

    iteration: int
    created_at: str
    cursor_before: str
    cursor_after: str
    finish_reason: str | None = None
    parsed_complete_json: bool
    segments_returned: int
    segments_added: int
    saved_segment_count: int
    response_id: str | None = None
    model_version: str | None = None
    usage_metadata: Any = None


class TranscriptState(BaseModel):
    model_config = ConfigDict(extra='ignore')

    schema_version: int = 1
    status: Literal['new', 'in_progress', 'truncated', 'complete', 'stopped'] = 'new'
    source_audio: str
    output_path: str | None = None
    uploaded_file_uri: str | None = None
    model: str
    max_output_tokens: int
    created_at: str
    updated_at: str
    saved_until_timestamp: str | None = None
    saved_segment_count: int = 0
    last_finish_reason: str | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)
    events: list[TranscriptStateEvent] = Field(default_factory=list)
