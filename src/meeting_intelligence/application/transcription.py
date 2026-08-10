"""Application use case for Provider-independent transcription."""

from meeting_intelligence.domain.transcript import TranscriptRecord
from meeting_intelligence.media.models import PreparedAudio
from meeting_intelligence.transcription.base import TranscriptionProvider


def transcribe_prepared_audio(prepared_audio: PreparedAudio, meeting_id: str, provider: TranscriptionProvider) -> TranscriptRecord:
    return provider.transcribe(prepared_audio, meeting_id)
