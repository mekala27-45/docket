"""Check authored language and published demonstration statements."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', '.venv312', 'node_modules', '.next', 'out', '.cache',
        '__pycache__', '.mypy_cache', '.ruff_cache', '.pytest_cache', '.hypothesis',
        'data', 'results', 'artifacts', 'notebooks', 'test-results', 'playwright-report'}
EXTENSIONS = {'.md', '.py', '.tsx', '.ts', '.css', '.html', '.j2', '.yml'}
WORDS = ['seam' + 'less', 'del' + 've', 'game' + '-changing', 'revolutio' + 'nary',
         'syner' + 'gy', 'cutting' + '-edge']
BANNED = re.compile(r'\b(?:' + '|'.join(re.escape(w) for w in WORDS) + r')\b', re.IGNORECASE)


def authored_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for directory, folders, names in os.walk(root):
        folders[:] = [name for name in folders if name not in SKIP]
        for name in names:
            path = Path(directory) / name
            if path.suffix in EXTENSIONS and 'public' not in path.relative_to(root).parts:
                files.append(path)
    if not files:
        raise ValueError('Refusing to check an empty project')
    return files


def check_text(text: str) -> list[str]:
    if not text.strip():
        raise ValueError('Refusing empty authored text')
    errors = []
    if chr(0x2014) in text:
        errors.append('forbidden punctuation')
    if BANNED.search(text):
        errors.append('banned vocabulary')
    return errors


def check_statement(text: str) -> None:
    if not text.strip() or 'demonstration' not in text.lower():
        raise ValueError('Missing demonstration statement')


def main() -> None:
    errors = []
    for path in authored_files(ROOT):
        content = path.read_text(encoding='utf-8-sig')
        if content.strip():
            errors.extend(f'{path.relative_to(ROOT)}: {e}' for e in check_text(content))
    for name in ['README.md', 'RESULTS.md', 'report/evaluation-report.md']:
        path = ROOT / name
        if not path.exists():
            errors.append(f'Missing published document {name}')
        else:
            try:
                check_statement(path.read_text(encoding='utf-8'))
            except ValueError as error:
                errors.append(f'{name}: {error}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Authored language and publication statement gates passed')


if __name__ == '__main__':
    main()
