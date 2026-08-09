from datetime import date, datetime, timezone
import pytest
from pydantic import ValidationError
from meeting_intelligence.domain.meeting import ActionItem, Decision, MeetingRecord, OpenItem, OwnerReference


def record(**updates: object) -> MeetingRecord:
    data = {
        "meeting": {"id": "m1", "title": None, "source": {"file_name": "会議.mp4", "file_path": "C:/会議.mp4", "sha256": "abc"}, "language": "ja", "started_at": None, "duration_seconds": 0, "participants": []},
        "summary": {"overview": "", "key_points": []}, "topics": [], "decisions": [], "action_items": [], "open_items": [],
        "processing": {"processed_at": datetime(2026, 8, 9, tzinfo=timezone.utc), "application_version": "0.1.0", "transcription": {"provider": "openai", "model": "test-stt"}, "analysis": {"provider": "openai", "model": "test-analysis"}, "schema_version": "0.1.0", "prompt_version": "0.1.0"},
        "quality": {"status": "pass", "warnings": [], "review_required": False},
    }
    data.update(updates)
    return MeetingRecord.model_validate(data)


def test_minimum_record_nulls_and_empty_collections() -> None:
    value = record()
    assert value.meeting.title is None and value.meeting.participants == [] and value.decisions == []


def test_decision_evidence_rule() -> None:
    Decision(id="d", statement="決定", status="confirmed", evidence_segment_ids=["s1"], confidence=1, review_required=False)
    with pytest.raises(ValidationError):
        Decision(id="d", statement="決定", status="confirmed", confidence=.9, review_required=True)
    Decision(id="d", statement="提案", status="proposed", confidence=.5, review_required=True)


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_confidence_bounds(confidence: float) -> None:
    Decision(id="d", statement="提案", status="proposed", confidence=confidence, review_required=False)


@pytest.mark.parametrize("confidence", [-.01, 1.01])
def test_invalid_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        Decision(id="d", statement="提案", status="proposed", confidence=confidence, review_required=False)


def test_owner_and_due_date_variants() -> None:
    assert ActionItem(id="a", task="確認", owner=None, due_date=None, confidence=.5, review_required=True).owner is None
    assert OwnerReference(type="named", value="田中").type.value == "named"
    assert OwnerReference(type="speaker", value="speaker_2").type.value == "speaker"
    assert ActionItem(id="a", task="確認", due_date="2026-08-15", confidence=.5, review_required=False).due_date == date(2026, 8, 15)
    with pytest.raises(ValidationError):
        OwnerReference(type="invalid", value="x")


def test_open_item_and_quality_enums() -> None:
    OpenItem(id="o", statement="調査", reason="investigation_required", confidence=.5, review_required=True)
    with pytest.raises(ValidationError):
        OpenItem(id="o", statement="調査", reason="invalid", confidence=.5, review_required=True)
    with pytest.raises(ValidationError):
        record(quality={"status": "invalid", "warnings": [], "review_required": False})


def test_json_roundtrip_dates_enums_japanese_and_schema() -> None:
    original = record(action_items=[{"id": "a", "task": "確認", "owner": None, "due_date": "2026-08-15", "status": "open", "evidence_segment_ids": [], "confidence": .7, "review_required": False}])
    encoded = original.model_dump_json()
    assert "会議.mp4" in encoded and "2026-08-15" in encoded
    assert MeetingRecord.model_validate_json(encoded) == original
    assert MeetingRecord.model_json_schema()["type"] == "object"
