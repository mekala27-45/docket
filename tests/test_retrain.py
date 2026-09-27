import copy
import hashlib

import pytest

from packages.core import FIELDS, ROOT, read_json
from packages.extract.tokens import MODEL_PATH, TokenExtractor
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
    dataset = read_json(ROOT / "data/dataset.json")
    document = next(item for item in dataset if item["source"] == "generated" and item["split"] == "validation")
    before_hash = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    report = retrain_from_corrections([{"document": document,
        "fields": {f: document[f] for f in FIELDS}, "line_items": document["line_items"],
        "provenance": {"kind": "simulated_ground_truth"}}])
    assert hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() == before_hash
    assert report["canonical_model_changed"] is False
    assert report["model_path"].startswith("artifacts/retrained/")
    assert (ROOT / report["model_path"]).exists()
    assert report["split"] == "test" and report["n_test"] == sum(item["split"] == "test" for item in dataset)
    assert report["cord_test"]["n_test"] == sum(item["split"] == "test" and item["source"] == "cord" for item in dataset)
    assert report["human_corrections_used"] == 0
    assert report["simulated_corrections_used"] == 1
    assert len(report["frozen_test_ids_sha256"]) == 64
    assert {row["ocr_engine"] for row in report["by_source"]} == {"gold", "tesseract"}


def test_partial_review_masks_unreviewed_tokens_instead_of_teaching_false_negatives():
    document = {"id": "partial", "type": "invoice", "tokens": [
        {"text": "unreviewed", "box": [.1, .1, .1, .02], "label": "tax"},
        {"text": "42.00", "box": [.3, .1, .1, .02], "label": "O"}]}
    corrected = correction_document({"document": document, "fields": {"total": 42}})
    assert [token["training_mask"] for token in corrected["tokens"]] == [False, True]
    assert corrected["tokens"][1]["label"] == "total"
    training = {"id": "base", "type": "invoice", "split": "train", "tokens": [
        {"text": "ordinary", "box": [.1, .1, .1, .02], "label": "O"},
        {"text": "7.00", "box": [.3, .1, .1, .02], "label": "total"}]}
    model = TokenExtractor().fit([training, corrected])
    feature_names = set(model.vectorizer.get_feature_names_out())
    assert "text=unreviewed" not in feature_names
    assert "left=unreviewed" in feature_names
    assert document["tokens"][0]["label"] == "tax"


def test_repeated_amounts_are_ambiguous_not_overwritten_by_field_order():
    corrected = correction_document({"document": {"id": "ambiguous", "tokens": [
        {"text": "50.00"}, {"text": "50.00"}]}, "fields": {"subtotal": 50, "total": 50}})
    assert corrected["correction_alignment"]["labeled_tokens"] == 0
    assert all(not token["training_mask"] for token in corrected["tokens"])


def test_corrected_line_items_align_within_their_described_row():
    tokens = [{"text": text, "box": [.1 + index * .15, .2, .1, .03]} for index, text in enumerate(["Paper", "2", "3.00", "6.00"])]
    result = correction_document({"document": {"id": "row", "tokens": tokens}, "fields": {},
        "line_items": [{"description": "Paper", "quantity": 2, "unit_price": 3, "amount": 6}]})
    assert [token["label"] for token in result["tokens"]] == ["description", "quantity", "unit_price", "amount"]
    assert result["correction_alignment"]["labeled_tokens"] == 4


def test_frozen_test_derivative_or_renamed_copy_cannot_train():
    document = next(item for item in read_json(ROOT / "data/dataset.json") if item["split"] == "test")
    for change in ({"id": "new-upload", "split": "upload", "parent_id": document["id"]},
                   {"id": "renamed-copy", "split": "upload"}):
        copied = {**copy.deepcopy(document), **change}
        with pytest.raises(ValueError, match="frozen test"):
            retrain_from_corrections([{"document": copied, "fields": {"total": copied["total"]}}])


def test_no_trainable_or_duplicate_corrections_are_rejected():
    document = {"id": "new-empty", "tokens": [], "type": "invoice", "split": "upload"}
    with pytest.raises(ValueError, match="unambiguous"):
        retrain_from_corrections([{"document": document, "fields": {"total": 10}}])
    with pytest.raises(ValueError, match="unique"):
        retrain_from_corrections([{"document": document}, {"document": document}])
