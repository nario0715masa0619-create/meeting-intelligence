"""Resume Meeting Analysis from immutable Canonical Transcript evidence."""

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path

from pydantic import ValidationError

from meeting_intelligence.analysis.base import MeetingAnalysisProvider
from meeting_intelligence.application.analysis import analyze_transcript
from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.domain.errors import OutputValidationError
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.output.transcript import validate_transcript_for_output
from meeting_intelligence.output.meeting_minutes import MeetingMinutesContext, persist_meeting_minutes
from meeting_intelligence.sheets.projection import SheetsMeetingContext


@dataclass(frozen=True)
class AnalysisResumeResult:
    transcript_path: Path
    analysis: MeetingAnalysis
    meeting_minutes_path: Path


def load_transcript_record(path: Path) -> TranscriptRecord:
    transcript_path = path.expanduser().resolve()
    if not transcript_path.is_file():
        raise OutputValidationError("transcript file does not exist")
    try:
        content = transcript_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OutputValidationError("transcript file is not valid UTF-8") from exc
    try:
        transcript = TranscriptRecord.model_validate_json(content)
    except ValidationError as exc:
        raise OutputValidationError("transcript file is not a valid Canonical Transcript Record") from exc
    validated = validate_transcript_for_output(transcript)
    if not validated.segments:
        raise OutputValidationError("transcript must contain at least one segment")
    return validated


def resume_analysis(
    transcript_path: Path,
    analysis_provider: MeetingAnalysisProvider,
    meeting_sink,
    *,
    expected_meeting_id: str | None = None,
    max_attempts: int = 2,
    progress: Callable[[str], None] | None = None,
) -> AnalysisResumeResult:
    notify = progress or (lambda _: None)
    notify("[1/4] Loading transcript")
    resolved_path = transcript_path.expanduser().resolve()
    transcript = load_transcript_record(resolved_path)
    if expected_meeting_id is not None and expected_meeting_id != transcript.meeting_id:
        raise OutputValidationError("explicit meeting_id does not match transcript meeting_id")

    def analysis_progress(message: str) -> None:
        if message.startswith("Analyzing"):
            notify(f"[2/4] {message}")
        else:
            notify(f"[3/4] {message}")

    analysis = analyze_transcript(
        transcript,
        analysis_provider,
        max_attempts=max_attempts,
        progress=analysis_progress,
    )
    source_reference = ""
    metadata_path = resolved_path.with_name("metadata.json")
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            source_reference = str(metadata.get("media", {}).get("source_path") or metadata.get("source") or "")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            source_reference = ""
    notify("[4/5] Persisting meeting-minutes.md")
    minutes_path = persist_meeting_minutes(
        analysis,
        resolved_path.parent,
        MeetingMinutesContext(transcript_path=resolved_path, source_path=source_reference),
    )
    notify("[4/5] meeting-minutes.md persisted")
    notify("[5/5] Writing Google Sheets")
    meeting_sink.write(
        analysis,
        SheetsMeetingContext(source_file=source_reference, transcript_path=str(resolved_path), minutes_reference=str(minutes_path)),
    )
    notify("[5/5] Google Sheets write completed")
    return AnalysisResumeResult(transcript_path=resolved_path, analysis=analysis, meeting_minutes_path=minutes_path)


def migrate_analysis_minutes(
    transcript_path: Path,
    analysis_provider: MeetingAnalysisProvider,
    meeting_sink,
    *,
    expected_meeting_id: str,
    max_attempts: int = 2,
    progress: Callable[[str], None] | None = None,
) -> AnalysisResumeResult:
    """Explicit one-time resume that updates one existing Sheets row, never appending."""
    notify = progress or (lambda _: None)
    resolved_path = transcript_path.expanduser().resolve()
    notify("[1/5] Loading transcript")
    transcript = load_transcript_record(resolved_path)
    if transcript.meeting_id != expected_meeting_id:
        raise OutputValidationError("explicit meeting_id does not match transcript meeting_id")

    analysis = analyze_transcript(
        transcript,
        analysis_provider,
        max_attempts=max_attempts,
        progress=lambda message: notify(f"[2/5] {message}" if message.startswith("Analyzing") else f"[3/5] {message}"),
    )
    source_reference = ""
    metadata_path = resolved_path.with_name("metadata.json")
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            source_reference = str(metadata.get("media", {}).get("source_path") or metadata.get("source") or "")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            source_reference = ""
    notify("[4/5] Persisting meeting-minutes.md")
    minutes_path = persist_meeting_minutes(
        analysis,
        resolved_path.parent,
        MeetingMinutesContext(transcript_path=resolved_path, source_path=source_reference),
    )
    notify("[5/5] Migrating existing Google Sheets row")
    meeting_sink.migrate_minutes_reference(analysis.meeting_id, str(minutes_path))
    notify("[5/5] Existing Google Sheets row migrated and verified")
    return AnalysisResumeResult(transcript_path=resolved_path, analysis=analysis, meeting_minutes_path=minutes_path)
