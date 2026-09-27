"""Render entire publications from committed evidence and reject drift."""
from __future__ import annotations

import argparse
import difflib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATEMENT = ('Demonstration documents only. Generated invoices contain fictional vendors and transactions. '
             'Public CORD receipts are attributed separately. Browser review practice is local to this device.')


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError('Refusing to publish empty evidence')
    for key in ['scope', 'extraction', 'operating_point']:
        if not value.get(key):
            raise ValueError(f'Missing evidence: {key}')
    op = value['operating_point']
    if op.get('chosen_on') != 'validation' or op.get('reported_on') != 'test':
        raise ValueError('Routing must be selected on validation and reported on test')
    for row in value['extraction']:
        if row.get('n', 0) <= 0 or not row.get('backend') or not row.get('ocr_engine'):
            raise ValueError('Every extraction row needs a population and backend')
        for metric in ['field_f1', 'exact_match', 'document_success', 'line_item_f1']:
            entry = row.get(metric)
            if not isinstance(entry, dict):
                raise TypeError(f'Missing interval for {metric}')
            if entry.get('value') is None and entry.get('reason'):
                continue
            estimate, ci = entry.get('value'), entry.get('ci')
            if not isinstance(estimate, (float, int)) or not math.isfinite(estimate):
                raise ValueError(f'Invalid estimate: {metric}')
            if not isinstance(ci, list) or len(ci) != 2 or not 0 <= ci[0] <= estimate <= ci[1] <= 1:
                raise ValueError(f'Invalid interval: {metric}')
    return value


def score(value: Any) -> str:
    if value is None:
        return 'Not measured'
    if isinstance(value, dict):
        point = value.get('value')
        if point is None:
            return str(value.get('reason', 'Not measured'))
        interval = value.get('ci')
        return (f'{point:.3f} [{interval[0]:.3f}, {interval[1]:.3f}]'
                if interval is not None else f'{point:.3f}')
    return f'{value:.3f}' if isinstance(value, (int, float)) else str(value)


def table(evidence: dict[str, Any]) -> str:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in evidence['extraction']:
        groups.setdefault((row['source'], row['backend']), {})[row['ocr_engine']] = row
    lines = ['| Population / extractor | Gold OCR field F1 | Tesseract field F1 |',
             '| --- | --- | --- |']
    for (source, backend), rows in sorted(groups.items()):
        gold = next((r for k, r in rows.items() if 'gold' in k.lower()), {})
        real = next((r for k, r in rows.items() if 'tesseract' in k.lower()), {})
        lines.append(f'| {source} / {backend} | {score(gold.get("field_f1"))} | {score(real.get("field_f1"))} |')
    return '\n'.join(lines)


