"""Pattern redaction for demonstration uploads, before any database or image write."""

from __future__ import annotations

import copy
import io
import math
import re
from typing import Any

from PIL import Image, ImageDraw

PATTERNS = [
    re.compile(r"(?<!\d)\d{3}[- ]\d{2}[- ]\d{4}(?!\d)"),
    re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
    re.compile(r"(?i)\b(?:account|acct|iban|routing|tax[ -]?id|identifier)\s*[:#-]?\s*[A-Z]{0,2}[\d -]{6,34}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
]
PLANTED_IDENTIFIERS = ("4111 1111 1111 1111", "987-65-4321", "account: 9876543210")
REPLACEMENT = "[REDACTED]"


def sensitive_spans(text: str) -> list[tuple[int, int]]:
    return sorted({match.span() for pattern in PATTERNS for match in pattern.finditer(text)})


def redact_text(text: str) -> str:
    for pattern in PATTERNS:
        text = pattern.sub(REPLACEMENT, text)
    return text


def redact_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Remove matching strings from every nested value, including traces."""
    changed = 0

    def walk(value: Any) -> Any:
        nonlocal changed
        if isinstance(value, str):
            result = redact_text(value)
            changed += int(result != value)
            return result
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {str(key): walk(item) for key, item in value.items()}
        if isinstance(value, int) and not isinstance(value, bool) and sensitive_spans(str(value)):
            changed += 1
            return REPLACEMENT
        return value

    result: dict[str, Any] = walk(payload)
    return result, {"text_values_redacted": changed, "method": "pattern rules", "raw_persisted": False}


def redact_image(
    image_bytes: bytes, tokens: list[dict[str, Any]]
) -> tuple[bytes, list[dict[str, Any]], dict[str, Any]]:
    """Black out complete OCR token boxes overlapping a detected identifier.

    Joining tokens catches card/account identifiers split into separate OCR words.
    Coordinates are normalized x, y, width, height. Images are re-encoded to strip
    EXIF and other metadata. This is pattern coverage, not a guarantee to find all PII.
    """
    if not tokens:
        raise ValueError("OCR tokens are required before upload storage")
    cleaned = copy.deepcopy(tokens)
    joined = " ".join(str(token.get("text", "")) for token in tokens)
    spans = sensitive_spans(joined)
    with Image.open(io.BytesIO(image_bytes)) as source:
        canvas = source.convert("RGB")
    drawing = ImageDraw.Draw(canvas)
    cursor = 0
    redacted = 0
    for original, token in zip(tokens, cleaned, strict=True):
        text = str(original.get("text", ""))
        end = cursor + len(text)
        if any(start < end and stop > cursor for start, stop in spans):
            box = original.get("box")
            if not isinstance(box, list) or len(box) != 4:
                raise ValueError("Sensitive OCR token has no usable image box")
            x, y, width, height = (float(value) for value in box)
            if not all(math.isfinite(value) for value in (x, y, width, height)) or width <= 0 or height <= 0 or x < 0 or y < 0 or x + width > 1.001 or y + height > 1.001:
                raise ValueError("Sensitive OCR token has an invalid image box")
            padding = 3
            drawing.rectangle(
                (max(0, int(x * canvas.width) - padding), max(0, int(y * canvas.height) - padding),
                 min(canvas.width, int((x + width) * canvas.width) + padding),
                 min(canvas.height, int((y + height) * canvas.height) + padding)),
                fill="black",
            )
            token["text"] = REPLACEMENT
            redacted += 1
        cursor = end + 1
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue(), cleaned, {"tokens_redacted": redacted, "method": "pattern rules with OCR boxes", "raw_persisted": False}


def scan_text(text: str, identifiers: tuple[str, ...] = PLANTED_IDENTIFIERS) -> list[str]:
    """Return planted values found, rejecting an empty scan as uninformative."""
    if not text.strip():
        raise ValueError("Cannot scan an empty artifact")
    # Allow identifier separators without joining unrelated JSON values or
    # interpreting the digits of a fractional OCR coordinate as a card number.
    found = []
    for value in identifiers:
        digits = re.sub(r"\D", "", value)
        pattern = r"(?<![\d.])" + r"[\s-]*".join(digits) + r"(?![\d.])"
        if re.search(pattern, text):
            found.append(value)
    return found
