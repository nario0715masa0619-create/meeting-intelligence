"""OpenAI Responses API adapter for structured meeting understanding."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, OpenAI

from meeting_intelligence.analysis.prompt import ANALYSIS_PROMPT_VERSION, ANALYSIS_SYSTEM_PROMPT
from meeting_intelligence.domain.analysis import AnalysisProcessing, MeetingAnalysis, MeetingAnalysisPayload
from meeting_intelligence.domain.errors import (
    AnalysisAuthenticationError,
    AnalysisProviderError,
    AnalysisResponseError,
)
from meeting_intelligence.domain.transcript import TranscriptRecord


@dataclass(frozen=True)
class OpenAIAnalysisConfig:
    model: str = "gpt-5.6-terra"
    reasoning_effort: str = "low"
    timeout_seconds: float = 300.0
    max_retries: int = 2


class OpenAIAnalysisProvider:
    def __init__(self, *, api_key: str | None = None, config: OpenAIAnalysisConfig | None = None, client: Any = None):
        self.config = config or OpenAIAnalysisConfig()
        if client is None:
            if not api_key:
                raise AnalysisAuthenticationError("OpenAI credentials are not configured")
            client = OpenAI(api_key=api_key, max_retries=self.config.max_retries)
        self.client = client

    def analyze(self, transcript: TranscriptRecord) -> MeetingAnalysis:
        try:
            response = self.client.responses.parse(
                model=self.config.model,
                reasoning={"effort": self.config.reasoning_effort},
                input=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": transcript.model_dump_json()},
                ],
                text_format=MeetingAnalysisPayload,
                timeout=self.config.timeout_seconds,
            )
        except AuthenticationError as exc:
            raise AnalysisAuthenticationError("OpenAI authentication failed") from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise AnalysisProviderError("OpenAI analysis service is unavailable") from exc
        except APIStatusError as exc:
            raise AnalysisProviderError(f"OpenAI analysis request failed with status {exc.status_code}") from exc
        payload = getattr(response, "output_parsed", None)
        if not isinstance(payload, MeetingAnalysisPayload):
            raise AnalysisResponseError("OpenAI returned no valid structured analysis")
        return MeetingAnalysis(
            meeting_id=transcript.meeting_id,
            **payload.model_dump(),
            processing=AnalysisProcessing(
                processed_at=datetime.now(timezone.utc),
                provider="openai",
                model=self.config.model,
                prompt_version=ANALYSIS_PROMPT_VERSION,
            ),
        )
