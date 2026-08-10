"""Evidence and review gates for structured meeting analysis."""

from collections.abc import Iterable

from meeting_intelligence.domain.analysis import EvidenceBackedValue, MeetingAnalysis
from meeting_intelligence.domain.errors import EvidenceValidationError
from meeting_intelligence.domain.transcript import TranscriptRecord


def _profile_values(analysis: MeetingAnalysis) -> Iterable[EvidenceBackedValue]:
    profile = analysis.meeting_profile
    for values in (
        profile.counterparty_names,
        profile.introducer_names,
        profile.counterparty_businesses,
        profile.gives_from_counterparty,
        profile.people_we_can_introduce,
    ):
        yield from values


def validate_analysis_evidence(analysis: MeetingAnalysis, transcript: TranscriptRecord) -> MeetingAnalysis:
    if analysis.meeting_id != transcript.meeting_id:
        raise EvidenceValidationError("analysis meeting_id does not match transcript")
    valid_ids = {segment.id for segment in transcript.segments}
    evidence_items = [
        *_profile_values(analysis),
        *analysis.key_topics,
        *analysis.decisions,
        *analysis.action_items,
        *analysis.open_items,
    ]
    for item in evidence_items:
        evidence_ids = item.evidence_segment_ids
        if not evidence_ids:
            raise EvidenceValidationError("an extracted item is missing Evidence")
        if any(segment_id not in valid_ids for segment_id in evidence_ids):
            raise EvidenceValidationError("analysis references an unknown Transcript Segment")
        confidence = getattr(item, "confidence", None)
        if confidence is not None and confidence < 0.6 and not item.review_required:
            raise EvidenceValidationError("low-confidence extraction must require review")
    item_ids: set[str] = set()
    for item in [*analysis.key_topics, *analysis.decisions, *analysis.action_items, *analysis.open_items]:
        if item.id in item_ids:
            raise EvidenceValidationError("analysis contains duplicate item IDs")
        item_ids.add(item.id)
    requires_review = analysis.quality.review_required or any(
        getattr(item, "review_required", False) for item in evidence_items
    )
    if requires_review and not analysis.quality.review_required:
        raise EvidenceValidationError("analysis quality must reflect item-level review requirements")
    return analysis
