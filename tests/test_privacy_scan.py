import io
import shutil

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from packages.api.store import Audit, Base, Correction, Document, make_engine
from scripts.scan_for_planted_identifiers import image_probe, scan_artifacts, scan_database


def test_artifact_scan_clean_pass(tmp_path):
    artifact = tmp_path / "report.md"
    artifact.write_text("Demonstration invoices contain fictional transactions.", encoding="utf-8")
    assert scan_artifacts([artifact])["failures"] == []


def test_artifact_scan_deliberate_violation(tmp_path):
    artifact = tmp_path / "report.md"
    artifact.write_text("Identifier: 987-65-4321", encoding="utf-8")
    assert scan_artifacts([artifact])["failures"] == [str(artifact)]


def test_artifact_scan_refuses_nothing():
    with pytest.raises(ValueError):
        scan_artifacts([])


def test_database_scan_uses_independent_connection(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'probe.sqlite'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    output = io.BytesIO()
    Image.new("RGB", (30, 30), "white").save(output, "PNG")
    with Session(engine) as session, session.begin():
        session.add(Document(id="probe", payload={"vendor": "Example Supplies"}, source="generated", image=output.getvalue()))
        session.flush()
        session.add(Correction(document_id="probe", fields={"total": 10}, line_items=[], decision="accept"))
        session.add(Audit(document_id="probe", action="review", detail={"decision": "accept"}))
    monkeypatch.setattr("scripts.scan_for_planted_identifiers.recognize", lambda image: {"tokens": [{"text": "safe"}]})
    result = scan_database(url)
    assert result == {"database_rows_scanned": 3, "stored_images_reocr": 1, "failures": []}
    engine.dispose()


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract unavailable on host; required in pipeline container")
def test_real_ocr_planted_identifiers_removed_from_stored_pixels():
    result = image_probe()
    assert result["planted_identifiers_observed_before"] == 3
    assert result["stored_images_reocr"] == 1
    assert result["failures"] == []
