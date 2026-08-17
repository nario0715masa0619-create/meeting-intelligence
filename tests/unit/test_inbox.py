import json
import os
from pathlib import Path

import pytest

from meeting_intelligence.application.inbox import (
    InboxState,
    SourceIdentity,
    classify_item,
    discover_mp4,
    inbox_lock,
    infer_meeting_id,
    run_inbox,
    source_is_stable,
)
from meeting_intelligence.domain.errors import ConfigurationError


def mp4(path: Path, content: bytes = b"video") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (1, 1))
    return path


def output_for(root: Path, meeting_id: str, source: Path, source_hash: str, *, minutes: bool = False) -> Path:
    directory = root / meeting_id
    directory.mkdir(parents=True)
    (directory / "transcript.json").write_text("{}", encoding="utf-8")
    (directory / "transcript.md").write_text("transcript", encoding="utf-8")
    (directory / "metadata.json").write_text(json.dumps({"media": {"source_path": str(source.resolve()), "source_sha256": source_hash}}), encoding="utf-8")
    if minutes:
        (directory / "meeting-minutes.md").write_text("minutes", encoding="utf-8")
    return directory


def identity(path: Path, root: Path, digest: str = "a" * 64) -> SourceIdentity:
    return SourceIdentity(path.resolve(), path.resolve().relative_to(root.resolve()).as_posix(), path.stat().st_size, digest)


def test_recursive_discovery_is_unicode_space_safe_and_deterministic(tmp_path: Path) -> None:
    second = mp4(tmp_path / "日本語" / "b file.MP4")
    first = mp4(tmp_path / "a" / "会議.mp4")
    (tmp_path / "ignore.wav").write_bytes(b"x")
    assert discover_mp4(tmp_path) == [first.resolve(), second.resolve()]


def test_stability_and_deterministic_meeting_id(tmp_path: Path) -> None:
    path = mp4(tmp_path / "260809" / "Zoom ミーティング 2026.mp4")
    assert source_is_stable(path, 120, now=1000) == (True, "")
    os.utime(path, (950, 950))
    assert source_is_stable(path, 120, now=1000)[0] is False
    path.write_bytes(b"")
    assert source_is_stable(path, 0, now=1000)[1] == "source is zero bytes"
    value = infer_meeting_id("260809/Zoom ミーティング 2026.mp4", "a" * 64)
    assert value == infer_meeting_id("260809/Zoom ミーティング 2026.mp4", "a" * 64)
    assert "Zoom" in value


def test_state_classification_new_resume_analysis_complete_complete_and_blocked(tmp_path: Path) -> None:
    inbox, output = tmp_path / "inbox", tmp_path / "output"
    source = mp4(inbox / "meeting.mp4")
    item_source = identity(source, inbox)
    assert classify_item(item_source, output).state is InboxState.NEW
    directory = output_for(output, "existing", source, item_source.sha256)
    assert classify_item(item_source, output).state is InboxState.TRANSCRIPT_COMPLETE
    assert classify_item(item_source, output, failed_marker=True).state is InboxState.FAILED_RESUMABLE
    (directory / "meeting-minutes.md").write_text("minutes", encoding="utf-8")
    assert classify_item(item_source, output).state is InboxState.ANALYSIS_COMPLETE
    assert classify_item(item_source, output, sheet_exists=True).state is InboxState.COMPLETE
    (directory / "transcript.md").unlink()
    assert classify_item(item_source, output).state is InboxState.BLOCKED


def test_one_completed_output_wins_over_older_resumable_output_for_same_source(tmp_path: Path) -> None:
    inbox, output = tmp_path / "inbox", tmp_path / "output"
    source = mp4(inbox / "meeting.mp4")
    item_source = identity(source, inbox)
    output_for(output, "older", source, item_source.sha256)
    output_for(output, "completed", source, item_source.sha256, minutes=True)
    item = classify_item(item_source, output, sheet_exists=True)
    assert item.meeting_id == "completed"
    assert item.state is InboxState.COMPLETE


def test_multiple_resumable_outputs_for_same_source_are_blocked(tmp_path: Path) -> None:
    inbox, output = tmp_path / "inbox", tmp_path / "output"
    source = mp4(inbox / "meeting.mp4")
    item_source = identity(source, inbox)
    output_for(output, "first", source, item_source.sha256)
    output_for(output, "second", source, item_source.sha256)
    assert classify_item(item_source, output).state is InboxState.BLOCKED


def test_lock_prevents_second_runner_and_cleans_after_failure(tmp_path: Path) -> None:
    with inbox_lock(tmp_path):
        with pytest.raises(ConfigurationError):
            with inbox_lock(tmp_path):
                pass
    assert not (tmp_path / "inbox.lock").exists()
    with pytest.raises(RuntimeError):
        with inbox_lock(tmp_path):
            raise RuntimeError
    assert not (tmp_path / "inbox.lock").exists()


def test_dry_run_has_no_callbacks_lock_or_manifest(tmp_path: Path) -> None:
    inbox, output, work = tmp_path / "inbox", tmp_path / "output", tmp_path / "work"
    mp4(inbox / "日本語 meeting.mp4")
    calls = []
    summary = run_inbox(inbox, output, work, stable_age_seconds=0, dry_run=True, continue_on_failure=True, process_new=lambda *_: calls.append("process"), resume=lambda *_: calls.append("resume"), sheet_contains=lambda *_: calls.append("sheet") or True)
    assert calls == []
    assert summary.skipped == 1
    assert not work.exists()


def test_sequential_failure_isolation_and_summary(tmp_path: Path) -> None:
    inbox, output, work = tmp_path / "inbox", tmp_path / "output", tmp_path / "work"
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        mp4(inbox / name.removesuffix(".mp4") / name)
    calls = []
    def process(path, meeting_id):
        name = path.parts[0].path.name
        calls.append(name)
        if name == "b.mp4":
            raise RuntimeError("safe failure")
    summary = run_inbox(inbox, output, work, stable_age_seconds=0, dry_run=False, continue_on_failure=True, process_new=process)
    assert calls == ["a.mp4", "b.mp4", "c.mp4"]
    assert summary.processed == 2 and summary.failed == 1
    manifests = list((work / "inbox-runs").glob("*.json"))
    assert len(manifests) == 1
    assert "safe failure" in manifests[0].read_text(encoding="utf-8")


def test_complete_never_calls_processing_and_resume_uses_transcript(tmp_path: Path) -> None:
    inbox, output, work = tmp_path / "inbox", tmp_path / "output", tmp_path / "work"
    source = mp4(inbox / "meeting.mp4")
    from meeting_intelligence.media.tools import sha256_file
    digest = sha256_file(source)
    directory = output_for(output, "m1", source, digest, minutes=True)
    calls = []
    summary = run_inbox(inbox, output, work, stable_age_seconds=0, dry_run=False, continue_on_failure=True, process_new=lambda *_: calls.append("process"), resume=lambda *_: calls.append("resume"), sheet_contains=lambda meeting_id: meeting_id == "m1")
    assert calls == [] and summary.skipped == 1
    (directory / "meeting-minutes.md").unlink()
    summary = run_inbox(inbox, output, work, stable_age_seconds=0, dry_run=False, continue_on_failure=True, process_new=lambda *_: calls.append("process"), resume=lambda path, meeting_id: calls.append((path.name, meeting_id)))
    assert calls == [("transcript.json", "m1")] and summary.resumed == 1
