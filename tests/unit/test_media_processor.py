import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from meeting_intelligence.domain.errors import ArtifactExistsError
from meeting_intelligence.media.models import AudioChunk, PreparedAudio
from meeting_intelligence.media.processor import (
    MediaProcessingConfig, build_chunk_command, build_extract_command,
    cleanup_workspace, prepare_audio,
)


class FakeRunner:
    def __init__(self, duration: float = 5.0) -> None:
        self.duration = duration
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        command = list(args)
        self.calls.append(command)
        if command[1:] == ["-version"]:
            return subprocess.CompletedProcess(command, 0, "version", "")
        if "-print_format" in command:
            payload = json.dumps({"format": {"duration": str(self.duration), "format_name": "mp3", "bit_rate": "64000"}, "streams": [{"index": 0, "codec_type": "audio", "codec_name": "mp3"}]})
            return subprocess.CompletedProcess(command, 0, payload, "")
        Path(command[-1]).write_bytes(b"prepared-audio" * 10)
        return subprocess.CompletedProcess(command, 0, "", "")


def make_source(tmp_path: Path) -> Path:
    source = tmp_path / "テスト 会議.mp4"
    source.write_bytes(b"original-source")
    return source


def test_command_construction_uses_argument_lists_and_safe_flags(tmp_path: Path) -> None:
    config = MediaProcessingConfig()
    assert config.max_chunk_duration_seconds == 300
    extract = build_extract_command(tmp_path / "a b.mp4", tmp_path / "out.mp3", config)
    chunk = build_chunk_command(tmp_path / "out.mp3", tmp_path / "chunk.mp3", 1, 2, config)
    assert "-n" in extract and extract[-1].endswith("out.mp3")
    assert chunk[-1].endswith("chunk.mp3") and "1.000" in chunk and "2.000" in chunk


def test_chunking_not_required_preserves_source(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    before = source.read_bytes()
    result = prepare_audio(source, tmp_path / "work", MediaProcessingConfig(max_chunk_duration_seconds=10), runner=FakeRunner())
    assert result.chunks == []
    assert result.audio_path.is_file() and result.size_bytes > 0
    assert source.read_bytes() == before


def test_duration_chunking_is_deterministic_and_ordered(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    result = prepare_audio(source, tmp_path / "work", MediaProcessingConfig(max_chunk_duration_seconds=2), runner=FakeRunner())
    assert [chunk.path.name for chunk in result.chunks] == ["audio_chunk_0001.mp3", "audio_chunk_0002.mp3", "audio_chunk_0003.mp3"]
    assert [(chunk.start_seconds, chunk.end_seconds) for chunk in result.chunks] == [(0, 2), (2, 4), (4, 5)]


def test_size_threshold_triggers_chunking(tmp_path: Path) -> None:
    result = prepare_audio(make_source(tmp_path), tmp_path / "work", MediaProcessingConfig(max_audio_bytes=20, max_chunk_duration_seconds=100), runner=FakeRunner())
    assert len(result.chunks) > 1


def test_invalid_chunk_order_fails() -> None:
    digest = "0" * 64
    chunks = [
        AudioChunk(chunk_id="c1", path=Path("1.mp3"), start_seconds=0, end_seconds=2, duration_seconds=2, size_bytes=1, sha256=digest),
        AudioChunk(chunk_id="c2", path=Path("2.mp3"), start_seconds=1, end_seconds=3, duration_seconds=2, size_bytes=1, sha256=digest),
    ]
    with pytest.raises(ValidationError):
        PreparedAudio(source_path=Path("s.mp4"), audio_path=Path("a.mp3"), duration_seconds=3, size_bytes=1, format="mp3", sha256=digest, chunks=chunks)


def test_existing_destination_fails_safely(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "prepared_audio.mp3").write_bytes(b"existing")
    with pytest.raises(ArtifactExistsError):
        prepare_audio(source, work, MediaProcessingConfig(), runner=FakeRunner())


def test_cleanup_removes_only_explicit_workspace(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "artifact").write_bytes(b"x")
    cleanup_workspace(work)
    assert not work.exists() and source.exists()
