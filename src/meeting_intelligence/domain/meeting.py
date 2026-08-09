"""Canonical Meeting Record models."""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DecisionStatus(StrEnum):
    CONFIRMED = "confirmed"
    PROPOSED = "proposed"
    UNCERTAIN = "uncertain"


class OwnerType(StrEnum):
    NAMED = "named"
    SPEAKER = "speaker"


class OpenItemReason(StrEnum):
    DECISION_PENDING = "decision_pending"
    INVESTIGATION_REQUIRED = "investigation_required"
    INFORMATION_MISSING = "information_missing"
    APPROVAL_REQUIRED = "approval_required"
    OPINION_UNRESOLVED = "opinion_unresolved"
    FOLLOW_UP_REQUIRED = "follow_up_required"
    OTHER = "other"


class QualityStatus(StrEnum):
    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    FAILED = "failed"


class Source(CanonicalModel):
    file_name: str
    file_path: str
    sha256: str


class Participant(CanonicalModel):
    id: str = Field(min_length=1)
    display_name: str | None = None


class Meeting(CanonicalModel):
    id: str = Field(min_length=1)
    title: str | None = None
    source: Source
    language: str
    started_at: datetime | None = None
    duration_seconds: float = Field(ge=0)
    participants: list[Participant] = Field(default_factory=list)


class Summary(CanonicalModel):
    overview: str = ""
    key_points: list[str] = Field(default_factory=list)


class Topic(CanonicalModel):
    id: str = Field(min_length=1)
    title: str
    summary: str
    evidence_segment_ids: list[str] = Field(default_factory=list)


class Decision(CanonicalModel):
    id: str = Field(min_length=1)
    statement: str
    status: DecisionStatus
    evidence_segment_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    review_required: bool

    @model_validator(mode="after")
    def confirmed_requires_evidence(self) -> "Decision":
        if self.status is DecisionStatus.CONFIRMED and not self.evidence_segment_ids:
            raise ValueError("confirmed decisions require at least one evidence segment")
        return self


class OwnerReference(CanonicalModel):
    type: OwnerType
    value: str = Field(min_length=1)


class ActionItem(CanonicalModel):
    id: str = Field(min_length=1)
    task: str
    owner: OwnerReference | None = None
    due_date: date | None = None
    status: Literal["open"] = "open"
    evidence_segment_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    review_required: bool


class OpenItem(CanonicalModel):
    id: str = Field(min_length=1)
    statement: str
    reason: OpenItemReason
    evidence_segment_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    review_required: bool


class ProviderMetadata(CanonicalModel):
    provider: str
    model: str


class ProcessingMetadata(CanonicalModel):
    processed_at: datetime
    application_version: str
    transcription: ProviderMetadata
    analysis: ProviderMetadata
    schema_version: Literal["0.1.0"] = "0.1.0"
    prompt_version: str


class QualityWarning(CanonicalModel):
    code: str
    target_id: str | None = None
    message: str


class Quality(CanonicalModel):
    status: QualityStatus
    warnings: list[QualityWarning] = Field(default_factory=list)
    review_required: bool


class MeetingRecord(CanonicalModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    meeting: Meeting
    summary: Summary
    topics: list[Topic] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    open_items: list[OpenItem] = Field(default_factory=list)
    processing: ProcessingMetadata
    quality: Quality
