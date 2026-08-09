import pytest
from pydantic import ValidationError
from meeting_intelligence.domain.transcript import TranscriptRecord, TranscriptSegment


def record(**updates: object) -> TranscriptRecord:
    data = {"meeting_id": "m1", "language": "ja", "duration_seconds": 10, "segments": [{"id": "s1", "start": 0, "end": 1, "speaker": None, "text": "こんにちは"}]}
    data.update(updates)
    return TranscriptRecord.model_validate(data)


def test_valid_null_speaker_and_empty_segments() -> None:
    assert record().segments[0].speaker is None
    assert record(segments=[]).segments == []


@pytest.mark.parametrize("start,end", [(-1, 1), (2, 1)])
def test_invalid_timestamps(start: float, end: float) -> None:
    with pytest.raises(ValidationError):
        TranscriptSegment(id="s", start=start, end=end, speaker=None, text="x")


def test_negative_duration_and_schema_version_fail() -> None:
    with pytest.raises(ValidationError):
        record(duration_seconds=-1)
    with pytest.raises(ValidationError):
        record(schema_version="9.9.9")


def test_japanese_json_roundtrip_and_schema_generation() -> None:
    original = record()
    encoded = original.model_dump_json()
    assert "こんにちは" in encoded
    assert TranscriptRecord.model_validate_json(encoded) == original
    assert TranscriptRecord.model_json_schema()["type"] == "object"

