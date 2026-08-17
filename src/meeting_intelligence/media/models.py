"""Minimal media models for reproducible audio preparation."""

import hashlib
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MediaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediaSource(MediaModel):
    path: Path
    file_name: str
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class MeetingSourcePart(MediaModel):
    sequence: int = Field(ge=1)
    path: Path
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_seconds: float | None = Field(default=None, ge=0)


class MeetingSource(MediaModel):
    directory: Path
    relative_directory: str
    parts: list[MeetingSourcePart] = Field(min_length=1)
    composite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def source_type(self) -> str:
        return "single" if len(self.parts) == 1 else "multi"

    @classmethod
    def from_parts(cls, directory: Path, relative_directory: str, parts: list[MeetingSourcePart]) -> "MeetingSource":
        ordered = sorted(parts, key=lambda part: part.relative_path.casefold())
        normalized = [part.model_copy(update={"sequence": index}) for index, part in enumerate(ordered, start=1)]
        manifest = [{"relative_path": part.relative_path, "size_bytes": part.size_bytes, "sha256": part.sha256} for part in normalized]
        digest = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        return cls(directory=directory, relative_directory=relative_directory, parts=normalized, composite_sha256=digest)


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
