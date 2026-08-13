"""Resume Meeting Analysis from immutable Canonical Transcript evidence."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from meeting_intelligence.analysis.base import MeetingAnalysisProvider
from meeting_intelligence.application.analysis import analyze_transcript
from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.domain.errors import OutputValidationError
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.output.transcript import validate_transcript_for_output
from meeting_intelligence.sheets.projection import SheetsMeetingContext


@dataclass(frozen=True)
class AnalysisResumeResult:
    transcript_path: Path
    analysis: MeetingAnalysis


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
    notify("[4/4] Writing Google Sheets")
    meeting_sink.write(
        analysis,
        SheetsMeetingContext(transcript_path=str(resolved_path)),
    )
    notify("[4/4] Google Sheets write completed")
    return AnalysisResumeResult(transcript_path=resolved_path, analysis=analysis)
