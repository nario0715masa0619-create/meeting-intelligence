from pathlib import Path
from meeting_intelligence.analysis.base import AnalysisProvider
from meeting_intelligence.domain.meeting import MeetingRecord
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.transcription.base import TranscriptionProvider


class FakeTranscription:
    def transcribe(self, audio_path: Path, meeting_id: str) -> TranscriptRecord:
        return TranscriptRecord(meeting_id=meeting_id, language="ja", duration_seconds=0)


class FakeAnalysis:
    def __init__(self, result: MeetingRecord) -> None:
        self.result = result

    def analyze(self, transcript: TranscriptRecord) -> MeetingRecord:
        return self.result


def accepts_transcription(provider: TranscriptionProvider) -> TranscriptRecord:
    return provider.transcribe(Path("audio.wav"), "m1")


def accepts_analysis(provider: AnalysisProvider, transcript: TranscriptRecord) -> MeetingRecord:
    return provider.analyze(transcript)


def test_fake_transcription_satisfies_contract_without_openai() -> None:
    assert accepts_transcription(FakeTranscription()).meeting_id == "m1"


def test_fake_analysis_satisfies_contract_without_openai() -> None:
    transcript = TranscriptRecord(meeting_id="m1", language="ja", duration_seconds=0)
    expected = MeetingRecord.model_construct()
    assert accepts_analysis(FakeAnalysis(expected), transcript) is expected
    assert "openai" not in FakeAnalysis.__module__
