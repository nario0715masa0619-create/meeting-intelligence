from typing import Protocol
from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.media.models import PreparedAudio


class TranscriptionProvider(Protocol):
    def transcribe(self, prepared_audio: PreparedAudio, meeting_id: str) -> TranscriptRecord:
        ...
