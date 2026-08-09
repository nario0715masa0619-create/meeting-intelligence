"""Minimal media models for reproducible audio preparation."""

from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MediaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediaSource(MediaModel):
    path: Path
    file_name: str
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AudioStreamMetadata(MediaModel):
    index: int
    codec_name: str | None = None
    sample_rate: int | None = Field(default=None, ge=0)
    channels: int | None = Field(default=None, ge=0)
    channel_layout: str | None = None


class MediaMetadata(MediaModel):
    duration_seconds: float | None = Field(default=None, ge=0)
    format_name: str | None = None
    bit_rate: int | None = Field(default=None, ge=0)
    audio_streams: list[AudioStreamMetadata] = Field(default_factory=list)


class AudioChunk(MediaModel):
    chunk_id: str = Field(min_length=1)
    path: Path
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    duration_seconds: float = Field(ge=0)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_times(self) -> "AudioChunk":
        if self.end_seconds < self.start_seconds:
            raise ValueError("chunk end must not precede start")
        if abs((self.end_seconds - self.start_seconds) - self.duration_seconds) > 0.01:
            raise ValueError("chunk duration must match its time range")
        return self


class PreparedAudio(MediaModel):
    source_path: Path
    audio_path: Path
    duration_seconds: float = Field(ge=0)
    size_bytes: int = Field(gt=0)
    format: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunks: list[AudioChunk] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_chunk_order(self) -> "PreparedAudio":
        for previous, current in zip(self.chunks, self.chunks[1:]):
            if previous.end_seconds > current.start_seconds + 0.01:
                raise ValueError("audio chunks must be ordered and non-overlapping")
        return self
