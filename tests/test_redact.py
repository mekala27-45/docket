import io
import json

import pytest
from PIL import Image, ImageDraw

from packages.redact import PLANTED_IDENTIFIERS, redact_image, redact_payload, redact_text, scan_text


def test_redaction_clean_pass():
    payload, report = redact_payload({"vendor": "Example Supplies", "total": 12})
    assert payload["vendor"] == "Example Supplies"
    assert report["text_values_redacted"] == 0
    assert scan_text(json.dumps(payload)) == []


def test_redaction_planted_defect():
    payload, report = redact_payload({"trace": [{"detail": value} for value in PLANTED_IDENTIFIERS]})
    assert scan_text(json.dumps(payload)) == []
    assert report["text_values_redacted"] == len(PLANTED_IDENTIFIERS)
    assert scan_text("Plant: " + PLANTED_IDENTIFIERS[0])


def test_scan_refuses_nothing():
    with pytest.raises(ValueError):
        scan_text(" ")


def test_image_redacts_identifier_split_across_tokens():
    canvas = Image.new("RGB", (600, 120), "white")
    drawing = ImageDraw.Draw(canvas)
    drawing.text((10, 20), PLANTED_IDENTIFIERS[0], fill="black")
    original = io.BytesIO()
    canvas.save(original, format="PNG")
    tokens = [{"text": "4111", "box": [0.01, 0.1, 0.15, 0.5]}] + [
        {"text": "1111", "box": [0.16 + index * 0.15, 0.1, 0.15, 0.5]} for index in range(3)
    ]
    raw, cleaned, report = redact_image(original.getvalue(), tokens)
    assert all(token["text"] == "[REDACTED]" for token in cleaned)
    assert report["tokens_redacted"] == 4
    assert Image.open(io.BytesIO(raw)).getpixel((20, 30)) == (0, 0, 0)
    assert tokens[0]["text"] == "4111"


def test_image_refuses_no_ocr():
    with pytest.raises(ValueError):
        redact_image(b"unparsed", [])


def test_identifier_patterns():
    for value in PLANTED_IDENTIFIERS:
        assert value not in redact_text(value)
    assert "name@example.com" not in redact_text("name@example.com")
