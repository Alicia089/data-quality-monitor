"""Unit tests for AnomalyDetector."""
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from anomaly_detector import AnomalyDetector


def _event(name="assessment_started", minutes_ago=0, **props):
    occurred = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    return {
        "event_name": name,
        "occurred_at": occurred,
        "properties": props,
    }


@pytest.fixture
def detector():
    return AnomalyDetector(expected_events=["assessment_started", "alert_triggered"])


def test_no_anomalies_for_clean_batch(detector):
    events = [_event("assessment_started"), _event("alert_triggered")]
    report = detector.analyze(events)
    assert not report.has_anomalies


def test_frequency_spike_detected(detector):
    events = [_event("assessment_started")] * 30 + [_event("alert_triggered")]
    report = detector.analyze(events)
    spike = [a for a in report.anomalies if a.anomaly_type == "frequency_spike"]
    assert len(spike) > 0


def test_missing_expected_event(detector):
    events = [_event("assessment_started")]
    report = detector.analyze(events)
    missing = [a for a in report.anomalies if a.anomaly_type == "missing_expected_event"]
    assert any(a.event_name == "alert_triggered" for a in missing)


def test_numeric_outlier_detected():
    detector = AnomalyDetector(numeric_zscore_threshold=2.0)
    events = [_event(risk_score=float(v)) for v in [80, 82, 81, 79, 83, 1000]]
    report = detector.analyze(events)
    outliers = [a for a in report.anomalies if a.anomaly_type == "numeric_outlier"]
    assert len(outliers) > 0


def test_stale_events_flagged():
    detector = AnomalyDetector()
    events = [_event(minutes_ago=200), _event(minutes_ago=180)]
    report = detector.analyze(events, window_minutes=60)
    stale = [a for a in report.anomalies if a.anomaly_type == "stale_events"]
    assert len(stale) > 0


def test_empty_batch_returns_no_anomalies(detector):
    report = detector.analyze([])
    assert not report.has_anomalies
