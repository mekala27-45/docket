from copy import deepcopy
from typing import Any

import pytest

from scripts.render_reports import validate_manifest


def evidence() -> dict[str, Any]:
    metric = {'value': 0.5, 'ci': [0.2, 0.8]}
    return {'scope': {'test': 2}, 'extraction': [{'n': 2, 'source': 'fixture', 'backend': 'rules',
            'ocr_engine': 'gold', **{k: metric for k in ['field_f1', 'exact_match', 'document_success', 'line_item_f1']}}],
            'operating_point': {'chosen_on': 'validation', 'reported_on': 'test'}}


def test_claim_gate_clean_pass() -> None:
    validate_manifest(evidence())


def test_claim_gate_catches_invalid_interval() -> None:
    value = deepcopy(evidence())
    value['extraction'][0]['field_f1'] = {'value': 0.5, 'ci': [0.7, 0.8]}
    with pytest.raises(ValueError, match='interval'):
        validate_manifest(value)


def test_claim_gate_refuses_empty() -> None:
    with pytest.raises(ValueError):
        validate_manifest({})


def test_claim_gate_rejects_test_selection() -> None:
    value = evidence()
    value['operating_point']['chosen_on'] = 'test'
    with pytest.raises(ValueError, match='validation'):
        validate_manifest(value)
