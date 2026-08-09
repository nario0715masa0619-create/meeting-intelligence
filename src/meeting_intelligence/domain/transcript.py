"""Canonical Transcript Record models."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    speaker: str | None = None
    text: str

    @model_validator(mode="after")
    def validate_times(self) -> "TranscriptSegment":
        if self.end < self.start:
            raise ValueError("segment end must be greater than or equal to start")
        return self


class TranscriptRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1.0"] = "0.1.0"
    meeting_id: str = Field(min_length=1)
    language: str
    duration_seconds: float = Field(ge=0)
    segments: list[TranscriptSegment] = Field(default_factory=list)
