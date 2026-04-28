"""
Schema validator for clinical analytics events.

Loads JSON Schema definitions from event_schemas/ and validates each
event against its corresponding schema based on event_name.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft7Validator


SCHEMAS_DIR = Path(__file__).parent.parent / "event_schemas"


@dataclass
class ValidationError:
    error_type: str
    field_path: str
    message: str


@dataclass
class ValidationResult:
    event_name: str | None
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    raw_event: dict = field(default_factory=dict)


class SchemaValidator:
    def __init__(self, schemas_dir: Path = SCHEMAS_DIR):
        self._validators: dict[str, Draft7Validator] = {}
        self._load_schemas(schemas_dir)

    def _load_schemas(self, schemas_dir: Path) -> None:
        for schema_file in schemas_dir.glob("*.json"):
            schema = json.loads(schema_file.read_text())
            event_name = schema_file.stem
            self._validators[event_name] = Draft7Validator(schema)

    @property
    def known_events(self) -> list[str]:
        return list(self._validators.keys())

    def validate(self, event: dict[str, Any]) -> ValidationResult:
        event_name = event.get("event_name")

        if not event_name:
            return ValidationResult(
                event_name=None,
                is_valid=False,
                errors=[ValidationError("missing_field", "event_name", "event_name is required")],
                raw_event=event,
            )

        validator = self._validators.get(event_name)
        if not validator:
            return ValidationResult(
                event_name=event_name,
                is_valid=False,
                errors=[ValidationError("schema", "event_name", f"No schema registered for event '{event_name}'")],
                raw_event=event,
            )

        errors = []
        for err in validator.iter_errors(event):
            field_path = ".".join(str(p) for p in err.absolute_path) or err.schema_path[-1]
            error_type = _classify_error(err)
            errors.append(ValidationError(error_type, str(field_path), err.message))

        return ValidationResult(
            event_name=event_name,
            is_valid=len(errors) == 0,
            errors=errors,
            raw_event=event,
        )

    def validate_batch(self, events: list[dict[str, Any]]) -> list[ValidationResult]:
        return [self.validate(e) for e in events]


def _classify_error(err: jsonschema.ValidationError) -> str:
    if err.validator == "required":
        return "missing_field"
    if err.validator in ("type", "format"):
        return "type_mismatch"
    return "schema"
