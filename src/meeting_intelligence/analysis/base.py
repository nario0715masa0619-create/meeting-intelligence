from typing import Protocol
from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.domain.transcript import TranscriptRecord


class MeetingAnalysisProvider(Protocol):
    def analyze(
        self,
        transcript: TranscriptRecord,
        *,
        validation_feedback: str | None = None,
    ) -> MeetingAnalysis:
        ...


AnalysisProvider = MeetingAnalysisProvider
