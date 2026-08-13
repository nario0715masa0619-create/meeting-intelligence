"""Pure projection of a meeting analysis into operational spreadsheet rows."""

from dataclasses import dataclass
from datetime import datetime

from meeting_intelligence.domain.analysis import MeetingAnalysis


HEADERS = {
    "Meetings": ["ミーティングID", "日時", "タイトル", "お相手の名前", "紹介者名", "その人のビジネス", "ショート要約", "議事録", "主要論点", "具体的にギブしてくれる内容", "ギブできる（こちらが紹介できる）人", "元動画", "文字起こし", "処理日時"],
    "Decisions": ["ミーティングID", "決定事項", "ステータス", "Confidence", "Review Required", "Evidence"],
    "Action Items": ["ミーティングID", "アクション", "担当者", "期限", "ステータス", "Confidence", "Review Required", "Evidence"],
    "Open Items": ["ミーティングID", "未決・確認事項", "理由", "Confidence", "Review Required", "Evidence"],
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
    minutes_reference: str = ""


def project_analysis(analysis: MeetingAnalysis, sheet_names: dict[str, str] | None = None, context: SheetsMeetingContext | None = None) -> SheetsProjection:
    names = sheet_names or {name: name for name in HEADERS}
    context = context or SheetsMeetingContext()
    p = analysis.meeting_profile
    rows = {
        names["Meetings"]: [[analysis.meeting_id, context.meeting_started_at.isoformat() if context.meeting_started_at else "", analysis.title or "", _values(p.counterparty_names), _values(p.introducer_names), _values(p.counterparty_businesses), analysis.short_summary, context.minutes_reference, "\n".join(x.title for x in analysis.key_topics), _values(p.gives_from_counterparty), _values(p.people_we_can_introduce), context.source_file, context.transcript_path, analysis.processing.processed_at.isoformat()]],
        names["Decisions"]: [[analysis.meeting_id, x.statement, x.status.value, str(x.confidence), str(x.review_required).lower(), ", ".join(x.evidence_segment_ids)] for x in analysis.decisions],
        names["Action Items"]: [[analysis.meeting_id, x.task, (x.owner.value if x.owner else ""), (x.due_date.isoformat() if x.due_date else ""), x.status, str(x.confidence), str(x.review_required).lower(), ", ".join(x.evidence_segment_ids)] for x in analysis.action_items],
        names["Open Items"]: [[analysis.meeting_id, x.statement, x.reason.value, str(x.confidence), str(x.review_required).lower(), ", ".join(x.evidence_segment_ids)] for x in analysis.open_items],
    }
    return SheetsProjection(rows=rows)
