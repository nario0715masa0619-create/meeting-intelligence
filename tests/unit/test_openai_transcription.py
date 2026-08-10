from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import meeting_intelligence.transcription.openai as adapter
from meeting_intelligence.application.transcription import transcribe_prepared_audio
from meeting_intelligence.domain.errors import (
    TranscriptionAuthenticationError, TranscriptionProviderError,
    TranscriptionResponseError,
)
from meeting_intelligence.media.models import AudioChunk, PreparedAudio
from meeting_intelligence.transcription.openai import (
    OpenAITranscriptionConfig, OpenAITranscriptionProvider,
    normalize_diarized_segments,
)


class FakeTranscriptions:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.files: list[Any] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        self.files.append(kwargs["file"])
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.transcriptions = FakeTranscriptions(responses)
        self.audio = SimpleNamespace(transcriptions=self.transcriptions)


def response(*segments: dict[str, Any]) -> dict[str, Any]:
    return {"segments": list(segments), "text": "".join(str(item.get("text", "")) for item in segments)}


def prepared(tmp_path: Path, *, chunks: bool = False, duration: float = 10) -> PreparedAudio:
    audio = tmp_path / "prepared.mp3"
    audio.write_bytes(b"audio")
    chunk_values: list[AudioChunk] = []
    if chunks:
        for index, start in enumerate((0.0, 5.0), start=1):
            path = tmp_path / f"audio_chunk_{index:04d}.mp3"
            path.write_bytes(b"chunk")
            chunk_values.append(AudioChunk(
                chunk_id=f"chunk_{index:04d}", path=path, start_seconds=start,
                end_seconds=start + 5, duration_seconds=5, size_bytes=5, sha256="0" * 64,
            ))
    return PreparedAudio(
        source_path=tmp_path / "source.mp4", audio_path=audio,
        duration_seconds=duration, size_bytes=5, format="mp3", sha256="0" * 64,
        chunks=chunk_values,
    )


def test_single_file_normalizes_japanese_speaker_and_request(tmp_path: Path) -> None:
    client = FakeClient([response({"start": 0.2, "end": 1.5, "speaker": "A", "text": " 今日は認証方式について決めます。 "})])
    provider = OpenAITranscriptionProvider(api_key=None, client=client)
    record = transcribe_prepared_audio(prepared(tmp_path), "meeting-1", provider)
    assert record.segments[0].model_dump() == {"id": "seg_0001", "start": 0.2, "end": 1.5, "speaker": "A", "text": "今日は認証方式について決めます。"}
    call = client.transcriptions.calls[0]
    assert call["model"] == "gpt-4o-transcribe-diarize"
    assert call["response_format"] == "diarized_json"
    assert call["chunking_strategy"] == "auto" and call["language"] == "ja"
    assert "b" in call["file"].mode and client.transcriptions.files[0].closed


def test_multiple_segments_are_chronological_with_unique_ids(tmp_path: Path) -> None:
    client = FakeClient([response(
        {"start": 2, "end": 3, "speaker": "B", "text": "後"},
        {"start": 0, "end": 1, "speaker": "A", "text": "先"},
        {"start": 1, "end": 1.1, "speaker": "A", "text": "   "},
    )])
    record = OpenAITranscriptionProvider(api_key=None, client=client).transcribe(prepared(tmp_path), "m1")
    assert [item.id for item in record.segments] == ["seg_0001", "seg_0002"]
    assert [item.text for item in record.segments] == ["先", "後"]


def test_chunks_apply_offsets_and_scope_speakers(tmp_path: Path) -> None:
    client = FakeClient([
        response({"start": 1, "end": 2, "speaker": "A", "text": "一"}),
        response({"start": 0.5, "end": 1.5, "speaker": "A", "text": "二"}),
    ])
    record = OpenAITranscriptionProvider(api_key=None, client=client).transcribe(prepared(tmp_path, chunks=True), "m1")
    assert [(item.start, item.end) for item in record.segments] == [(1, 2), (5.5, 6.5)]
    assert [item.speaker for item in record.segments] == ["chunk_0001:A", "chunk_0002:A"]
    assert [item.id for item in record.segments] == ["seg_0001", "seg_0002"]


@pytest.mark.parametrize("segment", [
    {"start": -1, "end": 1, "speaker": "A", "text": "x"},
    {"start": 2, "end": 1, "speaker": "A", "text": "x"},
    {"start": 0, "end": 1, "speaker": "A"},
])
def test_malformed_segments_fail(segment: dict[str, Any]) -> None:
    with pytest.raises(TranscriptionResponseError):
        normalize_diarized_segments(response(segment))


def test_missing_segments_and_duration_contradiction_fail(tmp_path: Path) -> None:
    with pytest.raises(TranscriptionResponseError):
        normalize_diarized_segments({"text": "x"})
    client = FakeClient([response({"start": 0, "end": 12, "speaker": "A", "text": "x"})])
    with pytest.raises(TranscriptionResponseError, match="duration"):
        OpenAITranscriptionProvider(api_key=None, client=client).transcribe(prepared(tmp_path, duration=10), "m1")


def test_oversized_file_rejected_before_upload(tmp_path: Path) -> None:
    client = FakeClient([])
    config = OpenAITranscriptionConfig(max_upload_bytes=4)
    with pytest.raises(TranscriptionProviderError, match="upload limit"):
        OpenAITranscriptionProvider(api_key=None, client=client, config=config).transcribe(prepared(tmp_path), "m1")
    assert client.transcriptions.calls == []


def test_missing_key_is_explicit_and_secret_is_not_exposed() -> None:
    with pytest.raises(TranscriptionAuthenticationError, match="required") as exc:
        OpenAITranscriptionProvider(api_key=None)
    assert "sk-" not in str(exc.value)


def test_authentication_error_is_sanitized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeAuthenticationError(Exception):
        pass

    monkeypatch.setattr(adapter, "AuthenticationError", FakeAuthenticationError)
    client = FakeClient([FakeAuthenticationError("secret-key-value")])
    with pytest.raises(TranscriptionAuthenticationError) as exc:
        OpenAITranscriptionProvider(api_key=None, client=client).transcribe(prepared(tmp_path), "m1")
    assert "secret-key-value" not in str(exc.value)


def test_partial_chunk_failure_returns_no_record(tmp_path: Path) -> None:
    client = FakeClient([
        response({"start": 0, "end": 1, "speaker": "A", "text": "ok"}),
        TranscriptionProviderError("chunk failed"),
    ])
    with pytest.raises(TranscriptionProviderError, match="chunk failed"):
        OpenAITranscriptionProvider(api_key=None, client=client).transcribe(prepared(tmp_path, chunks=True), "m1")
