from pathlib import Path

import pytest

from meeting_intelligence.domain.errors import OutputExistsError, OutputWriteError
from meeting_intelligence.output.meeting_minutes import MeetingMinutesContext, persist_meeting_minutes, render_meeting_minutes
from test_phase7_sheets import analysis


def test_renderer_contains_all_sections_unicode_multiline_and_traceability(tmp_path: Path) -> None:
    rendered = render_meeting_minutes(
        analysis(),
        MeetingMinutesContext(
            transcript_path=tmp_path / "transcript.json",
            source_path="D:/日本語/会議.mp4",
            meeting_started_at="2026-08-09T11:31:36+09:00",
        ),
    )
    for heading in ("# MTG議事録", "## 基本情報", "## ショート要約", "## MTG全体の議事録", "## 主要論点", "## 決定事項", "## アクション項目", "## 未決事項・確認事項", "## Give / Get", "## Traceability"):
        assert heading in rendered
    assert "要約1\n要約2" in rendered
    assert "■ 1. 序盤\n内容" in rendered
    assert "日本語/会議.mp4" in rendered


def test_renderer_uses_none_consistently_for_empty_values(tmp_path: Path) -> None:
    value = analysis().model_copy(update={"title": None, "short_summary": "", "full_meeting_minutes": "", "key_topics": [], "decisions": [], "action_items": [], "open_items": []})
    rendered = render_meeting_minutes(value, MeetingMinutesContext(transcript_path=tmp_path / "transcript.json"))
    assert rendered.count("なし") >= 8


def test_persistence_is_utf8_new_only_and_preserves_transcript_artifacts(tmp_path: Path) -> None:
    tracked = {}
    for name in ("transcript.json", "transcript.md", "metadata.json"):
        path = tmp_path / name
        path.write_bytes(f"unchanged-{name}".encode())
        tracked[name] = path.read_bytes()
    target = persist_meeting_minutes(analysis(), tmp_path, MeetingMinutesContext(transcript_path=tmp_path / "transcript.json"))
    assert target.read_bytes().decode("utf-8").startswith("# MTG議事録")
    assert {name: (tmp_path / name).read_bytes() for name in tracked} == tracked
    with pytest.raises(OutputExistsError):
        persist_meeting_minutes(analysis(), tmp_path, MeetingMinutesContext(transcript_path=tmp_path / "transcript.json"))
    assert not list(tmp_path.glob(".meeting-minutes.*.tmp"))


def test_atomic_temp_is_cleaned_when_publish_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "rename", lambda self, target: (_ for _ in ()).throw(OSError("publish failed")))
    with pytest.raises(OutputWriteError):
        persist_meeting_minutes(analysis(), tmp_path, MeetingMinutesContext(transcript_path=tmp_path / "transcript.json"))
    assert not list(tmp_path.glob(".meeting-minutes.*.tmp"))
