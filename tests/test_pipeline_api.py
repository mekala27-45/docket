import io

import pytest
from PIL import Image

from packages import pipeline


@pytest.fixture
def pipeline_dependencies(tmp_path, monkeypatch):
    class Calibration:
        def apply(self, extraction):
            for field in extraction["fields"].values():
                field["confidence"] = 0.5
                field["calibration_sentence"] = "Fixture calibrator"

    monkeypatch.setattr(pipeline.FieldCalibrator, "load", lambda: Calibration())
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "CLASSIFIER_PATH", tmp_path / "missing-classifier.pkl")
    buffer = io.BytesIO()
    Image.new("RGB", (1000, 1200), "white").save(buffer, "PNG")
    return buffer.getvalue()


def test_image_pipeline_calls_ocr_and_returns_ephemeral_pixels(pipeline_dependencies, monkeypatch):
    called = []

    def recognize(image):
        called.append(image.size)
        return {"tokens": [{"text": "Total:", "box": [0.1, 0.3, 0.1, 0.02], "confidence": 0.9}, {"text": "108.00", "box": [0.3, 0.3, 0.1, 0.02], "confidence": 0.9}], "engine": "tesseract"}

    monkeypatch.setattr(pipeline, "recognize", recognize)
    result = pipeline.process_image(pipeline_dependencies, "upload.png")
    assert called == [(1000, 1200)]
    assert result["source"] == "upload" and result["ocr_engine"] == "tesseract"
    assert result["_image_bytes"].startswith(b"\x89PNG")
    assert result["status"] == "needs_review"
    assert result["tokens"][1]["text"] == "108.00"
    assert {"vendor", "number", "currency", "total", "line_items"}.issubset(result)
    assert isinstance(result["vendor"], str) and result["vendor"]
    assert next(rule for rule in result["rules"] if rule["id"] == "vendor")["status"] == "fail"


def test_image_pipeline_refuses_unavailable_ocr(pipeline_dependencies, monkeypatch):
    def unavailable(image):
        raise RuntimeError("Unavailable test engine")

    monkeypatch.setattr(pipeline, "recognize", unavailable)
    with pytest.raises(RuntimeError, match="raw upload was not stored"):
        pipeline.process_image(pipeline_dependencies, "upload.png")


def test_image_pipeline_refuses_empty_ocr(pipeline_dependencies, monkeypatch):
    monkeypatch.setattr(pipeline, "recognize", lambda image: {"tokens": []})
    with pytest.raises(RuntimeError, match="no words"):
        pipeline.process_image(pipeline_dependencies, "upload.png")


def test_process_document_records_backend_and_trace(pipeline_dependencies):
    document = {"id": "seed", "type": "invoice", "tokens": [], "source": "generated"}
    result = pipeline.process_document(document)
    assert result["extraction"]["backend"] == "rules"
    assert result["extraction"]["ocr_engine"] == "gold"
    for field in result["extraction"]["fields"].values():
        assert field["trace"][-2]["step"] == "business_rules"
        assert field["trace"][-1]["step"] == "routing"
    assert "extraction" not in document
