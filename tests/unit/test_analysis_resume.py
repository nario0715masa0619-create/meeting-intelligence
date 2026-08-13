import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meeting_intelligence.application.analysis import analyze_transcript
from meeting_intelligence.application.resume import load_transcript_record, resume_analysis
from meeting_intelligence.domain.analysis import (
    AnalysisProcessing,
    EvidenceBackedValue,
    MeetingAnalysis,
    MeetingProfile,
)
from meeting_intelligence.domain.errors import EvidenceValidationError, OutputExistsError, OutputValidationError
from meeting_intelligence.domain.meeting import (
    ActionItem,
    Decision,
    DecisionStatus,
    Quality,
    QualityStatus,
)
from meeting_intelligence.domain.transcript import TranscriptRecord


def transcript() -> TranscriptRecord:
    return TranscriptRecord(
        meeting_id="会議-1",
        language="ja",
        duration_seconds=2,
        segments=[
            {"id": "seg_0001", "start": 0, "end": 1, "speaker": "A", "text": "日本語です"},
            {"id": "seg_0002", "start": 1, "end": 2, "speaker": "B", "text": "進めます"},
        ],
    )


def analysis(
    evidence_id: str = "seg_0001",
    *,
    profile: bool = False,
    action: bool = False,
) -> MeetingAnalysis:
    return MeetingAnalysis(
        meeting_id="会議-1",
        meeting_profile=MeetingProfile(
            counterparty_names=[
                EvidenceBackedValue(
                    value="山田",
                    evidence_segment_ids=[evidence_id],
                    confidence=0.9,
                    review_required=False,
                )
            ] if profile else []
        ),
        decisions=[] if action else [
            Decision(
                id="decision_001",
                statement="進める",
                status=DecisionStatus.CONFIRMED,
                evidence_segment_ids=[evidence_id],
                confidence=0.9,
                review_required=False,
            )
        ],
        action_items=[
            ActionItem(
                id="action_001",
                task="進める",
                evidence_segment_ids=[evidence_id],
                confidence=0.9,
                review_required=False,
            )
        ] if action else [],
        quality=Quality(status=QualityStatus.PASS, review_required=False),
        processing=AnalysisProcessing(
            processed_at=datetime.now(timezone.utc),
            provider="fake",
            model="fake",
            prompt_version="test",
        ),
    )


def write_transcript(path: Path, value: TranscriptRecord | dict | str) -> None:
    if isinstance(value, TranscriptRecord):
        path.write_text(value.model_dump_json(), encoding="utf-8")
    elif isinstance(value, dict):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(value, encoding="utf-8")


