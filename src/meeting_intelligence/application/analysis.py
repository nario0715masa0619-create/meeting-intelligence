"""Application use case for Provider-independent Meeting Understanding."""

from meeting_intelligence.analysis.base import MeetingAnalysisProvider
from meeting_intelligence.analysis.validation import validate_analysis_evidence
from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.domain.transcript import TranscriptRecord


def analyze_transcript(transcript: TranscriptRecord, provider: MeetingAnalysisProvider) -> MeetingAnalysis:
    return validate_analysis_evidence(provider.analyze(transcript), transcript)
