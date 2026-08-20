from typing import Any

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
