import shutil
import subprocess
from pathlib import Path

import pytest

from meeting_intelligence.media.processor import MediaProcessingConfig, prepare_audio
from meeting_intelligence.media.tools import probe_media, sha256_file


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="ffmpeg and ffprobe are required for media integration tests")


def test_synthetic_mp4_extract_probe_and_chunk(tmp_path: Path) -> None:
    source = tmp_path / "テスト会議.mp4"
    subprocess.run([
        str(FFMPEG), "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:d=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest",
        "-c:v", "libx264", "-c:a", "aac", str(source),
    ], shell=False, check=True, capture_output=True, timeout=30)
    source_hash = sha256_file(source)
    result = prepare_audio(source, tmp_path / "work", MediaProcessingConfig(
        ffmpeg_path=str(FFMPEG), ffprobe_path=str(FFPROBE), max_chunk_duration_seconds=1.2,
    ))
    assert source_hash == sha256_file(source)
    assert result.audio_path.stat().st_size > 0
    assert len(result.chunks) >= 2
    metadata = probe_media(result.audio_path, str(FFPROBE), timeout=30)
    assert metadata.duration_seconds == pytest.approx(3, abs=.25)
