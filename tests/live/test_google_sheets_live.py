"""Explicit opt-in acceptance test for the production Google Sheets sink."""

from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from meeting_intelligence.config.settings import Settings
from meeting_intelligence.domain.analysis import AnalysisProcessing, EvidenceBackedValue, MeetingAnalysis, MeetingProfile
from meeting_intelligence.domain.errors import DuplicateMeetingError
from meeting_intelligence.domain.meeting import ActionItem, Decision, DecisionStatus, OpenItem, OpenItemReason, OwnerReference, OwnerType, Quality, QualityStatus, Summary, Topic
from meeting_intelligence.sheets.google import GoogleSheetsConfig, GoogleSheetsMeetingSink
from meeting_intelligence.sheets.projection import HEADERS, SheetsMeetingContext


pytestmark = [pytest.mark.live, pytest.mark.google_sheets_live]
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _configured_path(path: Path | None) -> Path:
    if path is None or str(path) in ("", "."):
        pytest.skip("GOOGLE_SERVICE_ACCOUNT_FILE is not set")
    resolved = path.expanduser()
    if not resolved.is_absolute():
        resolved = REPOSITORY_ROOT / resolved
    if not resolved.is_file():
        pytest.skip("GOOGLE_SERVICE_ACCOUNT_FILE does not identify a file")
    return resolved


def _row_by_id(service, spreadsheet_id: str, sheet_name: str, meeting_id: str) -> tuple[list[str], list[str]]:
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A:Z",
        valueRenderOption="FORMULA",
    ).execute()
    values = result.get("values", [])
    assert values, f"{sheet_name} is empty after the acceptance write"
    matches = [row for row in values[1:] if row and row[0] == meeting_id]
    assert len(matches) == 1
    return values[0], matches[0]


def _value(headers: list[str], row: list[str], name: str) -> str:
    index = headers.index(name)
    return row[index] if index < len(row) else ""


def test_google_sheets_operational_projection_live_acceptance() -> None:
    settings = Settings(_env_file=REPOSITORY_ROOT / ".env")
    spreadsheet_id = settings.google_sheets_spreadsheet_id.strip()
    if not spreadsheet_id:
        pytest.skip("GOOGLE_SHEETS_SPREADSHEET_ID is not set")
    credential_file = _configured_path(settings.google_service_account_file)
    config = GoogleSheetsConfig(
        spreadsheet_id=spreadsheet_id,
        service_account_file=credential_file,
        meetings_sheet=settings.google_meetings_sheet,
        decisions_sheet=settings.google_decisions_sheet,
        action_items_sheet=settings.google_action_items_sheet,
        open_items_sheet=settings.google_open_items_sheet,
    )
    meeting_id = f"live_acceptance_{uuid4().hex}"
    evidence = ["seg_live_001"]
    analysis = MeetingAnalysis(
        meeting_id=meeting_id,
        title="Google Sheets Live Acceptance",
        title_generated=True,
        meeting_profile=MeetingProfile(
            counterparty_names=[EvidenceBackedValue(value="山田太郎", evidence_segment_ids=evidence, confidence=1, review_required=False)],
            introducer_names=[EvidenceBackedValue(value="佐藤花子", evidence_segment_ids=evidence, confidence=1, review_required=False)],
            counterparty_businesses=[EvidenceBackedValue(value="法人向けAI研修事業", evidence_segment_ids=evidence, confidence=1, review_required=False)],
            gives_from_counterparty=[EvidenceBackedValue(value="AI導入を検討している経営者を3人紹介できる", evidence_segment_ids=evidence, confidence=1, review_required=False)],
            people_we_can_introduce=[EvidenceBackedValue(value="SNSマーケティングに強い経営者を紹介できる", evidence_segment_ids=evidence, confidence=1, review_required=False)],
        ),
        summary=Summary(overview="=LIVE_ACCEPTANCE_TEXT", key_points=["日本語の書込み確認"]),
        key_topics=[Topic(id="topic_live_001", title="AI研修", summary="法人向け研修", evidence_segment_ids=evidence)],
        decisions=[Decision(id="decision_live_001", statement="テストSpreadsheetへ登録する", status=DecisionStatus.CONFIRMED, evidence_segment_ids=evidence, confidence=1, review_required=False)],
        action_items=[ActionItem(id="action_live_001", task="山田太郎へ資料を送る", owner=OwnerReference(type=OwnerType.NAMED, value="担当者A"), due_date=date(2030, 1, 2), evidence_segment_ids=evidence, confidence=1, review_required=False)],
        open_items=[OpenItem(id="open_live_001", statement="次回日程を確認する", reason=OpenItemReason.FOLLOW_UP_REQUIRED, evidence_segment_ids=evidence, confidence=1, review_required=False)],
        quality=Quality(status=QualityStatus.PASS, review_required=False),
        processing=AnalysisProcessing(processed_at=datetime.now(timezone.utc), provider="acceptance-fixture", model="none", prompt_version="acceptance-v1"),
    )
    context = SheetsMeetingContext(source_file="live-acceptance-source.mp4", transcript_path="output/live-acceptance/transcript.json")
    sink = GoogleSheetsMeetingSink(config)
    sink.write(analysis, context)

    for canonical, actual in config.names.items():
        headers, row = _row_by_id(sink.service, spreadsheet_id, actual, meeting_id)
        assert all(header in headers for header in HEADERS[canonical])
        assert row

    headers, meeting_row = _row_by_id(sink.service, spreadsheet_id, config.meetings_sheet, meeting_id)
    expected_profile = {
        "お相手の名前": "山田太郎",
        "紹介者名": "佐藤花子",
        "その人のビジネス": "法人向けAI研修事業",
        "具体的にギブしてくれる内容": "AI導入を検討している経営者を3人紹介できる",
        "ギブできる（こちらが紹介できる）人": "SNSマーケティングに強い経営者を紹介できる",
    }
    for header, expected in expected_profile.items():
        assert _value(headers, meeting_row, header) == expected
    assert _value(headers, meeting_row, "会議要約") == "=LIVE_ACCEPTANCE_TEXT"
    assert _value(headers, meeting_row, "source_file") == context.source_file
    assert _value(headers, meeting_row, "transcript_path") == context.transcript_path

    child_expectations = {
        config.decisions_sheet: ("決定事項", "テストSpreadsheetへ登録する"),
        config.action_items_sheet: ("タスク", "山田太郎へ資料を送る"),
        config.open_items_sheet: ("未決事項", "次回日程を確認する"),
    }
    for sheet_name, (column, expected) in child_expectations.items():
        child_headers, child_row = _row_by_id(sink.service, spreadsheet_id, sheet_name, meeting_id)
        assert _value(child_headers, child_row, column) == expected
        assert _value(child_headers, child_row, "evidence_segment_ids") == "seg_live_001"
    action_headers, action_row = _row_by_id(sink.service, spreadsheet_id, config.action_items_sheet, meeting_id)
    assert _value(action_headers, action_row, "担当者") == "担当者A"
    assert _value(action_headers, action_row, "期限") == "2030-01-02"

    with pytest.raises(DuplicateMeetingError):
        sink.write(analysis, context)
