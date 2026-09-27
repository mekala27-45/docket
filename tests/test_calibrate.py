import pickle

import pytest

from packages.calibrate import FieldCalibrator, reliability
from packages.extract.rules import field_result


def test_calibration_fits_heldout_only_and_sentence_uses_population():
    rows = [{"backend": "rules", "field": "total", "score": .8, "correct": correct}
            for correct in [1, 1, 0, 1]]
    calibrator = FieldCalibrator().fit(rows)
    extraction = {"backend": "rules", "fields": {"total": field_result("total", [
        {"value": 10, "score": .8, "box": [.1, .1, .1, .1]}])}}
    result = calibrator.apply(extraction)["fields"]["total"]
    assert result["confidence"] == .75
    assert "75 were correct" in result["calibration_sentence"]
    assert "4 validation fields" in result["calibration_sentence"]
    assert result["calibration_n"] == 4
    with pytest.raises(ValueError):
        FieldCalibrator().fit(rows, "test")
    with pytest.raises(ValueError):
        FieldCalibrator().fit([])


def test_isotonic_predictions_bounded_and_missing_fails_closed(tmp_path):
    rows = [{"backend": "tokens", "field": "total", "score": x, "correct": y}
            for x, y in [(0, 0), (.2, 1), (.4, 0), (.8, 1), (1, 1)]]
    model = FieldCalibrator().fit(rows)
    values = [model.predict("tokens", "total", x / 10) for x in range(-2, 13)]
    assert values == sorted(values)
    assert all(0 <= v <= 1 for v in values)
    assert model.predict("tokens", "total", 1, missing=True) == 0
    assert model.predict("rules", "total", 1) == 0
    path = tmp_path / "model.pkl"
    model.save(path)
    assert FieldCalibrator.load(path).predict("tokens", "total", .8) == model.predict("tokens", "total", .8)
    assert FieldCalibrator.load(tmp_path / "missing").models == {}
    path.write_bytes(pickle.dumps("bad"))
    with pytest.raises(TypeError):
        FieldCalibrator.load(path)


def test_reliability_accounts_for_confidence_one():
    result = reliability([0, .5, 1], [0, 1, 1])
    assert sum(b["count"] for b in result["bins"]) == 3
    assert result["ece"] == pytest.approx(1 / 6)
    assert reliability([], [])["bins"] == []


def test_receipt_headers_cannot_inherit_generated_calibration():
    rows = [{"backend": "rules", "field": field, "score": .9, "correct": 1}
            for field in ["vendor", "total"]]
    model = FieldCalibrator().fit(rows)
    extraction = {"backend": "rules", "document_type": "receipt", "fields": {
        field: field_result(field, [{"value": value, "score": .9, "box": [.1, .1, .1, .1]}])
        for field, value in [("vendor", "Unverified header"), ("total", 10)]}}
    fields = model.apply(extraction)["fields"]
    assert fields['vendor']['confidence'] == 0
    assert fields['vendor']['calibration_n'] == 0
    assert 'document population' in fields['vendor']['calibration_sentence']
    assert fields['total']['confidence'] == 1


def test_source_populations_do_not_transfer_generated_perfection_to_receipts():
    rows = [{"backend": "rules", "field": "total", "score": .9, "correct": outcome,
             "population": population, "parent_id": str(i), "split": "validation"}
            for population, outcomes in [("generated", [1, 1, 1, 1]), ("cord", [0, 1, 0, 1])]
            for i, outcome in enumerate(outcomes)]
    model = FieldCalibrator().fit(rows)
    assert model.predict("rules", "total", .9, population="generated") == 1
    assert model.predict("rules", "total", .9, population="cord") == .5
    assert model.predict("rules", "total", .9, population="unmeasured") == 0
    rows[0]["split"] = "test"
    with pytest.raises(ValueError, match="held-out"):
        FieldCalibrator().fit(rows)


def test_imperfect_heldout_fields_produce_measured_nonconstant_confidence():
    rows = [{"backend": "rules", "field": "vendor", "score": score, "correct": correct,
             "population": "generated", "parent_id": f"parent-{i % 2}"}
            for i, (score, correct) in enumerate([(.2, 0), (.3, 0), (.7, 1), (.9, 1)])]
    model = FieldCalibrator().fit(rows)
    assert model.predict("rules", "vendor", .3, population="generated") == 0
    assert model.predict("rules", "vendor", .7, population="generated") == 1
    assert model.population["rules:generated:vendor"] == 4
    assert model.parents["rules:generated:vendor"] == 2
    rows[0]["score"] = float("nan")
    with pytest.raises(ValueError, match="probabilities"):
        FieldCalibrator().fit(rows)


def test_reliability_resamples_parents_instead_of_counting_variants_independent():
    measured = reliability([.5] * 20, [0] * 10 + [1] * 10, groups=["a"] * 10 + ["b"] * 10)
    row = measured["bins"][0]
    assert row["count"] == 20
    assert row["independent_documents"] == 2
    assert row["ci"] == [0, 1]
    with pytest.raises(ValueError, match="align"):
        reliability([.5], [1], groups=[])
    with pytest.raises(ValueError, match="probabilities"):
        reliability([2], [1])
