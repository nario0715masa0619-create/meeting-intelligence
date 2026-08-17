from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

from meeting_intelligence.application.inbox import InboxState, classify_item, discover_meeting_directories, identify_meeting_source, meeting_source_is_stable
from meeting_intelligence.application.pipeline import merge_part_transcripts
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.media.models import MeetingSource, MeetingSourcePart
from meeting_intelligence.output.transcript import ProcessingContext, persist_transcript_record


def write_part(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (1, 1))
    return path


def make_source(root: Path, folder: str, values: list[tuple[str, bytes]]) -> MeetingSource:
    directory = root / folder
    for name, content in values:
        write_part(directory / name, content)
    return identify_meeting_source(directory, root)


def test_three_mp4_in_two_folders_discover_two_meetings_and_order_parts(tmp_path: Path) -> None:
    write_part(tmp_path / "A" / "02.mp4", b"2")
    write_part(tmp_path / "A" / "01.mp4", b"1")
    write_part(tmp_path / "B" / "日本語 meeting.mp4", b"3")
    (tmp_path / "A" / "notes.txt").write_text("ignore")
    assert discover_meeting_directories(tmp_path) == [(tmp_path / "A").resolve(), (tmp_path / "B").resolve()]
    source = identify_meeting_source(tmp_path / "A", tmp_path)
    assert [part.path.name for part in source.parts] == ["01.mp4", "02.mp4"]


def test_composite_identity_changes_for_content_added_or_path_hash_assignment(tmp_path: Path) -> None:
    first = make_source(tmp_path, "A", [("01.mp4", b"one"), ("02.mp4", b"two")])
    same = identify_meeting_source(tmp_path / "A", tmp_path)
    assert same.composite_sha256 == first.composite_sha256
    (tmp_path / "A" / "02.mp4").write_bytes(b"changed")
    changed = identify_meeting_source(tmp_path / "A", tmp_path)
    assert changed.composite_sha256 != first.composite_sha256
    write_part(tmp_path / "A" / "03.mp4", b"three")
    added = identify_meeting_source(tmp_path / "A", tmp_path)
    assert added.composite_sha256 != changed.composite_sha256
    swapped = make_source(tmp_path, "B", [("01.mp4", b"two"), ("02.mp4", b"one")])
    assert swapped.composite_sha256 != first.composite_sha256


def test_timeline_ids_and_speakers_are_global_and_part_scoped() -> None:
    part1 = TranscriptRecord(meeting_id="p1", language="ja", duration_seconds=100, segments=[{"id":"local1","start":90,"end":100,"speaker":"A","text":"前半"}])
    part2 = TranscriptRecord(meeting_id="p2", language="ja", duration_seconds=50, segments=[{"id":"local1","start":10,"end":20,"speaker":"A","text":"後半"}])
    merged = merge_part_transcripts([part1, part2], [100, 50], "meeting")
    assert merged.duration_seconds == 150
    assert [(segment.id, segment.start, segment.end) for segment in merged.segments] == [("seg_0001", 90, 100), ("seg_0002", 110, 120)]
    assert [segment.speaker for segment in merged.segments] == ["part_0001:A", "part_0002:A"]


def test_all_parts_and_folder_must_be_stable(tmp_path: Path) -> None:
    directory = tmp_path / "meeting"
    first = write_part(directory / "01.mp4", b"one")
    second = write_part(directory / "02.mp4", b"two")
    os.utime(directory, (1, 1))
    assert meeting_source_is_stable(directory, 120, 120, now=1000) == (True, "")
    os.utime(second, (950, 950))
    assert meeting_source_is_stable(directory, 120, 120, now=1000)[0] is False
    second.write_bytes(b"")
    os.utime(second, (1, 1))
    assert "zero bytes" in meeting_source_is_stable(directory, 0, 0, now=1000)[1]


def test_completed_single_part_folder_with_late_part_is_blocked(tmp_path: Path) -> None:
    inbox, output = tmp_path / "inbox", tmp_path / "output"
    original = make_source(inbox, "meeting", [("01.mp4", b"one")])
    directory = output / "existing"
    directory.mkdir(parents=True)
    part = original.parts[0]
    (directory / "metadata.json").write_text(json.dumps({"media": {"source_path": str(part.path), "source_sha256": part.sha256}}), encoding="utf-8")
    (directory / "transcript.json").write_text("{}")
    (directory / "transcript.md").write_text("text")
    (directory / "meeting-minutes.md").write_text("minutes")
    write_part(inbox / "meeting" / "02.mp4", b"late")
    changed = identify_meeting_source(inbox / "meeting", inbox)
    assert classify_item(changed, output).state is InboxState.BLOCKED


def test_multi_source_metadata_keeps_each_part_and_composite_identity(tmp_path: Path) -> None:
    source = make_source(tmp_path, "meeting", [("01.mp4", b"one"), ("02.mp4", b"two")])
    source = source.model_copy(update={"parts": [part.model_copy(update={"duration_seconds": float(index * 10)}) for index, part in enumerate(source.parts, start=1)]})
    transcript = TranscriptRecord(meeting_id="m1", language="ja", duration_seconds=30, segments=[])
    context = ProcessingContext(application_version="test", schema_version="0.1.0", transcription_provider="fake", transcription_model="fake", transcription_response_format="fake", transcription_language="ja", processed_at=datetime.now(timezone.utc))
    artifacts = persist_transcript_record(transcript, source, 30, context, tmp_path / "output")
    metadata = json.loads(artifacts.metadata_path.read_text(encoding="utf-8"))
    assert metadata["media"]["source_type"] == "multi"
    assert metadata["media"]["composite_sha256"] == source.composite_sha256
    assert [part["sequence"] for part in metadata["media"]["sources"]] == [1, 2]
    assert metadata["media"]["total_duration_seconds"] == 30