def test_load_transcript_valid_utf8_and_meeting_id(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    write_transcript(path, transcript())
    loaded = load_transcript_record(path)
    assert loaded.meeting_id == "会議-1"
    assert loaded.segments[0].text == "日本語です"


@pytest.mark.parametrize("case", ["missing", "malformed", "invalid", "duplicate", "empty"])
def test_load_transcript_rejects_invalid_inputs(tmp_path: Path, case: str) -> None:
    path = tmp_path / "transcript.json"
    if case == "malformed":
        write_transcript(path, "{")
    elif case == "invalid":
        write_transcript(path, {"schema_version": "9", "meeting_id": "m1"})
    elif case == "duplicate":
        value = transcript().model_dump(mode="json")
        value["segments"][1]["id"] = "seg_0001"
        write_transcript(path, value)
    elif case == "empty":
        value = transcript().model_copy(update={"segments": []})
        write_transcript(path, value)
    with pytest.raises(OutputValidationError):
        load_transcript_record(path)


class Provider:
    def __init__(self, results: list[MeetingAnalysis]) -> None:
        self.results = results
        self.feedback: list[str | None] = []

    def analyze(self, value, *, validation_feedback=None):
        assert value.meeting_id == "会議-1"
        self.feedback.append(validation_feedback)
        return self.results[len(self.feedback) - 1]


class Sink:
    def __init__(self) -> None:
        self.calls = []

    def write(self, value, context) -> None:
        self.calls.append((value, context))


def test_initial_valid_analysis_does_not_retry() -> None:
    provider = Provider([analysis()])
    assert analyze_transcript(transcript(), provider).meeting_id == "会議-1"
    assert provider.feedback == [None]


@pytest.mark.parametrize(
    "invalid_analysis,affected",
    [
        (analysis("seg_9999", profile=True), "meeting_profile.counterparty_names[0]"),
        (analysis("seg_9999"), "decision_001"),
        (analysis("seg_9999", action=True), "action_001"),
    ],
)
def test_invalid_evidence_retries_with_bounded_correction(invalid_analysis, affected) -> None:
    provider = Provider([invalid_analysis, analysis()])
    result = analyze_transcript(transcript(), provider)
    assert result.meeting_id == "会議-1"
    assert len(provider.feedback) == 2
    feedback = provider.feedback[1]
    assert feedback is not None
    assert "seg_9999" in feedback
    assert affected in feedback
    assert "Regenerate the COMPLETE analysis" in feedback
    assert "explicitly present" in feedback


def test_second_invalid_attempt_fails_and_reports_details() -> None:
    provider = Provider([analysis("seg_9999"), analysis("seg_8888")])
    with pytest.raises(EvidenceValidationError) as captured:
        analyze_transcript(transcript(), provider)
    assert captured.value.attempts == 2
    assert captured.value.invalid_ids == ("seg_8888",)
    assert captured.value.affected_items == ("decision_001",)
    assert len(provider.feedback) == 2


def test_resume_writes_only_after_valid_retry_and_preserves_transcript(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    write_transcript(path, transcript())
    before = path.read_bytes()
    sink = Sink()
    provider = Provider([analysis("seg_9999"), analysis()])
    result = resume_analysis(path, provider, sink, expected_meeting_id="会議-1")
    assert result.analysis.meeting_id == "会議-1"
    assert len(sink.calls) == 1
    assert sink.calls[0][1].minutes_reference.endswith("meeting-minutes.md")
    assert result.meeting_minutes_path.is_file()
    assert path.read_bytes() == before


def test_resume_uses_metadata_source_reference_without_rewriting_artifacts(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    write_transcript(path, transcript())
    metadata = tmp_path / "metadata.json"
    metadata.write_text('{"media":{"source_path":"D:/meeting.mp4"}}', encoding="utf-8")
    sink = Sink()
    resume_analysis(path, Provider([analysis()]), sink)
    assert sink.calls[0][1].source_file == "D:/meeting.mp4"
    assert metadata.read_text(encoding="utf-8") == '{"media":{"source_path":"D:/meeting.mp4"}}'


def test_resume_never_writes_when_retry_fails(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    write_transcript(path, transcript())
    sink = Sink()
    provider = Provider([analysis("seg_9999"), analysis("seg_8888")])
    with pytest.raises(EvidenceValidationError):
        resume_analysis(path, provider, sink)
    assert sink.calls == []


def test_resume_rejects_explicit_meeting_id_mismatch_before_analysis(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    write_transcript(path, transcript())
    provider = Provider([analysis()])
    with pytest.raises(OutputValidationError):
        resume_analysis(path, provider, Sink(), expected_meeting_id="other")
    assert provider.feedback == []


def test_resume_does_not_overwrite_existing_minutes_or_write_sheets(tmp_path: Path) -> None:
    path = tmp_path / "transcript.json"
    write_transcript(path, transcript())
    minutes = tmp_path / "meeting-minutes.md"
    minutes.write_text("existing", encoding="utf-8")
    sink = Sink()
    with pytest.raises(OutputExistsError):
        resume_analysis(path, Provider([analysis()]), sink)
    assert minutes.read_text(encoding="utf-8") == "existing"
    assert sink.calls == []
