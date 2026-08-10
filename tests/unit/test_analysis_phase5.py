from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from meeting_intelligence.analysis.openai import OpenAIAnalysisConfig, OpenAIAnalysisProvider
from meeting_intelligence.analysis.validation import validate_analysis_evidence
from meeting_intelligence.domain.analysis import AnalysisProcessing, EvidenceBackedValue, MeetingAnalysis, MeetingAnalysisPayload, MeetingProfile
from meeting_intelligence.domain.errors import AnalysisResponseError, DuplicateMeetingError, EvidenceValidationError
from meeting_intelligence.domain.meeting import Decision, DecisionStatus, Quality, QualityStatus, Summary
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.sheets.google import GoogleSheetsConfig, GoogleSheetsMeetingSink
from meeting_intelligence.sheets.projection import project_analysis


def transcript():
    return TranscriptRecord(meeting_id="m1", language="ja", duration_seconds=2, segments=[{"id":"s1","start":0,"end":2,"speaker":"話者A","text":"導入します"}])


def payload():
    return MeetingAnalysisPayload(title="打合せ", meeting_profile=MeetingProfile(counterparty_names=[EvidenceBackedValue(value="山田", evidence_segment_ids=["s1"], confidence=.9, review_required=False)]), summary=Summary(overview="概要"), decisions=[Decision(id="d1", statement="実施", status=DecisionStatus.CONFIRMED, evidence_segment_ids=["s1"], confidence=.9, review_required=False)], quality=Quality(status=QualityStatus.PASS, review_required=False))


def analysis():
    return MeetingAnalysis(meeting_id="m1", **payload().model_dump(), processing=AnalysisProcessing(processed_at=datetime.now(timezone.utc), provider="openai", model="gpt-5.6-terra", prompt_version="0.1.0"))


class Parse:
    def __init__(self, result): self.result = result; self.kwargs = None
    def parse(self, **kwargs): self.kwargs = kwargs; return SimpleNamespace(output_parsed=self.result)


def test_openai_adapter_uses_structured_responses_and_low_reasoning():
    parse = Parse(payload())
    result = OpenAIAnalysisProvider(config=OpenAIAnalysisConfig(), client=SimpleNamespace(responses=parse)).analyze(transcript())
    assert result.meeting_id == "m1"
    assert parse.kwargs["model"] == "gpt-5.6-terra"
    assert parse.kwargs["reasoning"] == {"effort": "low"}
    assert parse.kwargs["text_format"] is MeetingAnalysisPayload


def test_openai_adapter_rejects_missing_structured_output():
    with pytest.raises(AnalysisResponseError):
        OpenAIAnalysisProvider(client=SimpleNamespace(responses=Parse(None))).analyze(transcript())


def test_evidence_validation_accepts_known_evidence_and_rejects_unknown():
    assert validate_analysis_evidence(analysis(), transcript()).meeting_id == "m1"
    changed = analysis().model_copy(deep=True)
    changed.decisions[0].evidence_segment_ids = ["missing"]
    with pytest.raises(EvidenceValidationError): validate_analysis_evidence(changed, transcript())


def test_projection_preserves_unicode_and_profile_values():
    row = project_analysis(analysis()).rows["Meetings"][0]
    assert "打合せ" in row and "山田" in row


class Request:
    def __init__(self, value): self.value = value
    def execute(self): return self.value


class Values:
    def __init__(self, duplicate=False): self.duplicate = duplicate
    def get(self, **kwargs):
        if "A:A" in kwargs["range"]: return Request({"values": [["meeting_id"], ["m1"]] if self.duplicate else [["meeting_id"]]})
        return Request({"values": []})


class Spreadsheets:
    def __init__(self, duplicate=False): self.values_api=Values(duplicate); self.bodies=[]
    def get(self, **kwargs): return Request({"sheets": [{"properties":{"title":n,"sheetId":i}} for i,n in enumerate(["Meetings","Decisions","Action Items","Open Items"],1)]})
    def values(self): return self.values_api
    def batchUpdate(self, **kwargs): self.bodies.append(kwargs["body"]); return Request({})


class Service:
    def __init__(self, duplicate=False): self.api=Spreadsheets(duplicate)
    def spreadsheets(self): return self.api


def test_google_sink_uses_one_atomic_string_only_data_batch():
    service=Service()
    GoogleSheetsMeetingSink(GoogleSheetsConfig("sheet"), service).write(analysis())
    data = service.api.bodies[-1]
    assert all("appendCells" in r for r in data["requests"])
    assert "formulaValue" not in str(data)
    assert data["requests"][-1]["appendCells"]["sheetId"] == 1


def test_google_sink_duplicate_performs_no_writes():
    service=Service(True)
    with pytest.raises(DuplicateMeetingError): GoogleSheetsMeetingSink(GoogleSheetsConfig("sheet"), service).write(analysis())
    assert service.api.bodies == []
