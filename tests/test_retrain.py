import hashlib

import pytest

from packages.core import FIELDS, ROOT, read_json
from packages.extract.tokens import MODEL_PATH
from packages.pipeline import correction_document, retrain_from_corrections


def test_retrain_requires_corrections_and_rejects_frozen_test():
    with pytest.raises(ValueError, match="at least one"):
        retrain_from_corrections([])
    with pytest.raises(ValueError, match="frozen test"):
        retrain_from_corrections([{"document": {"id": "gen-0072"}}])


def test_corrections_align_only_supplied_truth():
    result = correction_document({"document": {"id": "new", "tokens": [
        {"text": "Morrow", "label": "total"}, {"text": "Supply"}, {"text": "50.00"}]},
        "fields": {"vendor": "Morrow Supply", "total": {"value": 50}}, "line_items": []})
    assert [t["label"] for t in result["tokens"]] == ["vendor", "vendor", "total"]
    assert result["split"] == "correction"


def test_retrain_isolated_from_canonical_artifact():
    document = read_json(ROOT / "data/dataset.json")[48]
    before_hash = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    report = retrain_from_corrections([{"document": document,
        "fields": {f: document[f] for f in FIELDS}, "line_items": document["line_items"]}])
    assert hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() == before_hash
    assert report["canonical_model_changed"] is False
    assert report["model_path"].startswith("artifacts/retrained/")
    assert (ROOT / report["model_path"]).exists()
    assert report["split"] == "test" and report["n_test"] == 44
