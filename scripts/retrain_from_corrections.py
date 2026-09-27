"""Retrain from an explicit provenance selection, preserving the frozen benchmark.

Example with your optional local API:
  python scripts/retrain_from_corrections.py --api-url http://127.0.0.1:8080 --provenance client_declared_human
The write token is read from DOCKET_WRITE_TOKEN, never from a command-line value.
An offline API export can instead be supplied using --corrections path/to/export.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.api.store import correction_records_digest
from packages.pipeline import retrain_from_corrections

PROVENANCE_KINDS = ("client_declared_human", "simulated_ground_truth", "integration_test", "unspecified")


def select_records(export: dict[str, Any], provenance: str) -> list[dict[str, Any]]:
    if export.get("schema_version") != 1 or not isinstance(export.get("records"), list):
        raise ValueError("Expected a schema_version 1 correction export with records")
    records = export["records"]
    if provenance != "all":
        records = [record for record in records if record.get("provenance", {}).get("kind", "unspecified") == provenance]
    if not records:
        raise ValueError("No accepted corrections match the explicitly selected provenance")
    if any(record.get("decision") != "accept" for record in records):
        raise ValueError("The export includes records that were not accepted")
    return list(records)


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.api_url:
        parsed = urlparse(args.api_url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError("API URL must be HTTP(S), with credentials supplied only through the token environment variable")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Use HTTPS for a non-loopback API so the review token is protected")
        token = os.environ.get(args.token_env, "")
        if not token:
            raise ValueError(f"Set the {args.token_env} environment variable for API access")
        with httpx.Client(base_url=args.api_url.rstrip("/"), headers={"Authorization": f"Bearer {token}"}, timeout=600) as client:
            response = client.get("/v1/corrections/export")
            response.raise_for_status()
            export = response.json()
            records = select_records(export, args.provenance)
            digest = correction_records_digest(records)
            response = client.post("/v1/retrain", json={"provenance_kinds": None if args.provenance == "all" else [args.provenance], "expected_records_sha256": digest})
            response.raise_for_status()
            report: dict[str, Any] = response.json()
    else:
        export = json.loads(Path(args.corrections).read_text(encoding="utf-8"))
        records = select_records(export, args.provenance)
        report = retrain_from_corrections(records)
        report["correction_records_sha256"] = correction_records_digest(records)
    directory = Path(args.output) if args.output else ROOT / "artifacts/retrain-command" / uuid.uuid4().hex[:12]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "corrections.json").write_text(json.dumps({**export, "records": records, "count": len(records),
        "records_sha256": correction_records_digest(records), "provenance_selection": args.provenance}, indent=2), encoding="utf-8")
    (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--api-url", help="Optional API to export from and retrain on")
    source.add_argument("--corrections", help="Previously exported accepted correction JSON")
    parser.add_argument("--provenance", required=True, choices=("all", *PROVENANCE_KINDS), help="Filter existing provenance; never relabel the source")
    parser.add_argument("--token-env", default="DOCKET_WRITE_TOKEN")
    parser.add_argument("--output", help="Directory for the exact selected corrections and report; defaults under ignored artifacts/")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), indent=2))
    except (ValueError, httpx.HTTPError) as exc:
        parser.exit(1, f"Retrain failed: {exc}\n")


if __name__ == "__main__":
    main()
