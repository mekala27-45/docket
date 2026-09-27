"""Re-derive the canonical demo from frozen inputs, excluding reviewer databases."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    # Canonical evaluation never reads local review databases or browser practice.
    # Its newly exported bundle restores the published session without deleting user data.
    for name in ['evaluate.py', 'render_reports.py', 'build_notebooks.py']:
        subprocess.run([sys.executable, str(ROOT / 'scripts' / name)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/render_reports.py'), '--check'], cwd=ROOT, check=True)
    print('Canonical demo and reports re-derived from the committed dataset and real OCR observations')


if __name__ == '__main__':
    main()
