"""Shared, deterministic normalization and document contracts."""

import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[2]
SEED = 11027
FIELDS = ("vendor", "number", "date", "due_date", "currency", "po_number", "subtotal", "tax", "total")
AMOUNTS = {"subtotal", "tax", "total", "amount", "unit_price", "quantity"}
STATEMENT = "Demonstration documents: fictional invoices and public CORD receipts. No customer transactions."


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def amount(value: Any) -> Decimal | None:
    """Parse US decimals and CORD's Indonesian dot thousands consistently."""
    if value is None or isinstance(value, bool):
        return None
    text = re.sub(r"[^0-9.,+-]", "", str(value))
    if not text or not re.search(r"\d", text):
        return None
    if re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")
    elif re.fullmatch(r"[+-]?\d+,\d{1,2}", text):
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def normalize(value: Any, field: str = "") -> str:
    if value is None:
        return ""
    if field in AMOUNTS:
        parsed = amount(value)
        return str(parsed) if parsed is not None else ""
    text = " ".join(str(value).strip().casefold().split())
    if field in {"date", "due_date"}:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
    return text


def matches(left: Any, right: Any, field: str = "") -> bool:
    return bool(normalize(right, field)) and normalize(left, field) == normalize(right, field)


def required_fields(doc_type: str) -> tuple[str, ...]:
    if doc_type == "receipt":
        return ("total",)
    if doc_type == "purchase_order":
        return ("vendor", "number", "date", "currency", "subtotal", "tax", "total")
    if doc_type == "invoice":
        return ("vendor", "number", "date", "due_date", "currency", "subtotal", "tax", "total")
    return ()


def union_box(tokens: list[dict[str, Any]]) -> list[float] | None:
    if not tokens:
        return None
    boxes = [t["box"] for t in tokens]
    x, y = min(b[0] for b in boxes), min(b[1] for b in boxes)
    return [x, y, max(b[0] + b[2] for b in boxes) - x, max(b[1] + b[3] for b in boxes) - y]


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any) -> None:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def utc_today() -> str:
    return date.today().isoformat()
