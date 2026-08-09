import json
import subprocess
from pathlib import Path

import pytest

from meeting_intelligence.domain.errors import (
    AudioStreamNotFoundError, ExecutableNotFoundError, MediaProbeError,
    MediaValidationError,
)
from meeting_intelligence.media.tools import (
    check_executable, parse_probe_json, run_command, sha256_file, validate_media_source,
)


def test_validate_mp4_and_japanese_path(tmp_path: Path) -> None:
    source = tmp_path / "テスト会議.mp4"
    source.write_bytes(b"media")
    result = validate_media_source(source)
    assert result.file_name == "テスト会議.mp4"
    assert result.size_bytes == 5


def test_invalid_sources_fail(tmp_path: Path) -> None:
    with pytest.raises(MediaValidationError):
        validate_media_source(tmp_path / "missing.mp4")
    empty = tmp_path / "empty.mp4"
    empty.touch()
    with pytest.raises(MediaValidationError):
        validate_media_source(empty)
    unsupported = tmp_path / "audio.wav"
    unsupported.write_bytes(b"x")
    with pytest.raises(MediaValidationError):
        validate_media_source(unsupported)


def test_hash_is_deterministic_with_chunked_reading(tmp_path: Path) -> None:
    path = tmp_path / "large.mp4"
    path.write_bytes(bytes(range(256)) * 8192)
    assert sha256_file(path, block_size=257) == sha256_file(path, block_size=1024 * 1024)


def test_parse_probe_json_and_missing_optional_fields() -> None:
    payload = json.dumps({
        "format": {"duration": "12.5", "format_name": "mov,mp4", "bit_rate": "64000"},
        "streams": [{"index": 1, "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2}],
    })
    metadata = parse_probe_json(payload)
    assert metadata.duration_seconds == 12.5
    assert metadata.audio_streams[0].channel_layout is None


def test_malformed_probe_and_no_audio_fail() -> None:
    with pytest.raises(MediaProbeError):
        parse_probe_json("not-json")
    with pytest.raises(AudioStreamNotFoundError):
        parse_probe_json('{"format": {}, "streams": []}')


def test_executable_found_and_missing() -> None:
    calls: list[list[str]] = []

    def found(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "version", "")

    check_executable("ffmpeg-custom", timeout=1, runner=found)
    assert calls == [["ffmpeg-custom", "-version"]]

    def missing(args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        raise ExecutableNotFoundError("ffmpeg executable not found")

    with pytest.raises(ExecutableNotFoundError, match="not found"):
        check_executable("ffmpeg", timeout=1, runner=missing)


def test_subprocess_runner_disables_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_command(["ffmpeg", "-version"], timeout=3)
    assert captured["shell"] is False
    assert captured["timeout"] == 3
