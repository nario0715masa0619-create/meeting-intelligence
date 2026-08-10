"""End-to-end batch orchestration composed from existing phase boundaries."""

from dataclasses import dataclass
from pathlib import Path

from meeting_intelligence.analysis.base import MeetingAnalysisProvider
from meeting_intelligence.analysis.validation import validate_analysis_evidence
from meeting_intelligence.application.media import prepare_meeting_media
from meeting_intelligence.application.transcript_output import persist_meeting_transcript
from meeting_intelligence.application.transcription import transcribe_prepared_audio
from meeting_intelligence.config.settings import Settings
from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.media.models import MediaSource
from meeting_intelligence.media.tools import sha256_file
from meeting_intelligence.output.transcript import TranscriptArtifacts
from meeting_intelligence.sheets.projection import SheetsMeetingContext
from meeting_intelligence.transcription.base import TranscriptionProvider


@dataclass(frozen=True)
class PipelineResult:
    artifacts: TranscriptArtifacts
    analysis: MeetingAnalysis


def run_pipeline(
    source_path: Path,
    meeting_id: str,
    settings: Settings,
    transcription_provider: TranscriptionProvider,
    analysis_provider: MeetingAnalysisProvider,
    meeting_sink,
) -> PipelineResult:
    source = source_path.expanduser().resolve()
    stat = source.stat()
    source_media = MediaSource(path=source, file_name=source.name, size_bytes=stat.st_size, sha256=sha256_file(source))
    prepared = prepare_meeting_media(source, Path(settings.work_dir) / meeting_id, settings)
    transcript = transcribe_prepared_audio(prepared, meeting_id, transcription_provider)
    artifacts = persist_meeting_transcript(transcript, source_media, prepared.duration_seconds, settings)
    analysis = validate_analysis_evidence(analysis_provider.analyze(transcript), transcript)
    meeting_sink.write(
        analysis,
        SheetsMeetingContext(source_file=source.name, transcript_path=str(artifacts.transcript_json_path.resolve())),
    )
    return PipelineResult(artifacts=artifacts, analysis=analysis)