def make_publications(e: dict[str, Any], checklist: list[dict[str, str]]) -> dict[str, str]:
    op = e['operating_point']
    limits = e.get('scope', {}).get('limitations', []) + e.get('limitations', [])
    limitations = '\n'.join(f'- {item}' for item in limits) or '- See the recorded population and protocol below.'
    measured = table(e)
    checklist_text = '\n'.join(f'| {row["item"]} | {row["status"]} | {row["evidence"]} |' for row in checklist)
    checklist_text = '| Capability | Status | Evidence |\n| --- | --- | --- |\n' + checklist_text
    threshold_label = 'review all' if op['threshold'] > 1 else f'{op["threshold"]:.3f}'
    headline = (f'At operating point **{threshold_label}**, selected on validation and reported on test, '
                f'the review rate is **{score(op.get("review_rate"))}** and the error rate among '
                f'automatically approved documents is **{score(op.get("auto_approval_error"))}**. '
                f'Review cost: {op["review_cost"]}; wrong approval cost: {op["error_cost"]}. '
                'These are policy cost units, not observed financial losses.')
    protocol = '```json\n' + json.dumps(e['scope'], indent=2, ensure_ascii=False) + '\n```'
    skills = '''| Skill | Evidence |
| --- | --- |
| OCR and preprocessing | `packages/ocr`, paired OCR columns |
| Synthetic known truth and degradation | `packages/gen` |
| Field extraction and trace | `packages/extract` |
| Learned token classification | `packages/extract`, notebook 02 |
| Calibration and routing by cost | `packages/calibrate`, `packages/decide` |
| Document classification | `packages/classify` |
| Business validation | `packages/rules`, rule tests |
| Durable human review | `packages/api`, independent persistence test |
| Privacy and redaction | `packages/redact`, planted identifier tests |
| Evaluation and uncertainty | `packages/evaluation`, `results/manifest.json` |
| Interface and browser SQL | `web`, recorded review and evidence pages |
| Reproducible reporting | `scripts/render_reports.py`, whole-file drift check |
| Deployment | `.github/workflows/pages.yml`, GitHub Pages |'''
    readme = f'''<!-- Generated by scripts/render_reports.py. -->
# docket

A document intelligence workbench for accounts payable. **Published scope: GitHub Pages with a recorded demo**, as selected by the owner. The repository includes a locally runnable review API; a public Fly/Neon API is outside this deployment. Read the evidence and limitations before interpreting the measured scores.

[Open docket](https://mekala27-45.github.io/docket/) · [Measured results](RESULTS.md) · [Evaluation report](report/evaluation-report.md)

> {STATEMENT}

## The operating point

{headline}

## Separate recognition from extraction

{measured}

Intervals are reported as estimate [lower, upper]. The difference between columns measures the effect of the OCR input, including recognition, tokenization, and boxes. It is not a guaranteed additive penalty: layout heuristics can perform better on an engine's boxes. Read `results/manifest.json` for sample sizes and the complete run.

## Run locally

```sh
uv sync --python 3.12
uv run pytest
uv run python scripts/render_reports.py --check
cd web
npm ci
npm run build
npm run preview
```

Open the printed preview URL with `/docket/`. For the optional API, follow [the runbook](docs/runbook.md) and `.env.example`. Uploads and server writes require a token. Browser practice edits do not reach a server or retrain a remote model.

## Skills and evidence

{skills}

## Implementation record

{checklist_text}

## Limits

{limitations}

Code is Apache 2.0. Receipt data retains its own attribution and license under `data/cord`. Generated vendors and transactions are fictional.
'''
    results = f'''<!-- Generated by scripts/render_reports.py. -->
# Measured results

> {STATEMENT}

{headline}

{measured}

## Recorded population

{protocol}

## Implementation record

{checklist_text}

## Limits

{limitations}

Every quantitative section below is rendered verbatim from the evidence manifest. A missing result remains missing.
'''
    report = f'''<!-- Generated by scripts/render_reports.py. -->
# Document intelligence evaluation

> {STATEMENT}

{headline}

{measured}

## Population and protocol

{protocol}

## What an accounts payable manager would challenge

Public Indonesian receipts and generated invoices do not reproduce an organization's mailroom. A low error estimate on a small held-out set can still have a wide interval. Review and error costs are explicit policy assumptions, and an organization must choose its own costs and measure its own population before approving transactions automatically.

## Limits

{limitations}
'''
    for name in ['ocr', 'calibration', 'classification', 'rules', 'degradation', 'retrain']:
        block = '\n\n## ' + name.replace('_', ' ').title() + '\n\n```json\n'
        block += json.dumps(e.get(name, {'status': 'not_measured'}), indent=2, ensure_ascii=False) + '\n```\n'
        results += block
        report += block
    return {'README.md': readme, 'RESULTS.md': results, 'report/evaluation-report.md': report}


def render(check: bool = False) -> None:
    evidence = validate_manifest(json.loads((ROOT / 'results/manifest.json').read_text(encoding='utf-8')))
    checklist = json.loads((ROOT / 'docs/implementation.json').read_text(encoding='utf-8'))
    for name, content in make_publications(evidence, checklist).items():
        path = ROOT / name
        if check:
            actual = path.read_text(encoding='utf-8') if path.exists() else ''
            if actual != content:
                diff = ''.join(difflib.unified_diff(actual.splitlines(True), content.splitlines(True), name, 'expected'))
                raise ValueError('Published evidence drift:\n' + diff)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8', newline='\n')
    print('Complete publication drift check passed' if check else 'Publications rendered from evidence')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    render(parser.parse_args().check)
