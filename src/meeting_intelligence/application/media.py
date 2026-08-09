"""Application boundary for Phase 2 media preparation."""

from pathlib import Path
from meeting_intelligence.config.settings import Settings
from meeting_intelligence.media.models import PreparedAudio
from meeting_intelligence.media.processor import MediaProcessingConfig, prepare_audio


def prepare_meeting_media(source_path: Path, workspace: Path, settings: Settings) -> PreparedAudio:
    config = MediaProcessingConfig(
        ffmpeg_path=settings.ffmpeg_path, ffprobe_path=settings.ffprobe_path,
        audio_codec=settings.audio_codec, audio_bitrate=settings.audio_bitrate,
        audio_sample_rate=settings.audio_sample_rate, audio_channels=settings.audio_channels,
        max_audio_bytes=settings.max_audio_bytes,
        max_chunk_duration_seconds=settings.max_chunk_duration_seconds,
        subprocess_timeout_seconds=settings.subprocess_timeout_seconds,
    )
    return prepare_audio(source_path, workspace, config)
