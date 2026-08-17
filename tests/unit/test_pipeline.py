from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from meeting_intelligence.application import pipeline
from meeting_intelligence.domain.analysis import AnalysisProcessing, MeetingAnalysis
from meeting_intelligence.domain.meeting import Quality, QualityStatus
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.media.models import MeetingSource, MeetingSourcePart, PreparedAudio
from meeting_intelligence.output.transcript import TranscriptArtifacts


def test_pipeline_preserves_phase_order_and_traceability(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"source")
    transcript = TranscriptRecord(meeting_id="m1", language="ja", duration_seconds=1, segments=[])
    prepared = PreparedAudio(source_path=source, audio_path=tmp_path / "audio.mp3", duration_seconds=1, size_bytes=1, format="mp3", sha256="a" * 64)
    (tmp_path / "output").mkdir()
    artifacts = TranscriptArtifacts(tmp_path / "output", tmp_path / "output/transcript.json", tmp_path / "output/transcript.md", tmp_path / "output/metadata.json")
    analysis = MeetingAnalysis(meeting_id="m1", quality=Quality(status=QualityStatus.PASS, review_required=False), processing=AnalysisProcessing(processed_at=datetime.now(timezone.utc), provider="fake", model="fake", prompt_version="test"))
    calls = []
    monkeypatch.setattr(pipeline, "sha256_file", lambda _: "b" * 64)
    monkeypatch.setattr(pipeline, "prepare_meeting_media", lambda *args: calls.append("media") or prepared)
    monkeypatch.setattr(pipeline, "transcribe_prepared_audio", lambda *args: calls.append("transcription") or transcript)
    monkeypatch.setattr(pipeline, "persist_meeting_transcript", lambda *args: calls.append("persistence") or artifacts)

    class Provider:
        def analyze(self, value):
            calls.append("analysis")
            assert value is transcript
            return analysis

    class Sink:
        def write(self, value, context):
            calls.append("sheets")
            assert value is analysis
            assert context.source_file == "meeting.mp4"
            assert context.transcript_path.endswith("transcript.json")
            assert context.minutes_reference.endswith("meeting-minutes.md")

    settings = SimpleNamespace(work_dir=tmp_path / "work", analysis_evidence_max_attempts=2)
    result = pipeline.run_pipeline(source, "m1", settings, object(), Provider(), Sink())
    assert result.artifacts is artifacts
    assert result.meeting_minutes_path.read_text(encoding="utf-8").startswith("# MTG議事録")
    assert calls == ["media", "transcription", "persistence", "analysis", "sheets"]


def test_multi_part_pipeline_transcribes_parts_but_analyzes_and_writes_sheets_once(tmp_path: Path, monkeypatch) -> None:
    parts = []
    for index in (1, 2):
        path = tmp_path / "meeting" / f"0{index}.mp4"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(str(index).encode())
        parts.append(MeetingSourcePart(sequence=index, path=path, relative_path=f"meeting/0{index}.mp4", size_bytes=1, sha256=str(index) * 64))
    source = MeetingSource.from_parts(tmp_path / "meeting", "meeting", parts)
    prepared = [PreparedAudio(source_path=part.path, audio_path=tmp_path / f"{part.sequence}.mp3", duration_seconds=10, size_bytes=1, format="mp3", sha256="a" * 64) for part in parts]
    artifacts_dir = tmp_path / "output"
    artifacts_dir.mkdir()
    artifacts = TranscriptArtifacts(artifacts_dir, artifacts_dir / "transcript.json", artifacts_dir / "transcript.md", artifacts_dir / "metadata.json")
    result_analysis = MeetingAnalysis(meeting_id="m1", quality=Quality(status=QualityStatus.PASS, review_required=False), processing=AnalysisProcessing(processed_at=datetime.now(timezone.utc), provider="fake", model="fake", prompt_version="test"))
    calls = []
    monkeypatch.setattr(pipeline, "prepare_meeting_media", lambda path, *args: calls.append(("media", path.name)) or prepared[len([call for call in calls if call[0] == "media"]) - 1])
    monkeypatch.setattr(pipeline, "transcribe_prepared_audio", lambda value, meeting_id, provider: calls.append(("transcription", meeting_id)) or TranscriptRecord(meeting_id=meeting_id, language="ja", duration_seconds=10, segments=[]))
    monkeypatch.setattr(pipeline, "persist_meeting_transcript", lambda *args: calls.append(("persistence", len(args[1].parts))) or artifacts)
    monkeypatch.setattr(pipeline, "analyze_transcript", lambda *args, **kwargs: calls.append(("analysis", args[0].duration_seconds)) or result_analysis)
    monkeypatch.setattr(pipeline, "persist_meeting_minutes", lambda *args: artifacts_dir / "meeting-minutes.md")
    class Sink:
        def write(self, *args): calls.append(("sheets", args[0].meeting_id))
    settings = SimpleNamespace(work_dir=tmp_path / "work", analysis_evidence_max_attempts=2)
    pipeline.run_pipeline(source, "m1", settings, object(), object(), Sink())
    assert [call[0] for call in calls].count("transcription") == 2
    assert [call[0] for call in calls].count("analysis") == 1
    assert [call[0] for call in calls].count("sheets") == 1
