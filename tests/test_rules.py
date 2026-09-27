from copy import deepcopy

import pytest

from packages.rules import amount, perceptual_hash_distance, validate_document


@pytest.fixture
def clean():
    doc = {"id": "a", "type": "invoice", "vendor": "Example Supplies", "vendor_master": ["Example Supplies"], "po_number": "PO-123", "po_reference": {"number": "PO-123", "total": 11}, "source": "generated"}
    fields = {"vendor": "Example Supplies", "number": "INV-123", "date": "2026-01-01", "due_date": "2026-01-31", "currency": "USD", "subtotal": 10, "tax": 1, "total": 11, "po_number": "PO-123"}
    return doc, fields, [{"amount": 10}]


@pytest.mark.parametrize("rule", ["arithmetic", "dates", "currency", "vendor", "purchase_order", "duplicate"])
def test_rule_clean_pass(clean, rule):
    results = validate_document(*clean)
    assert next(item for item in results if item["id"] == rule)["status"] == "pass"


@pytest.mark.parametrize("rule,field,value", [("arithmetic", "total", 12), ("dates", "due_date", "2025-01-01"), ("currency", "currency", "ZZZ"), ("vendor", "vendor", "Unlisted Vendor"), ("purchase_order", "po_number", "PO-WRONG"), ("duplicate", "number", "INV-123")])
def test_rule_deliberate_defect(clean, rule, field, value):
    doc, fields, rows = deepcopy(clean)
    fields[field] = value
    known = [{"id": "independent", "vendor": fields["vendor"], "number": fields["number"], "total": fields["total"]}] if rule == "duplicate" else []
    result = next(item for item in validate_document(doc, fields, rows, known_documents=known) if item["id"] == rule)
    assert result["status"] == "fail"


@pytest.mark.parametrize("rule", ["arithmetic", "dates", "currency", "vendor", "purchase_order", "duplicate"])
def test_rule_refuses_empty(rule):
    result = next(item for item in validate_document({}, {}, []) if item["id"] == rule)
    assert result["status"] == "fail"


def test_independent_duplicate_evidence(clean):
    doc, fields, rows = clean
    other = {"id": "b", "vendor": fields["vendor"], "number": fields["number"], "total": fields["total"]}
    result = validate_document(doc, fields, rows, known_documents=[other])
    assert result[-1]["status"] == "fail"


def test_line_extension_must_reconcile(clean):
    doc, fields, _ = clean
    results = validate_document(doc, fields, [{"amount": 10, "quantity": 2, "unit_price": 6}])
    assert results[0]["status"] == "fail"


def test_date_window_is_deterministic(clean):
    doc, fields, rows = clean
    doc["as_of"] = "2025-12-31"
    assert validate_document(doc, fields, rows)[1]["status"] == "fail"


def test_currency_and_po_master_checks(clean):
    doc, fields, rows = clean
    doc["vendor_currencies"] = {"Example Supplies": "EUR"}
    doc["po_reference"] = {"number": "PO-123", "total": 12}
    results = validate_document(doc, fields, rows)
    assert results[2]["status"] == "fail"
    assert results[4]["status"] == "fail"


def test_amount_rejects_nonfinite():
    assert amount("NaN") is None
    assert amount("Infinity") is None
    assert str(amount("1,234.50")) == "1234.50"


def test_hash_distance_symmetric():
    assert perceptual_hash_distance("0f", "fc") == perceptual_hash_distance("fc", "0f")
    with pytest.raises(ValueError):
        perceptual_hash_distance("", "")


def test_injected_labels_are_not_detection_evidence(clean):
    doc, fields, rows = clean
    doc["duplicate_of"] = "some-document"
    doc["defects"] = ["duplicate"]
    assert validate_document(doc, fields, rows)[-1]["status"] == "pass"


def test_fields_cannot_verify_their_own_vendor_or_purchase_order(clean):
    doc, fields, rows = clean
    doc.pop("vendor_master")
    doc.pop("po_reference")
    results = validate_document(doc, fields, rows)
    assert results[3]["status"] == "fail"
    assert results[4]["status"] == "fail"
