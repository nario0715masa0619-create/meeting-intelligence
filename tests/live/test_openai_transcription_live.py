"""Explicitly opted-in acceptance test for OpenAI diarized transcription."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import wave

import pytest

from meeting_intelligence.config.settings import Settings
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.media.models import PreparedAudio
from meeting_intelligence.transcription.openai import OpenAITranscriptionProvider


pytestmark = pytest.mark.live

JAPANESE_CHARACTER = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _live_audio(configured_path: Path | None) -> tuple[Path, float]:
    if configured_path is None or str(configured_path) in ("", "."):
        pytest.skip("MEETING_INTELLIGENCE_LIVE_AUDIO is not set")

    path = configured_path.expanduser()
    if not path.is_file():
        pytest.skip("MEETING_INTELLIGENCE_LIVE_AUDIO does not identify a file")
    if path.suffix.lower() != ".wav":
        pytest.fail("MEETING_INTELLIGENCE_LIVE_AUDIO must identify a WAV file")

    try:
        with wave.open(str(path), "rb") as audio:
            duration_seconds = audio.getnframes() / audio.getframerate()
    except (EOFError, wave.Error) as exc:
        pytest.fail(f"MEETING_INTELLIGENCE_LIVE_AUDIO is not a valid WAV file: {exc}")

    if not 0 < duration_seconds <= 30:
        pytest.fail("live acceptance audio must be longer than zero and no more than 30 seconds")
    return path, duration_seconds


def test_openai_diarized_transcription_normalizes_to_canonical_record() -> None:
    settings = Settings(_env_file=REPOSITORY_ROOT / ".env")
    api_key = settings.openai_api_key
    if api_key is None or not api_key.get_secret_value():
        pytest.skip("OPENAI_API_KEY is not set")

    audio_path, duration_seconds = _live_audio(settings.live_audio_path)
    audio_bytes = audio_path.read_bytes()
    prepared_audio = PreparedAudio(
        source_path=audio_path,
        audio_path=audio_path,
        duration_seconds=duration_seconds,
        size_bytes=len(audio_bytes),
        format="wav",
        sha256=hashlib.sha256(audio_bytes).hexdigest(),
    )

    record = OpenAITranscriptionProvider(
        api_key=api_key.get_secret_value(),
    ).transcribe(
        prepared_audio,
        meeting_id="live-openai-acceptance",
    )

    assert isinstance(record, TranscriptRecord)
    assert len(record.segments) >= 1
    for segment in record.segments:
        assert segment.id
        assert segment.start >= 0
        assert segment.end >= segment.start
        assert segment.text.strip()
    assert any(segment.speaker is not None for segment in record.segments)
    assert any(JAPANESE_CHARACTER.search(segment.text) for segment in record.segments)
    assert TranscriptRecord.model_validate(record.model_dump()) == record
