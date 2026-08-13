"""Provider-independent structured Meeting Understanding models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from meeting_intelligence.domain.meeting import (
    ActionItem,
    Decision,
    OpenItem,
    Quality,
    Summary,
    Topic,
)


class AnalysisModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceBackedValue(AnalysisModel):
    value: str = Field(min_length=1)
    evidence_segment_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    review_required: bool


class MeetingProfile(AnalysisModel):
    counterparty_names: list[EvidenceBackedValue] = Field(default_factory=list)
    introducer_names: list[EvidenceBackedValue] = Field(default_factory=list)
    counterparty_businesses: list[EvidenceBackedValue] = Field(default_factory=list)
    gives_from_counterparty: list[EvidenceBackedValue] = Field(default_factory=list)
    people_we_can_introduce: list[EvidenceBackedValue] = Field(default_factory=list)


class MeetingAnalysisPayload(AnalysisModel):
    title: str | None = None
    title_generated: bool = False
    short_summary: str = ""
    full_meeting_minutes: str = ""
    meeting_profile: MeetingProfile = Field(default_factory=MeetingProfile)
    summary: Summary = Field(default_factory=Summary)
    key_topics: list[Topic] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    open_items: list[OpenItem] = Field(default_factory=list)
    quality: Quality

    @model_validator(mode="after")
    def generated_title_requires_title(self) -> "MeetingAnalysisPayload":
        if self.title_generated and not self.title:
            raise ValueError("title_generated requires a title")
        return self


class AnalysisProcessing(AnalysisModel):
    processed_at: datetime
    provider: str
    model: str
    prompt_version: str


class MeetingAnalysis(MeetingAnalysisPayload):
    meeting_id: str = Field(min_length=1)
    processing: AnalysisProcessing
