"""Build and execute evidence notebooks against the canonical manifest."""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat
from jupyter_client import KernelManager
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
LOAD = """from pathlib import Path
import json
import pandas as pd
root = Path.cwd()
e = json.loads((root / 'results/manifest.json').read_text(encoding='utf-8'))
print('Population:', e['scope'])
"""
SPECS = [
    ('01_cord_and_ocr', 'Recognition and extraction are separate measurements', '''
rows = pd.DataFrame([{'source':r['source'], 'extractor':r['backend'], 'input':r['ocr_engine'],
                     'documents':r['n'], 'field_f1':r['field_f1']['value']} for r in e['extraction']])
print(rows.to_string(index=False))
print(pd.DataFrame(e['ocr']).to_string(index=False))
assert rows['input'].nunique() >= 2, 'Gold words do not establish OCR quality'
''', '''
# Rejected shortcut: a gold-only result cannot measure recognition errors.
gold_only = rows[rows['input'].str.contains('gold')]
print('Gold-only rows:', len(gold_only))
print('Real OCR rows removed by this shortcut:', len(rows) - len(gold_only))
assert len(gold_only) < len(rows)
'''),
    ('02_token_classifier', 'Compare the learned extractor with rules', '''
rows = pd.DataFrame([{'source':r['source'], 'backend':r['backend'], 'input':r['ocr_engine'],
                     'field_f1':r['field_f1']['value'], 'interval':r['field_f1'].get('ci')}
                    for r in e['extraction']])
print(rows.to_string(index=False))
print('Recorded retraining:', e.get('retrain'))
assert rows['backend'].nunique() >= 2
''', '''
# Rejected shortcut: choosing the largest test estimate is not a promotion test.
leader = rows.sort_values('field_f1', ascending=False).iloc[0]
print('Largest point estimate:', leader.to_dict())
print('This observation alone has no paired significance or deployment guarantee.')
'''),
    ('03_calibration_and_operating_point', 'Costs, calibration, and held-out routing', '''
op = e['operating_point']
print({key:value for key,value in op.items() if key != 'curve'})
print(pd.DataFrame(op['curve']).to_string(index=False))
calibration = [{key:value for key,value in row.items() if key != 'bins'} for row in e['calibration']]
print(pd.DataFrame(calibration).to_string(index=False))
assert op['chosen_on'] == 'validation'
assert op['reported_on'] == 'test'
''', '''
# Negative control: test-selected routing must be rejected by publication.
from copy import deepcopy
from scripts.render_reports import validate_manifest
invalid = deepcopy(e)
invalid['operating_point']['chosen_on'] = 'test'
try:
    validate_manifest(invalid)
except ValueError as error:
    print('Rejected:', error)
else:
    raise AssertionError('Test leakage was not rejected')
'''),
]


def main() -> None:
    target = ROOT / 'notebooks'
    target.mkdir(exist_ok=True)
    for name, title, analysis, negative in SPECS:
        notebook = nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_markdown_cell('# ' + title + '\n\nDemonstration documents only. '
                                         'These notebooks inspect the committed evidence; they do not '
                                         'claim a separate full-dataset training run.'),
            nbformat.v4.new_code_cell(LOAD),
            nbformat.v4.new_code_cell(analysis.strip()),
            nbformat.v4.new_markdown_cell('## Rejected shortcut / negative control'),
            nbformat.v4.new_code_cell(negative.strip()),
        ])
        notebook.metadata['kernelspec'] = {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}
        manager = KernelManager(kernel_name='python3')
        manager.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
        try:
            NotebookClient(notebook, km=manager, timeout=120,
                           resources={'metadata': {'path': str(ROOT)}}).execute()
        finally:
            if manager.has_kernel:
                manager.shutdown_kernel(now=True)
        nbformat.write(notebook, target / (name + '.ipynb'))
        print('Executed', name)


if __name__ == '__main__':
    main()
