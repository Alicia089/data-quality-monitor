"""
Anomaly detector for clinical event streams.

Checks for statistical and structural anomalies that schema validation
alone cannot catch: unexpected event frequency spikes, missing expected
events within a time window, and numeric field outliers.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any


@dataclass
class Anomaly:
    anomaly_type: str
    event_name: str | None
    field_path: str | None
    message: str
    severity: str  # 'low', 'medium', 'high'


@dataclass
class AnomalyReport:
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def has_anomalies(self) -> bool:
        return len(self.anomalies) > 0

    @property
    def high_severity_count(self) -> int:
        return sum(1 for a in self.anomalies if a.severity == "high")


class AnomalyDetector:
    """
    Detects anomalies in a batch of events. Designed to run after
    schema validation so it only sees structurally valid events.
    """

    def __init__(
        self,
        expected_events: list[str] | None = None,
        frequency_spike_threshold: float = 3.0,
        numeric_zscore_threshold: float = 3.0,
    ):
        self._expected_events = set(expected_events or [])
        self._freq_threshold = frequency_spike_threshold
        self._zscore_threshold = numeric_zscore_threshold

    def analyze(self, events: list[dict[str, Any]], window_minutes: int = 60) -> AnomalyReport:
        report = AnomalyReport()

        if not events:
            return report

        report.anomalies.extend(self._check_frequency_spikes(events))
        report.anomalies.extend(self._check_missing_expected_events(events))
        report.anomalies.extend(self._check_numeric_outliers(events))
        report.anomalies.extend(self._check_timestamp_gaps(events, window_minutes))

        return report

    # ── Checks ────────────────────────────────────────────────────────────────

    def _check_frequency_spikes(self, events: list[dict]) -> list[Anomaly]:
        counts = Counter(e.get("event_name") for e in events if e.get("event_name"))
        if len(counts) < 2:
            return []

        mean = sum(counts.values()) / len(counts)
        anomalies = []
        for event_name, count in counts.items():
            if mean > 0 and count / mean >= self._freq_threshold:
                anomalies.append(Anomaly(
                    anomaly_type="frequency_spike",
                    event_name=event_name,
                    field_path=None,
                    message=f"'{event_name}' fired {count}x vs batch mean of {mean:.1f} ({count/mean:.1f}x spike)",
                    severity="high" if count / mean >= self._freq_threshold * 2 else "medium",
                ))
        return anomalies

    def _check_missing_expected_events(self, events: list[dict]) -> list[Anomaly]:
        if not self._expected_events:
            return []
        seen = {e.get("event_name") for e in events}
        anomalies = []
        for expected in self._expected_events:
            if expected not in seen:
                anomalies.append(Anomaly(
                    anomaly_type="missing_expected_event",
                    event_name=expected,
                    field_path=None,
                    message=f"Expected event '{expected}' was not present in this batch",
                    severity="medium",
                ))
        return anomalies

    def _check_numeric_outliers(self, events: list[dict]) -> list[Anomaly]:
        """Z-score outlier detection on numeric property fields."""
        field_values: dict[str, list[float]] = {}
        for event in events:
            for key, val in event.get("properties", {}).items():
                if isinstance(val, (int, float)):
                    field_values.setdefault(key, []).append(float(val))

        anomalies = []
        for field_name, values in field_values.items():
            if len(values) < 5:
                continue
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            std = variance ** 0.5
            if std == 0:
                continue
            for val in values:
                z = abs((val - mean) / std)
                if z >= self._zscore_threshold:
                    anomalies.append(Anomaly(
                        anomaly_type="numeric_outlier",
                        event_name=None,
                        field_path=f"properties.{field_name}",
                        message=f"Value {val} for '{field_name}' is {z:.2f} std deviations from mean ({mean:.2f})",
                        severity="medium",
                    ))
        return anomalies

    def _check_timestamp_gaps(self, events: list[dict], window_minutes: int) -> list[Anomaly]:
        """Flag if all events are clustered outside the expected recency window."""
        timestamps = []
        for e in events:
            ts = e.get("occurred_at")
            if isinstance(ts, str):
                try:
                    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                except ValueError:
                    pass
            elif isinstance(ts, datetime):
                timestamps.append(ts)

        if not timestamps:
            return []

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=window_minutes)
        stale = [t for t in timestamps if t < cutoff]

        if len(stale) == len(timestamps):
            return [Anomaly(
                anomaly_type="stale_events",
                event_name=None,
                field_path="occurred_at",
                message=f"All {len(timestamps)} events are older than {window_minutes}min window — possible backfill or clock skew",
                severity="low",
            )]
        return []
