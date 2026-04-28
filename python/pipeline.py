"""
Validation pipeline: orchestrates schema validation + anomaly detection
and persists results to PostgreSQL.
"""
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

from validator import SchemaValidator, ValidationResult
from anomaly_detector import AnomalyDetector, AnomalyReport


def _get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "dq_monitor"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


@dataclass
class PipelineResult:
    run_id: uuid.UUID
    total: int
    valid: int
    invalid: int
    anomalies: int
    error_rate_pct: float


class ValidationPipeline:
    def __init__(
        self,
        source: str,
        validator: SchemaValidator | None = None,
        detector: AnomalyDetector | None = None,
    ):
        self._source = source
        self._validator = validator or SchemaValidator()
        self._detector = detector or AnomalyDetector()

    def run(self, events: list[dict[str, Any]]) -> PipelineResult:
        run_id = uuid.uuid4()
        started_at = datetime.now(timezone.utc)

        validation_results: list[ValidationResult] = self._validator.validate_batch(events)
        valid_events = [e for e, r in zip(events, validation_results) if r.is_valid]
        anomaly_report: AnomalyReport = self._detector.analyze(valid_events)

        total = len(events)
        invalid = sum(1 for r in validation_results if not r.is_valid)
        valid = total - invalid
        anomaly_count = len(anomaly_report.anomalies)
        error_rate = round(invalid / total * 100, 2) if total else 0.0

        self._persist(
            run_id, started_at, total, valid, invalid,
            anomaly_count, validation_results, anomaly_report,
        )

        return PipelineResult(run_id, total, valid, invalid, anomaly_count, error_rate)

    def _persist(
        self,
        run_id: uuid.UUID,
        started_at: datetime,
        total: int,
        valid: int,
        invalid: int,
        anomaly_count: int,
        validation_results: list[ValidationResult],
        anomaly_report: AnomalyReport,
    ) -> None:
        conn = _get_conn()
        psycopg2.extras.register_uuid()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO validation_runs
                        (run_id, source, total_events, valid_events, invalid_events,
                         anomaly_count, started_at, completed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, self._source, total, valid, invalid, anomaly_count,
                     started_at, datetime.now(timezone.utc)),
                )

                for result in validation_results:
                    for err in result.errors:
                        cur.execute(
                            """
                            INSERT INTO validation_errors
                                (run_id, event_name, error_type, field_path, message, raw_event)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                run_id,
                                result.event_name,
                                err.error_type,
                                err.field_path,
                                err.message,
                                psycopg2.extras.Json(result.raw_event),
                            ),
                        )

                for anomaly in anomaly_report.anomalies:
                    cur.execute(
                        """
                        INSERT INTO validation_errors
                            (run_id, event_name, error_type, field_path, message)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            run_id,
                            anomaly.event_name,
                            "anomaly",
                            anomaly.field_path,
                            f"[{anomaly.severity.upper()}] {anomaly.message}",
                        ),
                    )

            conn.commit()
        finally:
            conn.close()
