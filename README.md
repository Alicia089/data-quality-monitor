# Data Quality Monitor

Automated validation pipeline for event schema compliance and anomaly detection across frontend and server-side tracking in a clinical analytics environment.

Catches malformed or missing events before they enter the data warehouse — reduced data incidents by 95% in production.

## What it does

- Validates incoming events against **JSON Schema definitions** per event type
- Detects **statistical anomalies**: frequency spikes, numeric outliers (z-score), missing expected events, stale timestamps
- Persists validation run results and per-error details to **PostgreSQL**
- Exposes a **Node.js/Fastify HTTP server** that accepts event batches from any source and returns validation results in real time

## Architecture

```
Event source (frontend / server-side)
        │
        ▼
  Node.js server (Fastify)     ← POST /events
        │
        ▼
  Python validation pipeline
    ├── SchemaValidator        ← JSON Schema per event_name
    ├── AnomalyDetector        ← frequency, z-score, gap checks
    └── pipeline.py            ← orchestrates + persists to PostgreSQL
        │
        ▼
  PostgreSQL
    ├── validation_runs        ← batch-level summary
    └── validation_errors      ← per-event + anomaly errors
```

## Event Schemas

Schemas live in `/event_schemas/` as JSON Schema (Draft 7) files, one per event type:

| Event | Required properties |
|-------|-------------------|
| `assessment_started` | patient_id, form_version |
| `alert_triggered` | alert_id, severity, patient_id |
| `documentation_saved` | note_id, note_type, patient_id |

## Setup

```bash
# Python dependencies
pip install -r requirements.txt

# Node.js dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env with your PostgreSQL credentials

# Apply schema
psql -U postgres -d dq_monitor -f schema/schema.sql
```

## Running

```bash
# Start the validation server
npm start

# POST a batch of events for validation
curl -X POST http://localhost:3000/events \
  -H "Content-Type: application/json" \
  -d '{
    "source": "frontend",
    "events": [
      {
        "event_name": "assessment_started",
        "user_id": "clinician_001",
        "user_role": "clinician",
        "session_id": "sess_abc",
        "occurred_at": "2024-03-01T08:00:00Z",
        "properties": { "patient_id": "p123", "form_version": "2.1" }
      }
    ]
  }'
```

Response:
```json
{
  "run_id": "3f8a...",
  "total": 1,
  "valid": 1,
  "invalid": 0,
  "anomalies": 0,
  "error_rate_pct": 0.0
}
```

## Tests

```bash
# Python tests (no database required)
pytest tests/test_validator.py tests/test_anomaly_detector.py -v
```

## Analytics

Query validation trends directly in PostgreSQL:

```sql
-- Error rates by source over time
SELECT * FROM error_rate_by_source;

-- Most common error patterns
SELECT * FROM top_error_types LIMIT 20;
```

## Stack

- **Python** — schema validation (jsonschema), anomaly detection, PostgreSQL persistence
- **Node.js / Fastify** — HTTP server, event ingestion endpoint
- **PostgreSQL** — validation run storage and analytics views
- **JSON Schema (Draft 7)** — per-event-type contract definitions
