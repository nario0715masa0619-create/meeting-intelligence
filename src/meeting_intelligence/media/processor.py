"""ffmpeg-backed media preparation with explicit safety boundaries."""

from __future__ import annotations

import math
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from meeting_intelligence.domain.errors import ArtifactExistsError, MediaValidationError
from meeting_intelligence.media.models import AudioChunk, PreparedAudio
from meeting_intelligence.media.tools import (
    CommandRunner, check_executable, probe_media, run_command, sha256_file,
    validate_media_source,
)


@dataclass(frozen=True, slots=True)
class MediaProcessingConfig:
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    audio_codec: str = "libmp3lame"
    audio_bitrate: str = "64k"
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    max_audio_bytes: int = 20 * 1024 * 1024
    max_chunk_duration_seconds: float = 1800.0
    subprocess_timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        numeric = (
            self.audio_sample_rate, self.audio_channels, self.max_audio_bytes,
            self.max_chunk_duration_seconds, self.subprocess_timeout_seconds,
        )
        if any(value <= 0 for value in numeric):
            raise ValueError("media processing numeric settings must be positive")


def build_extract_command(source: Path, destination: Path, config: MediaProcessingConfig) -> list[str]:
    return [
        config.ffmpeg_path, "-v", "error", "-n", "-i", os.fspath(source),
        "-map", "0:a:0", "-vn", "-c:a", config.audio_codec,
        "-b:a", config.audio_bitrate, "-ar", str(config.audio_sample_rate),
        "-ac", str(config.audio_channels), os.fspath(destination),
    ]


def build_chunk_command(source: Path, destination: Path, start: float, duration: float, config: MediaProcessingConfig) -> list[str]:
    return [
        config.ffmpeg_path, "-v", "error", "-n", "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}", "-i", os.fspath(source), "-c:a", "copy",
        os.fspath(destination),
    ]


def _ensure_new_destination(path: Path) -> None:
    if path.exists():
        raise ArtifactExistsError(f"destination already exists: {path}")


def _chunk_duration(duration: float, size_bytes: int, config: MediaProcessingConfig) -> float | None:
    candidates: list[float] = []
    if duration > config.max_chunk_duration_seconds:
        candidates.append(config.max_chunk_duration_seconds)
    if size_bytes > config.max_audio_bytes:
        candidates.append(max(1.0, duration * config.max_audio_bytes / size_bytes * 0.9))
    return min(candidates) if candidates else None


def prepare_audio(
    source_path: Path,
    workspace: Path,
    config: MediaProcessingConfig,
    *,
    runner: CommandRunner = run_command,
) -> PreparedAudio:
    source = validate_media_source(source_path)
    check_executable(config.ffmpeg_path, timeout=config.subprocess_timeout_seconds, runner=runner)
    check_executable(config.ffprobe_path, timeout=config.subprocess_timeout_seconds, runner=runner)
    source_metadata = probe_media(source.path, config.ffprobe_path, timeout=config.subprocess_timeout_seconds, runner=runner)
    if source_metadata.duration_seconds is None:
        raise MediaValidationError("source duration is unavailable")

    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    audio_path = workspace / "prepared_audio.mp3"
    _ensure_new_destination(audio_path)
    runner(build_extract_command(source.path, audio_path, config), timeout=config.subprocess_timeout_seconds)
    if not audio_path.is_file() or audio_path.stat().st_size <= 0:
        raise MediaValidationError("ffmpeg did not create a non-empty audio artifact")

    audio_metadata = probe_media(audio_path, config.ffprobe_path, timeout=config.subprocess_timeout_seconds, runner=runner)
    duration = audio_metadata.duration_seconds
    if duration is None:
        raise MediaValidationError("prepared audio duration is unavailable")
    size_bytes = audio_path.stat().st_size
    chunks: list[AudioChunk] = []
    target_duration = _chunk_duration(duration, size_bytes, config)
    if target_duration is not None:
        for index in range(math.ceil(duration / target_duration)):
            start = index * target_duration
            chunk_duration = min(target_duration, duration - start)
            destination = workspace / f"audio_chunk_{index + 1:04d}.mp3"
            _ensure_new_destination(destination)
            runner(build_chunk_command(audio_path, destination, start, chunk_duration, config), timeout=config.subprocess_timeout_seconds)
            if not destination.is_file() or destination.stat().st_size <= 0:
                raise MediaValidationError(f"ffmpeg did not create chunk {index + 1}")
            chunks.append(AudioChunk(
                chunk_id=f"chunk_{index + 1:04d}", path=destination,
                start_seconds=start, end_seconds=start + chunk_duration,
                duration_seconds=chunk_duration, size_bytes=destination.stat().st_size,
                sha256=sha256_file(destination),
            ))

    if sha256_file(source.path) != source.sha256:
        raise MediaValidationError("source media changed during processing")
    return PreparedAudio(
        source_path=source.path, audio_path=audio_path, duration_seconds=duration,
        size_bytes=size_bytes, format="mp3", sha256=sha256_file(audio_path), chunks=chunks,
    )


def cleanup_workspace(workspace: Path) -> None:
    """Remove only the explicitly supplied media workspace."""
    workspace = workspace.resolve()
    if workspace.exists():
        if not workspace.is_dir():
            raise MediaValidationError(f"workspace is not a directory: {workspace}")
        shutil.rmtree(workspace)
