"""Deterministic accounts payable checks; missing evidence never passes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

RULES = {
    "arithmetic": "Amounts reconcile",
    "dates": "Document dates are consistent",
    "currency": "Currency is supported",
    "vendor": "Vendor is in the master",
    "purchase_order": "Purchase order matches",
    "duplicate": "Document has no known duplicate",
}
SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "IDR", "CAD", "AUD", "JPY"}


def amount(value: Any) -> Decimal | None:
    """Parse a finite monetary value without binary floating point arithmetic."""
    try:
        parsed = Decimal(str(value).replace(",", "").strip())
        return parsed if parsed.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def perceptual_hash_distance(first: str, second: str) -> int:
    if not first or not second or len(first) != len(second):
        raise ValueError("Comparable nonempty hashes are required")
    return (int(first, 16) ^ int(second, 16)).bit_count()


def validate_document(
    document: dict[str, Any],
    fields: dict[str, Any],
    line_items: list[dict[str, Any]],
    *,
    known_documents: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Evaluate six policy checks against supplied evidence and known documents.

    A generated document's vendor and PO act as its reference master record.
    Uploaded documents need explicit vendor/PO verification to pass those checks.
    """
    values = {key: val.get("value") if isinstance(val, dict) else val for key, val in fields.items()}
    output: list[dict[str, str]] = []

    def add(rule: str, status: str, message: str) -> None:
        output.append({"id": rule, "name": RULES[rule], "status": status, "message": message})

    subtotal, tax, total = (amount(values.get(key)) for key in ("subtotal", "tax", "total"))
    rows = [amount(row.get("amount")) for row in line_items]
    if subtotal is None or tax is None or total is None or not rows or any(row is None for row in rows):
        add("arithmetic", "fail", "Subtotal, tax, total and complete line amounts are required.")
    else:
        row_sum = sum((row for row in rows if row is not None), Decimal(0))
        valid = abs(subtotal + tax - total) <= Decimal("0.02") and abs(row_sum - subtotal) <= Decimal("0.02")
        for row in line_items:
            quantity, unit, row_amount = (amount(row.get(key)) for key in ("quantity", "unit_price", "amount"))
            if "quantity" in row or "unit_price" in row:
                valid &= quantity is not None and unit is not None and row_amount is not None
                if quantity is not None and unit is not None and row_amount is not None:
                    valid &= abs(quantity * unit - row_amount) <= Decimal("0.02")
        add("arithmetic", "pass" if valid else "fail", "Subtotal plus tax and line sum must reconcile within 0.02.")

    try:
        issued = date.fromisoformat(str(values.get("date", "")))
        due_value = values.get("due_date")
        valid_date = not due_value or date.fromisoformat(str(due_value)) >= issued
        if document.get("type") == "invoice" and not due_value:
            valid_date = False
        if document.get("as_of"):
            as_of = date.fromisoformat(str(document["as_of"]))
            valid_date &= 0 <= (as_of - issued).days <= int(document.get("max_age_days", 730))
        add("dates", "pass" if valid_date else "fail", "An invoice needs a due date on or after its issue date.")
    except ValueError:
        add("dates", "fail", "A valid ISO issue date is required.")

    valid_currency = str(values.get("currency", "")).upper() in SUPPORTED_CURRENCIES
    vendor_currencies = document.get("vendor_currencies", {})
    expected_currency = vendor_currencies.get(str(values.get("vendor", "")))
    if expected_currency:
        valid_currency &= values.get("currency") == expected_currency
    add("currency", "pass" if valid_currency else "fail", "Currency must be a supported ISO currency code.")

    vendor = str(values.get("vendor") or "").strip().casefold()
    master = document.get("vendor_master", [document.get("vendor")] if document.get("source") != "upload" else [])
    known = {str(item).strip().casefold() for item in master if item}
    valid_vendor = bool(vendor and vendor in known)
    add("vendor", "pass" if valid_vendor else "fail", "Extracted vendor must match the supplied vendor master.")

    po_value = str(values.get("po_number") or "").strip()
    reference = document.get("po_reference", {})
    po_reference = str(reference.get("number", document.get("po_number")) or "").strip()
    if document.get("type") == "receipt" and values:
        add("purchase_order", "not_applicable", "Receipts do not require a purchase order.")
    else:
        valid_po = bool(po_value and po_reference and po_value == po_reference)
        if reference.get("total") is not None:
            expected_total = amount(reference["total"])
            valid_po &= expected_total is not None and total is not None
            if expected_total is not None and total is not None:
                valid_po &= abs(expected_total - total) <= Decimal("0.02")
        add("purchase_order", "pass" if valid_po else "fail", "Purchase order must match the supplied PO record.")

    number = str(values.get("number") or "").strip().casefold()
    duplicate = bool(document.get("duplicate_of"))
    for other in known_documents or []:
        if other.get("id") == document.get("id"):
            continue
        if number and vendor and number == str(other.get("number") or "").strip().casefold():
            other_total = amount(other.get("total"))
            duplicate |= vendor == str(other.get("vendor") or "").strip().casefold() and total is not None and other_total is not None and abs(total - other_total) <= Decimal("0.02")
        first, second = document.get("perceptual_hash"), other.get("perceptual_hash")
        if first and second:
            duplicate |= perceptual_hash_distance(str(first), str(second)) <= 3
    add("duplicate", "pass" if number and vendor and not duplicate else "fail", "Vendor plus number and image hash are checked against stored documents.")
    return output
