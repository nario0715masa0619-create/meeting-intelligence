class MeetingIntelligenceError(Exception):
    """Base application error."""


class SchemaValidationError(MeetingIntelligenceError):
    """Canonical schema validation failed."""


class ConfigurationError(MeetingIntelligenceError):
    """Application configuration is invalid."""
