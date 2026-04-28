"""Unit tests for SchemaValidator."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from validator import SchemaValidator


@pytest.fixture
def validator():
    return SchemaValidator()


VALID_ASSESSMENT = {
    "event_name": "assessment_started",
    "user_id": "clinician_001",
    "user_role": "clinician",
    "session_id": "sess_abc",
    "occurred_at": "2024-03-01T08:00:00+00:00",
    "properties": {
        "patient_id": "patient_123",
        "form_version": "2.1",
    },
}

VALID_ALERT = {
    "event_name": "alert_triggered",
    "user_id": "clinician_002",
    "user_role": "clinician",
    "session_id": "sess_def",
    "occurred_at": "2024-03-01T09:00:00+00:00",
    "properties": {
        "alert_id": "alert_456",
        "severity": "high",
        "patient_id": "patient_123",
        "risk_score": 87.5,
    },
}


def test_valid_assessment_passes(validator):
    result = validator.validate(VALID_ASSESSMENT)
    assert result.is_valid
    assert result.errors == []


def test_valid_alert_passes(validator):
    result = validator.validate(VALID_ALERT)
    assert result.is_valid


def test_missing_event_name(validator):
    event = {**VALID_ASSESSMENT}
    del event["event_name"]
    result = validator.validate(event)
    assert not result.is_valid
    assert any(e.error_type == "missing_field" for e in result.errors)


def test_unknown_event_name(validator):
    event = {**VALID_ASSESSMENT, "event_name": "unknown_event"}
    result = validator.validate(event)
    assert not result.is_valid


def test_invalid_user_role(validator):
    event = {**VALID_ASSESSMENT, "user_role": "robot"}
    result = validator.validate(event)
    assert not result.is_valid


def test_missing_required_property(validator):
    event = {**VALID_ASSESSMENT, "properties": {"form_version": "2.1"}}
    result = validator.validate(event)
    assert not result.is_valid
    assert any(e.error_type == "missing_field" for e in result.errors)


def test_invalid_risk_score_out_of_range(validator):
    event = {**VALID_ALERT, "properties": {**VALID_ALERT["properties"], "risk_score": 150}}
    result = validator.validate(event)
    assert not result.is_valid


def test_batch_validation(validator):
    events = [VALID_ASSESSMENT, VALID_ALERT, {"event_name": "bad_event"}]
    results = validator.validate_batch(events)
    assert results[0].is_valid
    assert results[1].is_valid
    assert not results[2].is_valid
