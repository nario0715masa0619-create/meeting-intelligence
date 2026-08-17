import json
import os
from pathlib import Path

from meeting_intelligence.application.inbox import run_inbox
from meeting_intelligence.media.tools import sha256_file


def test_fake_new_processing_then_second_run_skips_without_provider_calls(tmp_path: Path) -> None:
    inbox, output, work = tmp_path / "inbox", tmp_path / "output", tmp_path / "work"
    inbox.mkdir()
    source = inbox / "日本語 meeting.mp4"
    source.write_bytes(b"synthetic-video")
    os.utime(source, (1, 1))
    calls = []

    def fake_pipeline(source, meeting_id: str) -> None:
        calls.append((source, meeting_id))
        path = source.parts[0].path
        directory = output / meeting_id
        directory.mkdir(parents=True)
        (directory / "transcript.json").write_text("{}", encoding="utf-8")
        (directory / "transcript.md").write_text("transcript", encoding="utf-8")
        (directory / "meeting-minutes.md").write_text("minutes", encoding="utf-8")
        (directory / "metadata.json").write_text(json.dumps({"media": {"source_path": str(path.resolve()), "source_sha256": sha256_file(path)}}), encoding="utf-8")

    first = run_inbox(inbox, output, work, stable_age_seconds=0, dry_run=False, continue_on_failure=True, process_new=fake_pipeline)
    assert first.processed == 1 and len(calls) == 1
    second = run_inbox(inbox, output, work, stable_age_seconds=0, dry_run=False, continue_on_failure=True, process_new=lambda *_: calls.append("unexpected"), sheet_contains=lambda _: True)
    assert second.skipped == 1 and len(calls) == 1
