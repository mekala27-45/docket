"""Scan published text and independently read/re-OCR a stored redaction probe."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.api.store import Audit, Base, Correction, Document, make_engine
from packages.ocr import recognize
from packages.redact import PLANTED_IDENTIFIERS, redact_image, redact_payload, scan_text


def scan_artifacts(paths: list[Path]) -> dict[str, Any]:
    files = [path for path in paths if path.is_file() and path.stat().st_size > 0]
    if not files:
        raise ValueError("At least one nonempty published artifact is required")
    failures = []
    scanned = 0
    for path in files:
        contents = path.read_text(encoding="utf-8", errors="replace")
        if not contents.strip():
            continue
        scanned += 1
        if scan_text(contents):
            failures.append(str(path))
    if scanned == 0:
        raise ValueError("Cannot pass an empty artifact scan")
    return {"artifacts_scanned": scanned, "failures": failures}


def scan_database(url: str) -> dict[str, Any]:
    """Open an independent engine and examine stored payloads and decoded pixels."""
    engine = make_engine(url)
    checked = images = 0
    failures: list[str] = []
    try:
        with Session(engine) as session:
            for document in session.scalars(select(Document)):
                checked += 1
                if scan_text(json.dumps(document.payload)):
                    failures.append("document-payload")
                if document.image:
                    images += 1
                    result = recognize(Image.open(io.BytesIO(document.image)).convert("RGB"))
                    text = " ".join(token["text"] for token in result["tokens"])
                    if text.strip() and scan_text(text):
                        failures.append("document-image")
            for correction in session.scalars(select(Correction)):
                checked += 1
                if scan_text(json.dumps({"fields": correction.fields, "line_items": correction.line_items})):
                    failures.append("correction")
            for event in session.scalars(select(Audit)):
                checked += 1
                if scan_text(json.dumps(event.detail)):
                    failures.append("audit")
    finally:
        engine.dispose()
    if checked == 0:
        raise ValueError("Cannot pass an empty database scan")
    return {"database_rows_scanned": checked, "stored_images_reocr": images, "failures": failures}


def image_probe() -> dict[str, Any]:
    """Require visible planted identifiers before redaction and absence afterward."""
    canvas = Image.new("RGB", (1500, 500), "white")
    drawing = ImageDraw.Draw(canvas)
    drawing.text((45, 35), "DEMONSTRATION PRIVACY PROBE", fill="black", font_size=40)
    for index, identifier in enumerate(PLANTED_IDENTIFIERS):
        drawing.text((45, 135 + index * 90), identifier, fill="black", font_size=48)
    before = recognize(canvas)
    original_text = " ".join(token["text"] for token in before["tokens"])
    if len(scan_text(original_text)) != len(PLANTED_IDENTIFIERS):
        raise AssertionError("The OCR baseline did not read every planted identifier; the probe is inconclusive")
    buffer = io.BytesIO()
    canvas.save(buffer, "PNG")
    pixels, tokens, report = redact_image(buffer.getvalue(), before["tokens"])
    payload, _ = redact_payload({"id": "privacy-probe", "tokens": tokens, "trace": original_text})
    with tempfile.TemporaryDirectory(prefix="docket-privacy-") as directory:
        url = "sqlite:///" + (Path(directory) / "probe.sqlite3").as_posix()
        writer = make_engine(url)
        Base.metadata.create_all(writer)
        with Session(writer) as session, session.begin():
            session.add(Document(id="privacy-probe", payload=payload, image=pixels, source="upload"))
            session.add(Audit(document_id="privacy-probe", action="upload", detail=report))
        writer.dispose()
        result = scan_database(url)
    if result["failures"]:
        raise AssertionError("A planted identifier survived redaction")
    return {**result, "planted_identifiers_observed_before": len(PLANTED_IDENTIFIERS), "redacted_tokens": report["tokens_redacted"], "ocr_engine": before["engine"], "ocr_version": before["version"]}


def main() -> None:
    candidates: list[Path] = []
    for base in [ROOT / "results", ROOT / "report", ROOT / "docs", ROOT / "web/out", ROOT / "web/public/data"]:
        if base.exists():
            candidates.extend(path for path in base.rglob("*") if path.suffix in {".json", ".md", ".html", ".txt", ".csv", ".js"})
    candidates.extend(path for path in [ROOT / "README.md", ROOT / "RESULTS.md"] if path.exists())
    artifacts = scan_artifacts(candidates)
    probe = image_probe()
    existing = scan_database(os.environ["DATABASE_URL"]) if os.environ.get("DATABASE_URL") else None
    failures = artifacts["failures"] + probe["failures"] + (existing["failures"] if existing else [])
    print(json.dumps({"status": "fail" if failures else "pass", "published": artifacts, "stored_image_probe": probe, "configured_database": existing}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
