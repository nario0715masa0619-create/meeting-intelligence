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
