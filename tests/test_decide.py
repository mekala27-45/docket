import pytest

from packages.decide import choose_threshold, curve, document_confidence, eligible, route


def test_threshold_chosen_on_validation_cost_and_frozen():
    observations = [{"confidence": .4, "rules_pass": True, "correct": False},
                    {"confidence": .9, "rules_pass": True, "correct": True}]
    result = choose_threshold(observations)
    assert result["chosen_on"] == "validation"
    assert .4 < result["threshold"] <= .9
    with pytest.raises(ValueError, match="test data"):
        choose_threshold(observations, "test")
    with pytest.raises(ValueError):
        curve([])


def test_rule_failure_unknown_type_and_missing_calibration_fail_closed():
    doc = {"type": "receipt"}
    extraction = {"fields": {"total": {"value": 100, "confidence": .9, "calibration_n": 20}}}
    passes = [{"status": "pass"}, {"status": "not_applicable"}]
    assert eligible(doc, extraction, passes, .9)
    assert not eligible(doc, extraction, [{"status": "fail"}], .1)
    assert not eligible({"type": "other"}, extraction, passes, 0)
    assert not eligible(doc, extraction, [], 0)
    extraction["fields"]["total"]["calibration_n"] = 0
    assert not eligible(doc, extraction, passes, 0)
    extraction["fields"]["total"]["value"] = None
    assert document_confidence(doc, extraction) == 0


def test_risk_is_amount_times_uncertainty():
    result = route({"type": "receipt"}, {"fields": {"total": {"value": 100, "confidence": .8,
                                                               "calibration_n": 20}}}, [{"status": "pass"}], .9)
    assert result["risk"] == 20
    assert result["status"] == "needs_review"
    result = route({"type": "other"}, {"fields": {"total": {"value": "invalid"}}}, [], 0)
    assert result["risk"] == 0
