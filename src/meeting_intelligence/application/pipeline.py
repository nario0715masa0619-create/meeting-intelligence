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
from meeting_intelligence.domain.transcript import TranscriptRecord, TranscriptSegment
from meeting_intelligence.media.models import MediaSource, MeetingSource
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
    source_path: Path | MeetingSource,
    meeting_id: str,
    settings: Settings,
    transcription_provider: TranscriptionProvider,
    analysis_provider: MeetingAnalysisProvider,
    meeting_sink,
    progress: Callable[[str], None] | None = None,
) -> PipelineResult:
    notify = progress or (lambda _: None)
    if isinstance(source_path, MeetingSource):
        source_media = source_path
        notify(f"Meeting source: {len(source_media.parts)} MP4 parts")
        transcripts = []
        durations = []
        updated_parts = []
        for index, part in enumerate(source_media.parts, start=1):
            notify(f"Part {index}/{len(source_media.parts)}: {part.path.name}")
            prepared = prepare_meeting_media(part.path, Path(settings.work_dir) / meeting_id / f"part_{index:04d}", settings)
            local = transcribe_prepared_audio(prepared, f"{meeting_id}-part_{index:04d}", transcription_provider)
            transcripts.append(local)
            durations.append(prepared.duration_seconds)
            updated_parts.append(part.model_copy(update={"duration_seconds": prepared.duration_seconds}))
        transcript = merge_part_transcripts(transcripts, durations, meeting_id)
        source_media = source_media.model_copy(update={"parts": updated_parts})
        total_duration = sum(durations)
        source_reference = source_media.directory.resolve()
        source_label = source_media.directory.name
    else:
        source = source_path.expanduser().resolve()
        stat = source.stat()
        source_media = MediaSource(path=source, file_name=source.name, size_bytes=stat.st_size, sha256=sha256_file(source))
        notify("[1/7] Preparing audio")
        prepared = prepare_meeting_media(source, Path(settings.work_dir) / meeting_id, settings)
        notify("[1/7] Audio preparation completed")
        notify("[2/7] Starting transcription")
        transcript = transcribe_prepared_audio(prepared, meeting_id, transcription_provider)
        notify("[2/7] Transcription completed")
        total_duration = prepared.duration_seconds
        source_reference = source
        source_label = source.name
    notify("[3/7] Persisting canonical Transcript")
    artifacts = persist_meeting_transcript(transcript, source_media, total_duration, settings)
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
            source_path=str(source_reference),
        ),
    )
    notify("[6/7] meeting-minutes.md persisted")
    notify("[7/7] Writing Google Sheets projection")
    meeting_sink.write(
        analysis,
        SheetsMeetingContext(source_file=source_label, transcript_path=str(artifacts.transcript_json_path.resolve()), minutes_reference=str(minutes_path)),
    )
    notify("[7/7] Google Sheets projection completed")
    return PipelineResult(artifacts=artifacts, analysis=analysis, meeting_minutes_path=minutes_path)


def merge_part_transcripts(transcripts: list[TranscriptRecord], durations: list[float], meeting_id: str) -> TranscriptRecord:
    if len(transcripts) != len(durations) or not transcripts:
        raise ValueError("part transcripts and durations must be non-empty and aligned")
    languages = {transcript.language for transcript in transcripts}
    if len(languages) != 1:
        raise ValueError("all part transcripts must use the same language")
    segments = []
    offset = 0.0
    for part_index, (transcript, duration) in enumerate(zip(transcripts, durations, strict=True), start=1):
        for segment in transcript.segments:
            speaker = f"part_{part_index:04d}:{segment.speaker}" if segment.speaker is not None else None
            segments.append(TranscriptSegment(id=f"seg_{len(segments) + 1:04d}", start=segment.start + offset, end=segment.end + offset, speaker=speaker, text=segment.text))
        offset += duration
    return TranscriptRecord(meeting_id=meeting_id, language=languages.pop(), duration_seconds=sum(durations), segments=segments)
