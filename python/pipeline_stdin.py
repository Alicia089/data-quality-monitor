"""
Entry point for the Node.js → Python bridge.
Reads a JSON payload from stdin, runs the validation pipeline, writes result to stdout.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from pipeline import ValidationPipeline


def main():
    payload = json.load(sys.stdin)
    source = payload.get("source", "unknown")
    events = payload.get("events", [])

    pipeline = ValidationPipeline(source=source)
    result = pipeline.run(events)

    output = {
        "run_id": str(result.run_id),
        "total": result.total,
        "valid": result.valid,
        "invalid": result.invalid,
        "anomalies": result.anomalies,
        "error_rate_pct": result.error_rate_pct,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
