"""Evidence and review gates for structured meeting analysis."""

from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.domain.errors import EvidenceValidationError
from meeting_intelligence.domain.transcript import TranscriptRecord


def validate_analysis_evidence(analysis: MeetingAnalysis, transcript: TranscriptRecord) -> MeetingAnalysis:
    if analysis.meeting_id != transcript.meeting_id:
        raise EvidenceValidationError("analysis meeting_id does not match transcript")
    valid_ids = {segment.id for segment in transcript.segments}
    named_evidence_items = []
    for field_name in (
        "counterparty_names",
        "introducer_names",
        "counterparty_businesses",
        "gives_from_counterparty",
        "people_we_can_introduce",
    ):
        named_evidence_items.extend(
            (f"meeting_profile.{field_name}[{index}]", item)
            for index, item in enumerate(getattr(analysis.meeting_profile, field_name))
        )
    for collection_name in ("key_topics", "decisions", "action_items", "open_items"):
        named_evidence_items.extend(
            (getattr(item, "id", f"{collection_name}[{index}]"), item)
            for index, item in enumerate(getattr(analysis, collection_name))
        )
    invalid_ids: set[str] = set()
    affected_items: set[str] = set()
    for item_name, item in named_evidence_items:
        evidence_ids = item.evidence_segment_ids
        if not evidence_ids:
            raise EvidenceValidationError("an extracted item is missing Evidence")
        unknown = {segment_id for segment_id in evidence_ids if segment_id not in valid_ids}
        if unknown:
            invalid_ids.update(unknown)
            affected_items.add(item_name)
    if invalid_ids:
        raise EvidenceValidationError(
            "analysis references unknown Transcript Segments; "
            f"invalid_ids={','.join(sorted(invalid_ids))}; "
            f"affected_items={','.join(sorted(affected_items))}",
            invalid_ids=tuple(sorted(invalid_ids)),
            affected_items=tuple(sorted(affected_items)),
        )
    evidence_items = [item for _, item in named_evidence_items]
    for item in evidence_items:
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
