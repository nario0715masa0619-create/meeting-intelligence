"""Pure projection of a meeting analysis into operational spreadsheet rows."""

from dataclasses import dataclass
from datetime import datetime

from meeting_intelligence.domain.analysis import MeetingAnalysis


HEADERS = {
    "Meetings": ["meeting_id", "日時", "タイトル", "お相手の名前", "紹介者名", "その人のビジネス", "会議要約", "主要論点", "具体的にギブしてくれる内容", "ギブできる（こちらが紹介できる）人", "source_file", "transcript_path", "processed_at", "review_required"],
    "Decisions": ["meeting_id", "decision_id", "決定事項", "status", "confidence", "review_required", "evidence_segment_ids"],
    "Action Items": ["meeting_id", "action_id", "タスク", "担当者", "期限", "status", "confidence", "review_required", "evidence_segment_ids"],
    "Open Items": ["meeting_id", "open_item_id", "未決事項", "reason", "confidence", "review_required", "evidence_segment_ids"],
}


def _values(items):
    return "\n".join(item.value for item in items)


@dataclass(frozen=True)
class SheetsProjection:
    rows: dict[str, list[list[str]]]


@dataclass(frozen=True)
class SheetsMeetingContext:
    source_file: str = ""
    transcript_path: str = ""
    meeting_started_at: datetime | None = None


def project_analysis(analysis: MeetingAnalysis, sheet_names: dict[str, str] | None = None, context: SheetsMeetingContext | None = None) -> SheetsProjection:
    names = sheet_names or {name: name for name in HEADERS}
    context = context or SheetsMeetingContext()
    p = analysis.meeting_profile
    summary = analysis.summary.overview or "\n".join(analysis.summary.key_points)
    rows = {
        names["Meetings"]: [[analysis.meeting_id, context.meeting_started_at.isoformat() if context.meeting_started_at else "", analysis.title or "", _values(p.counterparty_names), _values(p.introducer_names), _values(p.counterparty_businesses), summary, "\n".join(x.title for x in analysis.key_topics), _values(p.gives_from_counterparty), _values(p.people_we_can_introduce), context.source_file, context.transcript_path, analysis.processing.processed_at.isoformat(), str(analysis.quality.review_required).lower()]],
        names["Decisions"]: [[analysis.meeting_id, x.id, x.statement, x.status.value, str(x.confidence), str(x.review_required).lower(), ", ".join(x.evidence_segment_ids)] for x in analysis.decisions],
        names["Action Items"]: [[analysis.meeting_id, x.id, x.task, (x.owner.value if x.owner else ""), (x.due_date.isoformat() if x.due_date else ""), x.status, str(x.confidence), str(x.review_required).lower(), ", ".join(x.evidence_segment_ids)] for x in analysis.action_items],
        names["Open Items"]: [[analysis.meeting_id, x.id, x.statement, x.reason.value, str(x.confidence), str(x.review_required).lower(), ", ".join(x.evidence_segment_ids)] for x in analysis.open_items],
    }
    return SheetsProjection(rows=rows)
