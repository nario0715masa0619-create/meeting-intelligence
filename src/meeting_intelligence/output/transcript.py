"""Immutable Canonical Transcript Record persistence."""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from meeting_intelligence.domain.errors import (
    OutputExistsError,
    OutputValidationError,
    OutputWriteError,
)
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.media.models import MediaSource
from meeting_intelligence.media.tools import sha256_file


_WINDOWS_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{index}" for index in range(1, 10)), *(f"LPT{index}" for index in range(1, 10))}


@dataclass(frozen=True, slots=True)
class ProcessingContext:
    application_version: str
    schema_version: str
    transcription_provider: str
    transcription_model: str
    transcription_response_format: str
    transcription_language: str
    prompt_version: str | None = None
    processed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TranscriptArtifacts:
    directory: Path
    transcript_json_path: Path
    transcript_markdown_path: Path
    metadata_path: Path
    status: str = "completed"


def _safe_meeting_id(meeting_id: str) -> str:
    if (
        not meeting_id
        or meeting_id in {".", ".."}
        or meeting_id[-1] in {" ", "."}
        or _WINDOWS_UNSAFE.search(meeting_id)
        or meeting_id.split(".", 1)[0].upper() in _WINDOWS_RESERVED
    ):
        raise OutputValidationError("meeting_id is not safe for a Windows output directory")
    return meeting_id


def validate_transcript_for_output(
    transcript: TranscriptRecord,
    *,
    chronological_tolerance: float = 0.001,
    duration_tolerance: float = 1.0,
) -> TranscriptRecord:
    try:
        validated = TranscriptRecord.model_validate(transcript.model_dump(mode="python"))
    except ValidationError as exc:
        raise OutputValidationError("invalid Canonical Transcript Record") from exc
    if not validated.language:
        raise OutputValidationError("transcript language must not be empty")
    seen: set[str] = set()
    previous_start: float | None = None
    for segment in validated.segments:
        if segment.id in seen:
            raise OutputValidationError("transcript contains duplicate segment IDs")
        seen.add(segment.id)
        if previous_start is not None and segment.start + chronological_tolerance < previous_start:
            raise OutputValidationError("transcript segments are not chronological")
        previous_start = segment.start
    if validated.segments:
        final_end = max(segment.end for segment in validated.segments)
        if final_end > validated.duration_seconds + duration_tolerance:
            raise OutputValidationError("transcript segment exceeds transcript duration")
    try:
        validated.model_dump_json().encode("utf-8")
    except UnicodeEncodeError as exc:
        raise OutputValidationError("transcript is not UTF-8 safe") from exc
    return validated


def format_timestamp(seconds: float) -> str:
    total_milliseconds = round(seconds * 1000)
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def render_transcript_markdown(transcript: TranscriptRecord) -> str:
    lines = [
        "# Transcript",
        "",
        f"Meeting ID: {transcript.meeting_id}",
        f"Language: {transcript.language}",
        f"Duration: {format_timestamp(transcript.duration_seconds)}",
        "",
        "---",
    ]
    for segment in transcript.segments:
        speaker = segment.speaker if segment.speaker is not None else "(speaker unknown)"
        lines.extend([
            "",
            f"[{format_timestamp(segment.start)} - {format_timestamp(segment.end)}] {speaker}",
            segment.text,
        ])
    return "\n".join(lines) + "\n"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _write_new(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def persist_transcript_record(
    transcript: TranscriptRecord,
    source_media: MediaSource,
    source_duration_seconds: float,
    processing: ProcessingContext,
    output_root: Path,
) -> TranscriptArtifacts:
    validated = validate_transcript_for_output(transcript)
    meeting_id = _safe_meeting_id(validated.meeting_id)
    if processing.schema_version != validated.schema_version:
        raise OutputValidationError("processing schema version does not match transcript schema version")
    if processing.transcription_language != validated.language:
        raise OutputValidationError("processing language does not match transcript language")
    if source_duration_seconds < 0:
        raise OutputValidationError("source duration must be non-negative")
    if source_media.sha256 != sha256_file(source_media.path):
        raise OutputValidationError("source media changed before output persistence")

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    final_directory = output_root / meeting_id
    if final_directory.exists():
        raise OutputExistsError("meeting output already exists; immutable artifacts cannot be overwritten")
    staging_directory = output_root / f".{meeting_id}.{uuid.uuid4().hex}.tmp"
    processed_at = processing.processed_at or datetime.now(timezone.utc)
    if processed_at.tzinfo is None:
        raise OutputValidationError("processed_at must include timezone information")

    try:
        staging_directory.mkdir()
        transcript_json = staging_directory / "transcript.json"
        transcript_markdown = staging_directory / "transcript.md"
        metadata_json = staging_directory / "metadata.json"
        _write_new(transcript_json, _json_bytes(validated.model_dump(mode="json")))
        _write_new(transcript_markdown, render_transcript_markdown(validated).encode("utf-8"))
        metadata = {
            "meeting_id": meeting_id,
            "source": str(source_media.path.resolve()),
            "status": "completed",
            "processed_at": processed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "application_version": processing.application_version,
            "schema_version": processing.schema_version,
            "prompt_version": processing.prompt_version,
            "transcription": {
                "provider": processing.transcription_provider,
                "model": processing.transcription_model,
                "response_format": processing.transcription_response_format,
                "language": processing.transcription_language,
            },
            "media": {
                "source_sha256": source_media.sha256,
                "source_file_name": source_media.file_name,
                "source_path": str(source_media.path.resolve()),
                "source_size_bytes": source_media.size_bytes,
                "source_duration_seconds": source_duration_seconds,
            },
            "artifacts": {
                "transcript_json": {"path": "transcript.json", "sha256": sha256_file(transcript_json)},
                "transcript_markdown": {"path": "transcript.md", "sha256": sha256_file(transcript_markdown)},
            },
        }
        _write_new(metadata_json, _json_bytes(metadata))
        staging_directory.rename(final_directory)
    except OutputExistsError:
        raise
    except Exception as exc:
        if staging_directory.exists():
            shutil.rmtree(staging_directory, ignore_errors=True)
        raise OutputWriteError("failed to finalize canonical transcript artifacts") from exc

    return TranscriptArtifacts(
        directory=final_directory,
        transcript_json_path=final_directory / "transcript.json",
        transcript_markdown_path=final_directory / "transcript.md",
        metadata_path=final_directory / "metadata.json",
    )
