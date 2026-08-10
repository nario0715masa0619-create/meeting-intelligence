from pathlib import Path
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MI_", extra="ignore")
    application_version: str = "0.1.0"
    schema_version: str = "0.1.0"
    output_dir: Path = Path("output")
    work_dir: Path = Path(".work")
    transcription_provider: str = "openai"
    analysis_provider: str = "openai"
    transcription_model: str = "gpt-4o-transcribe-diarize"
    transcription_response_format: str = "diarized_json"
    transcription_language: str = "ja"
    analysis_model: str = "gpt-5.6-terra"
    analysis_reasoning_effort: str = "low"
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    audio_codec: str = "libmp3lame"
    audio_bitrate: str = "64k"
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    max_audio_bytes: int = 20 * 1024 * 1024
    max_chunk_duration_seconds: float = 300.0
    subprocess_timeout_seconds: float = 300.0
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "MI_OPENAI_API_KEY"),
        repr=False,
    )
    live_audio_path: Path | None = Field(
        default=None,
        validation_alias="MEETING_INTELLIGENCE_LIVE_AUDIO",
    )
    openai_timeout_seconds: float = 300.0
    openai_max_retries: int = 2
    openai_max_upload_bytes: int = 20 * 1024 * 1024
    google_service_account_file: Path | None = Field(default=None, validation_alias="GOOGLE_SERVICE_ACCOUNT_FILE")
    google_sheets_spreadsheet_id: str = Field(default="", validation_alias="GOOGLE_SHEETS_SPREADSHEET_ID")
    google_meetings_sheet: str = "Meetings"
    google_decisions_sheet: str = "Decisions"
    google_action_items_sheet: str = "Action Items"
    google_open_items_sheet: str = "Open Items"
