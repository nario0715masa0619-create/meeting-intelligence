from pathlib import Path
from typing import Protocol
from meeting_intelligence.domain.transcript import TranscriptRecord


class TranscriptionProvider(Protocol):
    def transcribe(self, audio_path: Path, meeting_id: str) -> TranscriptRecord:
        ...

