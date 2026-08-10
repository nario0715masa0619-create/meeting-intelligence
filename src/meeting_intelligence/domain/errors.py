class MeetingIntelligenceError(Exception):
    """Base application error."""


class SchemaValidationError(MeetingIntelligenceError):
    """Canonical schema validation failed."""


class ConfigurationError(MeetingIntelligenceError):
    """Application configuration is invalid."""


class MediaError(MeetingIntelligenceError):
    """Base error for media preparation."""


class MediaValidationError(MediaError):
    """The source media or generated metadata is invalid."""


class MediaProbeError(MediaError):
    """ffprobe could not inspect media."""


class AudioStreamNotFoundError(MediaProbeError):
    """The source contains no audio stream."""


class ExecutableNotFoundError(MediaError):
    """A required system executable is unavailable."""


class ArtifactExistsError(MediaError):
    """A destination exists and overwrite was not authorized."""


class MediaProcessError(MediaError):
    """An ffmpeg or ffprobe operation failed."""

    def __init__(self, operation: str, return_code: int, stderr: str) -> None:
        summary = stderr.strip()[-2000:]
        super().__init__(f"{operation} failed with return code {return_code}: {summary}")
        self.operation = operation
        self.return_code = return_code
        self.stderr_summary = summary


class TranscriptionError(MeetingIntelligenceError):
    """Base transcription failure with an explicit retry classification."""

    retryable = False


class TranscriptionAuthenticationError(TranscriptionError):
    """Authentication failed without exposing credentials."""


class TranscriptionRateLimitError(TranscriptionError):
    """The Provider rejected the request due to rate limiting."""

    retryable = True


class TranscriptionTimeoutError(TranscriptionError):
    """The Provider request timed out."""

    retryable = True


class TranscriptionProviderError(TranscriptionError):
    """The Provider failed for a reason not represented more specifically."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class TranscriptionResponseError(TranscriptionError):
    """The Provider returned a malformed or contradictory response."""


class OutputError(MeetingIntelligenceError):
    """Base failure while validating or persisting output artifacts."""


class OutputValidationError(OutputError):
    """A record cannot be persisted as canonical output."""


class OutputExistsError(OutputError):
    """An immutable meeting output already exists."""


class OutputWriteError(OutputError):
    """The required artifact set could not be finalized."""


class AnalysisError(MeetingIntelligenceError):
    """Base meeting-analysis failure."""


class AnalysisAuthenticationError(AnalysisError):
    """Analysis Provider authentication failed without exposing credentials."""


class AnalysisProviderError(AnalysisError):
    """The analysis Provider request failed."""


class AnalysisResponseError(AnalysisError):
    """The analysis Provider returned invalid structured output."""


class EvidenceValidationError(AnalysisError):
    """Structured analysis contains missing or invalid Evidence references."""


class GoogleSheetsError(MeetingIntelligenceError):
    """Base Google Sheets integration failure."""


class GoogleSheetsAuthenticationError(GoogleSheetsError):
    """Service Account authentication failed without exposing credentials."""


class GoogleSheetsPermissionError(GoogleSheetsError):
    """The Service Account lacks access to the configured spreadsheet."""


class GoogleSheetsSchemaError(GoogleSheetsError):
    """The configured spreadsheet cannot satisfy the required tab schema."""


class DuplicateMeetingError(GoogleSheetsError):
    """The meeting_id already exists and no rows were appended."""


class GoogleSheetsWriteError(GoogleSheetsError):
    """The atomic spreadsheet data write failed."""
