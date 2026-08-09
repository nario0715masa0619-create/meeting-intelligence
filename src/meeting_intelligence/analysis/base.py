from typing import Protocol
from meeting_intelligence.domain.meeting import MeetingRecord
from meeting_intelligence.domain.transcript import TranscriptRecord


class AnalysisProvider(Protocol):
    def analyze(self, transcript: TranscriptRecord) -> MeetingRecord:
        ...
