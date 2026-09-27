import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts import render_reports
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


def test_gate_rejects_calibration_leakage_and_inflated_parent_counts() -> None:
    value = evidence()
    value['calibration'] = [{'fitted_on': 'test', 'split': 'test', 'n': 30, 'independent_documents': 2}]
    with pytest.raises(ValueError, match='held-out'):
        validate_manifest(value)
    value['calibration'][0]['fitted_on'] = 'validation'
    validate_manifest(value)
    value['calibration'][0]['independent_documents'] = 31
    with pytest.raises(ValueError, match='parent counts'):
        validate_manifest(value)


def test_gate_rejects_rule_rates_that_disagree_with_defect_counts() -> None:
    value = evidence()
    value['rules'] = [{'n': 4, 'tp': 1, 'fp': 1, 'fn': 1, 'tn': 1,
                       'precision': {'value': .5}, 'recall': {'value': .5}}]
    validate_manifest(value)
    value['rules'][0]['precision']['value'] = 1
    with pytest.raises(ValueError, match='injected-defect counts'):
        validate_manifest(value)


def test_gate_rejects_misleading_routing_population_breakdown() -> None:
    value = evidence()
    value['operating_point'].update({'n': 10, 'auto_approved': 2, 'by_source': [
        {'source': 'generated', 'n': 4, 'auto_approved': 2}, {'source': 'cord', 'n': 6, 'auto_approved': 0}]})
    validate_manifest(value)
    value['operating_point']['by_source'][1]['auto_approved'] = 1
    with pytest.raises(ValueError, match='headline population'):
        validate_manifest(value)


def test_whole_file_publication_drift_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = evidence()
    value['operating_point'].update({'threshold': .5, 'review_cost': 1, 'error_cost': 20,
                                    'review_rate': {'value': .5, 'ci': [.2, .8]},
                                    'auto_approval_error': {'value': 0, 'ci': [0, .5]}})
    (tmp_path / 'results').mkdir()
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'results/manifest.json').write_text(json.dumps(value), encoding='utf-8')
    (tmp_path / 'docs/implementation.json').write_text('[]', encoding='utf-8')
    monkeypatch.setattr(render_reports, 'ROOT', tmp_path)
    render_reports.render()
    render_reports.render(check=True)
    path = tmp_path / 'README.md'
    path.write_text(path.read_text(encoding='utf-8') + '\nInvented claim.\n', encoding='utf-8')
    with pytest.raises(ValueError, match='drift'):
        render_reports.render(check=True)
