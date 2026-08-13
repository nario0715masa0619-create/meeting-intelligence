"""Deterministic human-readable meeting-minutes artifact."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import uuid

from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.domain.errors import OutputExistsError, OutputWriteError


@dataclass(frozen=True, slots=True)
class MeetingMinutesContext:
    transcript_path: Path
    source_path: str = ""
    meeting_started_at: str = ""


def _text(value: str | None) -> str:
    return value.strip() if value and value.strip() else "なし"


def _list(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values if value.strip()) or "なし"


def render_meeting_minutes(analysis: MeetingAnalysis, context: MeetingMinutesContext) -> str:
    """Render validated analysis without adding facts absent from it."""
    profile = analysis.meeting_profile
    counterparties = [item.value for item in profile.counterparty_names]
    introducers = [item.value for item in profile.introducer_names]
    topics = [f"{item.title}: {item.summary}" if item.summary else item.title for item in analysis.key_topics]
    decisions = [item.statement for item in analysis.decisions]
    actions = [
        " / ".join(
            part
            for part in (
                item.task,
                f"担当: {item.owner.value}" if item.owner else "",
                f"期限: {item.due_date.isoformat()}" if item.due_date else "",
            )
            if part
        )
        for item in analysis.action_items
    ]
    open_items = [item.statement for item in analysis.open_items]
    gives = [item.value for item in profile.gives_from_counterparty]
    can_give = [item.value for item in profile.people_we_can_introduce]
    lines = [
        "# MTG議事録",
        "",
        "## 基本情報",
        "",
        f"- ミーティングID: {analysis.meeting_id}",
        f"- 日時: {_text(context.meeting_started_at)}",
        f"- タイトル: {_text(analysis.title)}",
        f"- お相手: {_text('、'.join(counterparties))}",
        f"- 紹介者: {_text('、'.join(introducers))}",
        "",
        "## ショート要約",
        "",
        _text(analysis.short_summary),
        "",
        "## MTG全体の議事録",
        "",
        _text(analysis.full_meeting_minutes),
        "",
        "## 主要論点",
        "",
        _list(topics),
        "",
        "## 決定事項",
        "",
        _list(decisions),
        "",
        "## アクション項目",
        "",
        _list(actions),
        "",
        "## 未決事項・確認事項",
        "",
        _list(open_items),
        "",
        "## Give / Get",
        "",
        "### 相手からのGive",
        "",
        _list(gives),
        "",
        "### こちらから提供できること",
        "",
        _list(can_give),
        "",
        "## Traceability",
        "",
        f"- Meeting ID: {analysis.meeting_id}",
        f"- Canonical Transcript: {context.transcript_path}",
        f"- Source: {_text(context.source_path)}",
        "",
    ]
    return "\n".join(lines)


def persist_meeting_minutes(
    analysis: MeetingAnalysis,
    output_directory: Path,
    context: MeetingMinutesContext,
) -> Path:
    """Publish meeting-minutes.md atomically and never overwrite it."""
    directory = output_directory.expanduser().resolve()
    target = directory / "meeting-minutes.md"
    if target.exists():
        raise OutputExistsError("meeting-minutes.md already exists; overwrite is not allowed")
    temporary = directory / f".meeting-minutes.{uuid.uuid4().hex}.tmp"
    try:
        content = render_meeting_minutes(analysis, context).encode("utf-8")
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.rename(target)
    except FileExistsError as exc:
        raise OutputExistsError("meeting-minutes.md already exists; overwrite is not allowed") from exc
    except OutputExistsError:
        raise
    except Exception as exc:
        raise OutputWriteError("failed to finalize meeting-minutes.md") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return target
