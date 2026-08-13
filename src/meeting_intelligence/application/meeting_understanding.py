"""Validated analysis-to-operational-projection use case."""

from meeting_intelligence.analysis.base import MeetingAnalysisProvider
from meeting_intelligence.application.analysis import analyze_transcript
from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.sheets.projection import SheetsMeetingContext


class MeetingUnderstandingService:
    def __init__(self, provider: MeetingAnalysisProvider, sink):
        self.provider = provider
        self.sink = sink

    def process(self, transcript: TranscriptRecord, context: SheetsMeetingContext | None = None) -> MeetingAnalysis:
        analysis = analyze_transcript(transcript, self.provider)
        self.sink.write(analysis, context)
        return analysis
