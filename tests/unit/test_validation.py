import pytest
from meeting_intelligence.domain.errors import SchemaValidationError
from meeting_intelligence.validation.schema import validate_meeting, validate_transcript


def test_validation_errors_are_translated() -> None:
    with pytest.raises(SchemaValidationError):
        validate_transcript({"schema_version": "0.1.0"})
    with pytest.raises(SchemaValidationError):
        validate_meeting("{}")

