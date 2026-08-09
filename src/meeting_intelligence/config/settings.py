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
    transcription_model: str = ""
    analysis_model: str = ""
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "MI_OPENAI_API_KEY"),
        repr=False,
    )
