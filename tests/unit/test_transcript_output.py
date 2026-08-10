import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import meeting_intelligence.output.transcript as output_module
from meeting_intelligence.domain.errors import (
    OutputExistsError,
    OutputValidationError,
    OutputWriteError,
)
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.media.models import MediaSource
from meeting_intelligence.output.transcript import (
    ProcessingContext,
    format_timestamp,
    persist_transcript_record,
    render_transcript_markdown,
    validate_transcript_for_output,
)


def transcript(**updates: object) -> TranscriptRecord:
    value: dict[str, object] = {
        "meeting_id": "日本語 会議",
        "language": "ja",
        "duration_seconds": 3723.5,
        "segments": [
            {"id": "seg_0001", "start": 12.4, "end": 18.1, "speaker": "chunk_0001:A", "text": "ではこの方針で進めましょう。"},
            {"id": "seg_0002", "start": 19.0, "end": 25.5, "speaker": None, "text": "分かりました。"},
        ],
    }
    value.update(updates)
    return TranscriptRecord.model_validate(value)


def source(tmp_path: Path) -> MediaSource:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "元 会議.mp4"
    content = b"original-source"
    path.write_bytes(content)
    return MediaSource(
        path=path,
        file_name=path.name,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def context() -> ProcessingContext:
    return ProcessingContext(
        application_version="0.1.0",
        schema_version="0.1.0",
        prompt_version=None,
        transcription_provider="openai",
        transcription_model="gpt-4o-transcribe-diarize",
        transcription_response_format="diarized_json",
        transcription_language="ja",
        processed_at=datetime(2026, 8, 10, 1, 2, 3, tzinfo=timezone.utc),
    )


def persist(tmp_path: Path, value: TranscriptRecord | None = None):
    media = source(tmp_path)
    original_hash = media.sha256
    artifacts = persist_transcript_record(value or transcript(), media, 3723.5, context(), tmp_path / "output")
    assert hashlib.sha256(media.path.read_bytes()).hexdigest() == original_hash
    return artifacts


def test_persists_canonical_json_japanese_nulls_and_roundtrip(tmp_path: Path) -> None:
    artifacts = persist(tmp_path)
    raw = artifacts.transcript_json_path.read_text(encoding="utf-8")
    assert "ではこの方針" in raw and "\\u3067" not in raw
    restored = TranscriptRecord.model_validate_json(raw)
    assert restored == transcript()
    assert restored.schema_version == "0.1.0"
    assert restored.meeting_id == "日本語 会議"
    assert restored.segments[1].speaker is None
    empty = persist_transcript_record(
        transcript(meeting_id="empty", duration_seconds=0, segments=[]),
        source(tmp_path / "empty-source"), 0, context(), tmp_path / "empty-output",
    )
    assert TranscriptRecord.model_validate_json(empty.transcript_json_path.read_text("utf-8")).segments == []


def test_markdown_is_exact_projection_with_readable_timestamps() -> None:
    rendered = render_transcript_markdown(transcript())
    assert "# Transcript" in rendered
    assert "Duration: 01:02:03.500" in rendered
    assert "[00:00:12.400 - 00:00:18.100] chunk_0001:A" in rendered
    assert "[00:00:19.000 - 00:00:25.500] (speaker unknown)" in rendered
    assert "ではこの方針で進めましょう。" in rendered
    assert format_timestamp(3858.25) == "01:04:18.250"


def test_metadata_traceability_and_artifact_hashes(tmp_path: Path) -> None:
    artifacts = persist(tmp_path)
    metadata = json.loads(artifacts.metadata_path.read_text("utf-8"))
    assert metadata["status"] == "completed"
    assert metadata["processed_at"] == "2026-08-10T01:02:03Z"
    assert metadata["application_version"] == metadata["schema_version"] == "0.1.0"
    assert metadata["prompt_version"] is None
    assert metadata["transcription"] == {
        "provider": "openai", "model": "gpt-4o-transcribe-diarize",
        "response_format": "diarized_json", "language": "ja",
    }
    assert metadata["media"]["source_file_name"] == "元 会議.mp4"
    assert metadata["media"]["source_path"] == metadata["source"]
    for key, path in (("transcript_json", artifacts.transcript_json_path), ("transcript_markdown", artifacts.transcript_markdown_path)):
        assert metadata["artifacts"][key]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("artifact_name", ["transcript.json", "transcript.md", "metadata.json"])
def test_existing_meeting_directory_never_overwritten(tmp_path: Path, artifact_name: str) -> None:
    output = tmp_path / "output"
    directory = output / "日本語 会議"
    directory.mkdir(parents=True)
    existing = directory / artifact_name
    existing.write_text("keep", encoding="utf-8")
    with pytest.raises(OutputExistsError):
        persist_transcript_record(transcript(), source(tmp_path), 3723.5, context(), output)
    assert existing.read_text("utf-8") == "keep"


@pytest.mark.parametrize("meeting_id", ["../escape", "..", "a/b", "a\\b", "C:drive", "bad.", "CON", "NUL.txt"])
def test_unsafe_meeting_id_is_rejected(tmp_path: Path, meeting_id: str) -> None:
    with pytest.raises(OutputValidationError, match="meeting_id"):
        persist_transcript_record(transcript(meeting_id=meeting_id), source(tmp_path), 1, context(), tmp_path / "output")


def test_duplicate_reverse_order_and_duration_contradiction_fail() -> None:
    with pytest.raises(OutputValidationError, match="duplicate"):
        validate_transcript_for_output(transcript(segments=[
            {"id": "same", "start": 0, "end": 1, "speaker": None, "text": "一"},
            {"id": "same", "start": 1, "end": 2, "speaker": None, "text": "二"},
        ]))
    with pytest.raises(OutputValidationError, match="chronological"):
        validate_transcript_for_output(transcript(segments=[
            {"id": "a", "start": 2, "end": 3, "speaker": None, "text": "後"},
            {"id": "b", "start": 0, "end": 1, "speaker": None, "text": "先"},
        ]))
    with pytest.raises(OutputValidationError, match="duration"):
        validate_transcript_for_output(transcript(duration_seconds=1, segments=[
            {"id": "a", "start": 0, "end": 3, "speaker": None, "text": "長い"},
        ]))


def test_partial_write_cleans_staging_and_does_not_finalize_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_write = output_module._write_new
    calls = 0

    def fail_second_write(path: Path, content: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated write failure")
        real_write(path, content)

    monkeypatch.setattr(output_module, "_write_new", fail_second_write)
    output = tmp_path / "output"
    with pytest.raises(OutputWriteError):
        persist_transcript_record(transcript(), source(tmp_path), 3723.5, context(), output)
    assert not (output / "日本語 会議").exists()
    assert list(output.glob("*.tmp")) == []
