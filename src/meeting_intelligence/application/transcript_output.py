"""Application orchestration for immutable transcript artifacts."""

from pathlib import Path

from meeting_intelligence.config.settings import Settings
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.media.models import MediaSource
from meeting_intelligence.output.transcript import (
    ProcessingContext,
    TranscriptArtifacts,
    persist_transcript_record,
)


def persist_meeting_transcript(
    transcript: TranscriptRecord,
    source_media: MediaSource,
    source_duration_seconds: float,
    settings: Settings,
) -> TranscriptArtifacts:
    context = ProcessingContext(
        application_version=settings.application_version,
        schema_version=settings.schema_version,
        transcription_provider=settings.transcription_provider,
        transcription_model=settings.transcription_model,
        transcription_response_format=settings.transcription_response_format,
        transcription_language=settings.transcription_language,
    )
    return persist_transcript_record(
        transcript,
        source_media,
        source_duration_seconds,
        context,
        Path(settings.output_dir),
    )
