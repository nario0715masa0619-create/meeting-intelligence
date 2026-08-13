"""End-to-end batch orchestration composed from existing phase boundaries."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from meeting_intelligence.analysis.base import MeetingAnalysisProvider
from meeting_intelligence.application.analysis import analyze_transcript
from meeting_intelligence.application.media import prepare_meeting_media
from meeting_intelligence.application.transcript_output import persist_meeting_transcript
from meeting_intelligence.application.transcription import transcribe_prepared_audio
from meeting_intelligence.config.settings import Settings
from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.media.models import MediaSource
from meeting_intelligence.media.tools import sha256_file
from meeting_intelligence.output.transcript import TranscriptArtifacts
from meeting_intelligence.output.meeting_minutes import MeetingMinutesContext, persist_meeting_minutes
from meeting_intelligence.sheets.projection import SheetsMeetingContext
from meeting_intelligence.transcription.base import TranscriptionProvider


@dataclass(frozen=True)
class PipelineResult:
    artifacts: TranscriptArtifacts
    analysis: MeetingAnalysis
    meeting_minutes_path: Path


def run_pipeline(
    source_path: Path,
    meeting_id: str,
    settings: Settings,
    transcription_provider: TranscriptionProvider,
    analysis_provider: MeetingAnalysisProvider,
    meeting_sink,
    progress: Callable[[str], None] | None = None,
) -> PipelineResult:
    notify = progress or (lambda _: None)
    source = source_path.expanduser().resolve()
    stat = source.stat()
    source_media = MediaSource(path=source, file_name=source.name, size_bytes=stat.st_size, sha256=sha256_file(source))
    notify("[1/7] Preparing audio")
    prepared = prepare_meeting_media(source, Path(settings.work_dir) / meeting_id, settings)
    notify("[1/7] Audio preparation completed")
    notify("[2/7] Starting transcription")
    transcript = transcribe_prepared_audio(prepared, meeting_id, transcription_provider)
    notify("[2/7] Transcription completed")
    notify("[3/7] Persisting canonical Transcript")
    artifacts = persist_meeting_transcript(transcript, source_media, prepared.duration_seconds, settings)
    notify("[3/7] Canonical Transcript persisted")

    def analysis_progress(message: str) -> None:
        stage = "[4/7]" if message.startswith("Analyzing") else "[5/7]"
        notify(f"{stage} {message}")

    analysis = analyze_transcript(
        transcript,
        analysis_provider,
        max_attempts=settings.analysis_evidence_max_attempts,
        progress=analysis_progress,
    )
    notify("[5/7] Meeting Analysis evidence validated")
    notify("[6/7] Persisting meeting-minutes.md")
    minutes_path = persist_meeting_minutes(
        analysis,
        artifacts.directory,
        MeetingMinutesContext(
            transcript_path=artifacts.transcript_json_path.resolve(),
            source_path=str(source),
        ),
    )
    notify("[6/7] meeting-minutes.md persisted")
    notify("[7/7] Writing Google Sheets projection")
    meeting_sink.write(
        analysis,
        SheetsMeetingContext(source_file=source.name, transcript_path=str(artifacts.transcript_json_path.resolve()), minutes_reference=str(minutes_path)),
    )
    notify("[7/7] Google Sheets projection completed")
    return PipelineResult(artifacts=artifacts, analysis=analysis, meeting_minutes_path=minutes_path)
