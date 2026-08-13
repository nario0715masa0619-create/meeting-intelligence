from datetime import datetime, timezone

import pytest

from meeting_intelligence.domain.analysis import AnalysisProcessing, EvidenceBackedValue, MeetingAnalysis, MeetingProfile
from meeting_intelligence.domain.errors import GoogleSheetsSchemaError
from meeting_intelligence.domain.meeting import ActionItem, Decision, DecisionStatus, OpenItem, OpenItemReason, Quality, QualityStatus, Topic
from meeting_intelligence.sheets.google import GoogleSheetsConfig, GoogleSheetsMeetingSink
from meeting_intelligence.sheets.projection import HEADERS, SheetsMeetingContext, project_analysis


def analysis():
    evidence = ["seg_0001"]
    return MeetingAnalysis(
        meeting_id="m1", title="タイトル", short_summary="要約1\n要約2", full_meeting_minutes="■ 1. 序盤\n内容\n\n■ 2. 終盤\n内容",
        meeting_profile=MeetingProfile(counterparty_names=[EvidenceBackedValue(value="山田", evidence_segment_ids=evidence, confidence=.9, review_required=False)]),
        key_topics=[Topic(id="t1", title="論点1", summary="", evidence_segment_ids=evidence), Topic(id="t2", title="論点2", summary="", evidence_segment_ids=evidence)],
        decisions=[Decision(id="d1", statement="決定", status=DecisionStatus.CONFIRMED, evidence_segment_ids=evidence, confidence=.9, review_required=False)],
        action_items=[ActionItem(id="a1", task="実行", evidence_segment_ids=evidence, confidence=.8, review_required=False)],
        open_items=[OpenItem(id="o1", statement="確認", reason=OpenItemReason.FOLLOW_UP_REQUIRED, evidence_segment_ids=evidence, confidence=.7, review_required=False)],
        quality=Quality(status=QualityStatus.PASS, review_required=False),
        processing=AnalysisProcessing(processed_at=datetime.now(timezone.utc), provider="fake", model="fake", prompt_version="test"),
    )


def test_formal_headers_and_projection_have_no_cross_sheet_duplication():
    assert HEADERS["Meetings"] == ["ミーティングID", "日時", "タイトル", "お相手の名前", "紹介者名", "その人のビジネス", "ショート要約", "議事録", "主要論点", "具体的にギブしてくれる内容", "ギブできる（こちらが紹介できる）人", "元動画", "文字起こし", "処理日時"]
    assert HEADERS["Decisions"] == ["ミーティングID", "決定事項", "ステータス", "Confidence", "Review Required", "Evidence"]
    assert HEADERS["Action Items"] == ["ミーティングID", "アクション", "担当者", "期限", "ステータス", "Confidence", "Review Required", "Evidence"]
    assert HEADERS["Open Items"] == ["ミーティングID", "未決・確認事項", "理由", "Confidence", "Review Required", "Evidence"]
    projection = project_analysis(analysis(), context=SheetsMeetingContext(source_file="source.mp4", transcript_path="transcript.json", minutes_reference="output/m1/meeting-minutes.md"))
    meeting = projection.rows["Meetings"][0]
    assert meeting[6] == "要約1\n要約2" and meeting[7] == "output/m1/meeting-minutes.md" and meeting[8] == "論点1\n論点2"
    assert analysis().full_meeting_minutes not in meeting
    assert meeting[11:13] == ["source.mp4", "transcript.json"]
    assert "決定" not in meeting and "実行" not in meeting and "確認" not in meeting
    assert projection.rows["Decisions"][0] == ["m1", "決定", "confirmed", "0.9", "false", "seg_0001"]
    assert "d1" not in projection.rows["Decisions"][0]
    assert "山田" not in projection.rows["Decisions"][0] + projection.rows["Action Items"][0] + projection.rows["Open Items"][0]


class Request:
    def __init__(self, value): self.value = value
    def execute(self): return self.value


class Values:
    def __init__(self, rows): self.rows = rows
    def get(self, **kwargs):
        title = kwargs["range"].split("'")[1]
        if "A:A" in kwargs["range"]: return Request({"values": [["ミーティングID"]]})
        return Request({"values": self.rows.get(title, [])})


class Spreadsheets:
    def __init__(self, rows): self.values_api = Values(rows); self.bodies = []
    def get(self, **kwargs): return Request({"sheets": [{"properties": {"title": name, "sheetId": i}} for i, name in enumerate(HEADERS, 1)]})
    def values(self): return self.values_api
    def batchUpdate(self, **kwargs):
        self.bodies.append(kwargs["body"])
        names = {i: name for i, name in enumerate(HEADERS, 1)}
        for request in kwargs["body"]["requests"]:
            if "updateCells" in request:
                update = request["updateCells"]
                self.values_api.rows[names[update["range"]["sheetId"]]] = [[cell.get("userEnteredValue", {}).get("stringValue", "") for cell in update["rows"][0]["values"]]]
        return Request({})


class Service:
    def __init__(self, rows): self.api = Spreadsheets(rows)
    def spreadsheets(self): return self.api


def test_empty_legacy_headers_are_safely_replaced():
    service = Service({name: [["legacy_header"]] for name in HEADERS})
    sink = GoogleSheetsMeetingSink(GoogleSheetsConfig("sheet"), service)
    _, columns = sink.initialize_schema()
    assert columns == HEADERS
    assert len(service.api.bodies) == 1


def test_data_rows_block_header_migration_without_write():
    service = Service({"Meetings": [["meeting_id"], ["existing"]], "Decisions": [], "Action Items": [], "Open Items": []})
    sink = GoogleSheetsMeetingSink(GoogleSheetsConfig("sheet"), service)
    with pytest.raises(GoogleSheetsSchemaError): sink.initialize_schema()
    assert service.api.bodies == []


def test_unknown_extra_column_with_data_blocks_destructive_change():
    service = Service({"Meetings": [[*HEADERS["Meetings"], "unknown"], [*[""] * 14, "value"]], "Decisions": [], "Action Items": [], "Open Items": []})
    with pytest.raises(GoogleSheetsSchemaError): GoogleSheetsMeetingSink(GoogleSheetsConfig("sheet"), service).initialize_schema()
    assert service.api.bodies == []
