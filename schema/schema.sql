-- Data Quality Monitor Schema
-- Stores validation run results and individual event errors.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- One row per batch of events validated.
CREATE TABLE IF NOT EXISTS validation_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(100) NOT NULL,   -- e.g. 'server', 'frontend', 'ingestion_pipeline'
    total_events    INTEGER NOT NULL,
    valid_events    INTEGER NOT NULL,
    invalid_events  INTEGER NOT NULL,
    anomaly_count   INTEGER NOT NULL DEFAULT 0,
    error_rate_pct  NUMERIC(6,2) GENERATED ALWAYS AS (
                        ROUND(invalid_events::NUMERIC / NULLIF(total_events, 0) * 100, 2)
                    ) STORED,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

-- Individual validation errors per event.
CREATE TABLE IF NOT EXISTS validation_errors (
    error_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL REFERENCES validation_runs(run_id) ON DELETE CASCADE,
    event_name  VARCHAR(100),
    error_type  VARCHAR(50) NOT NULL CHECK (error_type IN ('schema', 'anomaly', 'missing_field', 'type_mismatch')),
    field_path  VARCHAR(200),
    message     TEXT NOT NULL,
    raw_event   JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_errors_run     ON validation_errors(run_id);
CREATE INDEX IF NOT EXISTS idx_validation_errors_type    ON validation_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_validation_errors_event   ON validation_errors(event_name);
CREATE INDEX IF NOT EXISTS idx_validation_runs_source    ON validation_runs(source);
CREATE INDEX IF NOT EXISTS idx_validation_runs_started   ON validation_runs(started_at DESC);

-- ── Analytics views ───────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW error_rate_by_source AS
SELECT
    source,
    SUM(total_events)   AS total_events,
    SUM(invalid_events) AS total_invalid,
    ROUND(SUM(invalid_events)::NUMERIC / NULLIF(SUM(total_events), 0) * 100, 2) AS error_rate_pct,
    DATE_TRUNC('day', started_at) AS day
FROM validation_runs
GROUP BY source, DATE_TRUNC('day', started_at)
ORDER BY day DESC, error_rate_pct DESC;

CREATE OR REPLACE VIEW top_error_types AS
SELECT
    event_name,
    error_type,
    field_path,
    COUNT(*) AS occurrences
FROM validation_errors
GROUP BY event_name, error_type, field_path
ORDER BY occurrences DESC;
