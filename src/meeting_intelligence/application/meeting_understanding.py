"""Validated analysis-to-operational-projection use case."""

from meeting_intelligence.analysis.base import MeetingAnalysisProvider
from meeting_intelligence.analysis.validation import validate_analysis_evidence
from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.sheets.projection import SheetsMeetingContext


class MeetingUnderstandingService:
    def __init__(self, provider: MeetingAnalysisProvider, sink):
        self.provider = provider
        self.sink = sink

    def process(self, transcript: TranscriptRecord, context: SheetsMeetingContext | None = None) -> MeetingAnalysis:
        analysis = validate_analysis_evidence(self.provider.analyze(transcript), transcript)
        self.sink.write(analysis, context)
        return analysis
