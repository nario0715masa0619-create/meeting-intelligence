"""Application use case for Provider-independent Meeting Understanding."""

from collections.abc import Callable

from meeting_intelligence.analysis.base import MeetingAnalysisProvider
from meeting_intelligence.analysis.prompt import correction_prompt
from meeting_intelligence.analysis.validation import validate_analysis_evidence
from meeting_intelligence.domain.analysis import MeetingAnalysis
from meeting_intelligence.domain.errors import EvidenceValidationError
from meeting_intelligence.domain.transcript import TranscriptRecord


def analyze_transcript(
    transcript: TranscriptRecord,
    provider: MeetingAnalysisProvider,
    *,
    max_attempts: int = 2,
    progress: Callable[[str], None] | None = None,
) -> MeetingAnalysis:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    notify = progress or (lambda _: None)
    feedback: str | None = None
    for attempt in range(1, max_attempts + 1):
        notify(f"Analyzing meeting (attempt {attempt}/{max_attempts})")
        if feedback is None:
            analysis = provider.analyze(transcript)
        else:
            analysis = provider.analyze(transcript, validation_feedback=feedback)
        notify(f"Validating evidence (attempt {attempt}/{max_attempts})")
        try:
            return validate_analysis_evidence(analysis, transcript)
        except EvidenceValidationError as exc:
            if not exc.invalid_ids or attempt == max_attempts:
                if exc.invalid_ids:
                    raise EvidenceValidationError(
                        f"analysis evidence validation failed after {attempt} attempts; "
                        f"invalid_ids={','.join(exc.invalid_ids)}; "
                        f"affected_items={','.join(exc.affected_items)}",
                        invalid_ids=exc.invalid_ids,
                        affected_items=exc.affected_items,
                        attempts=attempt,
                    ) from exc
                raise
            notify(f"Evidence validation failed; retrying analysis ({attempt + 1}/{max_attempts})")
            feedback = correction_prompt(exc.invalid_ids, exc.affected_items)
    raise AssertionError("analysis attempt loop did not return or raise")
