import pytest

from packages.evaluation import (
    benjamini_hochberg,
    edit_distance,
    interval,
    ocr_error,
    paired_comparison,
    proportion_interval,
    score_document,
    score_rows,
    summarize,
)


def test_row_matching_never_reuses_reference():
    row = {"description": "paper", "quantity": 2, "unit_price": 5, "amount": 10}
    assert score_rows([row, row], [row]) == pytest.approx(2 / 3)
    assert score_rows([], [row]) == 0
    assert score_rows([], []) == 1
    assert score_rows([row], []) == 0


def test_interval_is_reproducible_and_missing_stays_null():
    assert interval([.1, .5, .9]) == interval([.1, .5, .9])
    assert interval([], reason="No denominator")["reason"] == "No denominator"
    assert interval([1, 1])["value"] == 1
    assert interval([0, 1])["ci"] == [0, 1]


def test_zero_observed_error_still_has_wilson_uncertainty():
    result = proportion_interval(0, 14)
    assert result["value"] == 0
    assert .20 < result["ci"][1] < .23
    assert proportion_interval(0, 0)["value"] is None


def test_edit_distance_known_insert_delete_substitute():
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance([], ["word"]) == 1
    assert edit_distance(["one", "two"], ["two"]) == 1


def test_ocr_measurement_against_reference():
    truth = [{"text": "hello", "box": [0, 0, .2, .1]}]
    assert ocr_error(truth, truth) == {"cer": 0, "wer": 0}
    assert ocr_error(truth, []) == {"cer": 1, "wer": 1}


def test_paired_comparison_and_multiple_testing():
    result = paired_comparison([1, 1, 1], [0, 0, 0])
    assert result["difference"]["value"] == 1
    assert result["p_value"] < .01
    assert benjamini_hochberg([.01, .04, .03]) == pytest.approx([.03, .04, .04])
    with pytest.raises(ValueError):
        paired_comparison([1], [])


def test_published_sweep_examples_reference_real_source_documents():
    from pathlib import Path

    from packages.core import ROOT, read_json
    bundle = read_json(ROOT / "web/public/data/demo.json")
    ids = {document["id"] for document in bundle["documents"]}
    for observation in bundle["evaluation"]["degradation"]:
        assert observation["document_id"] in ids
        assert (ROOT / "web/public" / observation["image"].lstrip("/")).is_file()
        assert Path(observation["image"]).stem.startswith(observation["document_id"] + "-")


def test_unknown_receipt_truth_is_not_an_extraction_failure_or_success():
    document = {"id": "unlabeled", "type": "receipt", "source": "cord", "total": None,
                "subtotal": None, "tax": None, "line_items": []}
    result = score_document(document, {"fields": {"total": {"value": 118000}}, "line_items": []})
    assert result["fields"] == {}
    assert result["reference_fields"] == 0 and result["document_evaluable"] is False
    for metric in ("field_f1", "precision", "recall", "exact_match", "document_success", "line_item_f1"):
        assert result[metric] is None


def test_document_correctness_requires_all_required_reference_fields():
    document = {"id": "partial", "type": "receipt", "source": "cord", "total": None, "tax": 10, "line_items": []}
    result = score_document(document, {"fields": {"tax": {"value": 10}}})
    assert result["field_f1"] == 1
    assert result["document_success"] is None
    document["total"] = 100
    assert score_document(document, {"fields": {"tax": {"value": 10}}})["document_success"] == 0


def test_summary_reports_per_metric_evaluable_denominators():
    complete = score_document({"id": "labeled", "source": "cord", "type": "receipt", "total": 10},
                              {"fields": {"total": {"value": 10}}})
    unknown = score_document({"id": "unknown", "source": "cord", "type": "receipt", "total": None},
                             {"fields": {"total": {"value": 999}}})
    summary = summarize([complete, unknown])
    assert summary["field_f1"]["value"] == 1
    assert summary["field_f1"]["n"] == 1
    assert summary["field_f1"]["population_n"] == 2
    assert summary["field_f1"]["excluded_without_reference"] == 1
    assert summary["document_success"]["n"] == 1
    assert summary["line_item_f1"]["value"] is None
    assert summary["line_item_f1"]["n"] == 0
