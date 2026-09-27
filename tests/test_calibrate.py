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
