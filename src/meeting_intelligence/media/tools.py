"""Safe subprocess, hashing, input validation, and ffprobe helpers."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from meeting_intelligence.domain.errors import (
    AudioStreamNotFoundError, ExecutableNotFoundError, MediaProbeError,
    MediaProcessError, MediaValidationError,
)
from meeting_intelligence.media.models import AudioStreamMetadata, MediaMetadata, MediaSource


class CommandRunner(Protocol):
    def __call__(self, args: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]: ...


def run_command(args: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(args), shell=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        raise ExecutableNotFoundError(f"{args[0]} executable not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProcessError(str(args[0]), -1, f"timed out after {timeout} seconds") from exc
    if result.returncode != 0:
        raise MediaProcessError(str(args[0]), result.returncode, result.stderr)
    return result


def check_executable(executable: str, *, timeout: float, runner: CommandRunner = run_command) -> None:
    try:
        runner([executable, "-version"], timeout=timeout)
    except ExecutableNotFoundError:
        raise
    except OSError as exc:
        raise ExecutableNotFoundError(f"{executable} executable not found") from exc


def sha256_file(path: Path, *, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_media_source(path: Path) -> MediaSource:
    path = path.expanduser().resolve()
    if not path.exists():
        raise MediaValidationError(f"media file does not exist: {path}")
    if not path.is_file():
        raise MediaValidationError(f"media source is not a regular file: {path}")
    if path.suffix.lower() != ".mp4":
        raise MediaValidationError("unsupported media extension; expected .mp4")
    try:
        size = path.stat().st_size
        with path.open("rb"):
            pass
    except OSError as exc:
        raise MediaValidationError(f"media file is not readable: {path}") from exc
    if size <= 0:
        raise MediaValidationError("media file is empty")
    return MediaSource(path=path, file_name=path.name, size_bytes=size, sha256=sha256_file(path))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_probe_json(payload: str, *, require_audio: bool = True) -> MediaMetadata:
    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MediaProbeError("ffprobe returned malformed JSON") from exc
    if not isinstance(raw, dict):
        raise MediaProbeError("ffprobe JSON root must be an object")
    format_data = raw.get("format") if isinstance(raw.get("format"), dict) else {}
    streams = raw.get("streams") if isinstance(raw.get("streams"), list) else []
    audio_streams = [
        AudioStreamMetadata(
            index=int(stream["index"]), codec_name=stream.get("codec_name"),
            sample_rate=_optional_int(stream.get("sample_rate")),
            channels=_optional_int(stream.get("channels")),
            channel_layout=stream.get("channel_layout"),
        )
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "audio" and "index" in stream
    ]
    if require_audio and not audio_streams:
        raise AudioStreamNotFoundError("media contains no audio stream")
    return MediaMetadata(
        duration_seconds=_optional_float(format_data.get("duration")),
        format_name=format_data.get("format_name"), bit_rate=_optional_int(format_data.get("bit_rate")),
        audio_streams=audio_streams,
    )


def probe_media(path: Path, ffprobe_path: str, *, timeout: float, runner: CommandRunner = run_command, require_audio: bool = True) -> MediaMetadata:
    try:
        result = runner([
            ffprobe_path, "-v", "error", "-show_format", "-show_streams",
            "-print_format", "json", os.fspath(path),
        ], timeout=timeout)
    except MediaProcessError as exc:
        raise MediaProbeError(f"ffprobe inspection failed: {exc}") from exc
    return parse_probe_json(result.stdout, require_audio=require_audio)
