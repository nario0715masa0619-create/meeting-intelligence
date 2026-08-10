"""OpenAI Transcriptions API Adapter for canonical diarized transcripts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import re
from threading import Event, Thread
from time import monotonic

from openai import (
    APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError,
    OpenAI, RateLimitError,
)

from meeting_intelligence.domain.errors import (
    TranscriptionAuthenticationError, TranscriptionProviderError,
    TranscriptionRateLimitError, TranscriptionResponseError,
    TranscriptionTimeoutError,
)
from meeting_intelligence.domain.transcript import TranscriptRecord, TranscriptSegment
from meeting_intelligence.media.models import AudioChunk, PreparedAudio


@dataclass(frozen=True, slots=True)
class OpenAITranscriptionConfig:
    model: str = "gpt-4o-transcribe-diarize"
    response_format: str = "diarized_json"
    language: str = "ja"
    timeout_seconds: float = 300.0
    max_retries: int = 2
    max_upload_bytes: int = 20 * 1024 * 1024
    max_audio_duration_seconds: float = 1400.0
    progress_interval_seconds: float = 15.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.max_upload_bytes <= 0 or self.max_audio_duration_seconds <= 0 or self.progress_interval_seconds <= 0 or self.max_retries < 0:
            raise ValueError("OpenAI transcription limits must be positive and retries non-negative")
        if self.response_format != "diarized_json":
            raise ValueError("Phase 3 requires diarized_json for Evidence timestamps and speakers")


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _safe_provider_field(value: Any, *, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value)).strip()
    return text[:limit] or None


def _status_error_details(exc: APIStatusError) -> tuple[str, dict[str, str | None]]:
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error", body) if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        error = {}
    details = {
        "provider_type": _safe_provider_field(error.get("type"), limit=100),
        "provider_code": _safe_provider_field(error.get("code"), limit=100),
        "provider_param": _safe_provider_field(error.get("param"), limit=100),
        "request_id": _safe_provider_field(getattr(exc, "request_id", None), limit=100),
    }
    message = _safe_provider_field(error.get("message"))
    parts = [f"OpenAI transcription failed with status {exc.status_code}"]
    for label, key in (("type", "provider_type"), ("code", "provider_code"), ("param", "provider_param")):
        if details[key]:
            parts.append(f"{label}={details[key]}")
    if message:
        parts.append(f"message={message}")
    if details["request_id"]:
        parts.append(f"request_id={details['request_id']}")
    return "; ".join(parts), details


def normalize_diarized_segments(
    response: Any,
    *,
    offset_seconds: float = 0.0,
    speaker_scope: str | None = None,
) -> list[tuple[float, float, str | None, str, int]]:
    raw_segments = _field(response, "segments")
    if not isinstance(raw_segments, (list, tuple)):
        raise TranscriptionResponseError("OpenAI diarized response is missing segments")
    normalized: list[tuple[float, float, str | None, str, int]] = []
    for ordinal, raw in enumerate(raw_segments):
        start, end, text, speaker = (_field(raw, key) for key in ("start", "end", "text", "speaker"))
        if start is None or end is None or text is None or speaker is None:
            raise TranscriptionResponseError("OpenAI diarized segment is missing a required field")
        try:
            global_start = float(start) + offset_seconds
            global_end = float(end) + offset_seconds
        except (TypeError, ValueError) as exc:
            raise TranscriptionResponseError("OpenAI diarized segment has invalid timestamps") from exc
        if global_start < 0 or global_end < global_start:
            raise TranscriptionResponseError("OpenAI diarized segment timestamps are invalid")
        clean_text = str(text).strip()
        if not clean_text:
            continue
        label = str(speaker)
        if speaker_scope is not None:
            label = f"{speaker_scope}:{label}"
        normalized.append((global_start, global_end, label, clean_text, ordinal))
    return normalized


class OpenAITranscriptionProvider:
    def __init__(self, *, api_key: str | None, config: OpenAITranscriptionConfig | None = None, client: Any | None = None, progress_callback: Callable[[str], None] | None = None) -> None:
        self.config = config or OpenAITranscriptionConfig()
        self.progress_callback = progress_callback
        if client is None:
            if not api_key:
                raise TranscriptionAuthenticationError("OpenAI API key is required")
            self._client = OpenAI(api_key=api_key, timeout=self.config.timeout_seconds, max_retries=self.config.max_retries)
        else:
            self._client = client

    def _transcribe_file(self, path: Path) -> Any:
        if not path.is_file():
            raise TranscriptionProviderError(f"prepared audio file does not exist: {path}")
        size = path.stat().st_size
        if size <= 0:
            raise TranscriptionProviderError("prepared audio file is empty")
        if size > self.config.max_upload_bytes:
            raise TranscriptionProviderError("prepared audio exceeds configured OpenAI upload limit")
        try:
            with path.open("rb") as audio_file:
                return self._client.audio.transcriptions.create(
                    model=self.config.model,
                    file=audio_file,
                    response_format=self.config.response_format,
                    chunking_strategy="auto",
                    language=self.config.language,
                    timeout=self.config.timeout_seconds,
                )
        except AuthenticationError as exc:
            raise TranscriptionAuthenticationError("OpenAI authentication failed") from exc
        except RateLimitError as exc:
            raise TranscriptionRateLimitError("OpenAI transcription rate limit exceeded") from exc
        except APITimeoutError as exc:
            raise TranscriptionTimeoutError("OpenAI transcription timed out") from exc
        except APIConnectionError as exc:
            raise TranscriptionProviderError("OpenAI transcription connection failed", retryable=True) from exc
        except APIStatusError as exc:
            retryable = exc.status_code >= 500
            message, details = _status_error_details(exc)
            raise TranscriptionProviderError(message, retryable=retryable, **details) from exc

    def _transcribe_with_progress(self, path: Path, *, index: int, total: int, duration: float) -> Any:
        callback = self.progress_callback
        if callback is None:
            return self._transcribe_file(path)
        started = monotonic()
        stop = Event()
        size = path.stat().st_size
        label = f"Transcribing chunk {index}/{total} ({duration:.1f}s, {size} bytes)"
        callback(f"{label} started; timeout={self.config.timeout_seconds:.0f}s")

        def heartbeat() -> None:
            while not stop.wait(self.config.progress_interval_seconds):
                callback(f"{label}... {monotonic() - started:.0f}s elapsed")

        thread = Thread(target=heartbeat, name="transcription-progress", daemon=True)
        thread.start()
        try:
            response = self._transcribe_file(path)
        except BaseException:
            callback(f"{label} stopped after {monotonic() - started:.1f}s")
            raise
        finally:
            stop.set()
            thread.join(timeout=1)
        callback(f"{label} completed in {monotonic() - started:.1f}s")
        return response

    def transcribe(self, prepared_audio: PreparedAudio, meeting_id: str) -> TranscriptRecord:
        items: list[tuple[Path, float, str | None, float]]
        if prepared_audio.chunks:
            items = [(chunk.path, chunk.start_seconds, chunk.chunk_id, chunk.duration_seconds) for chunk in prepared_audio.chunks]
        else:
            items = [(prepared_audio.audio_path, 0.0, None, prepared_audio.duration_seconds)]
        merged: list[tuple[float, float, str | None, str, int, int]] = []
        for item_order, (path, offset, scope, duration) in enumerate(items):
            if duration > self.config.max_audio_duration_seconds:
                raise TranscriptionProviderError(
                    f"prepared audio duration {duration:.3f} seconds exceeds the configured Provider limit of {self.config.max_audio_duration_seconds:.3f} seconds"
                )
            response = self._transcribe_with_progress(path, index=item_order + 1, total=len(items), duration=duration)
            for segment in normalize_diarized_segments(response, offset_seconds=offset, speaker_scope=scope):
                merged.append((*segment, item_order))
        merged.sort(key=lambda item: (item[0], item[5], item[4]))
        tolerance = 1.0
        if merged and merged[-1][1] > prepared_audio.duration_seconds + tolerance:
            raise TranscriptionResponseError("transcript segment exceeds prepared audio duration")
        segments = [
            TranscriptSegment(id=f"seg_{index:04d}", start=item[0], end=item[1], speaker=item[2], text=item[3])
            for index, item in enumerate(merged, start=1)
        ]
        return TranscriptRecord(
            meeting_id=meeting_id, language=self.config.language,
            duration_seconds=prepared_audio.duration_seconds, segments=segments,
        )
