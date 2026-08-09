from typing import Any
from pydantic import ValidationError
from meeting_intelligence.domain.errors import SchemaValidationError
from meeting_intelligence.domain.meeting import MeetingRecord
from meeting_intelligence.domain.transcript import TranscriptRecord


def validate_transcript(data: dict[str, Any] | str | bytes) -> TranscriptRecord:
    try:
        return TranscriptRecord.model_validate(data) if isinstance(data, dict) else TranscriptRecord.model_validate_json(data)
    except ValidationError as exc:
        raise SchemaValidationError("invalid Canonical Transcript Record") from exc


def validate_meeting(data: dict[str, Any] | str | bytes) -> MeetingRecord:
    try:
        return MeetingRecord.model_validate(data) if isinstance(data, dict) else MeetingRecord.model_validate_json(data)
    except ValidationError as exc:
        raise SchemaValidationError("invalid Canonical Meeting Record") from exc
