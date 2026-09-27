from pathlib import Path

import pytest

from scripts.quality_gates import authored_files, check_statement, check_text


def test_language_clean_pass() -> None:
    assert check_text('Documents awaiting review.') == []


def test_language_deliberate_failure() -> None:
    assert check_text('One' + chr(0x2014) + 'two')
    assert check_text('seam' + 'less')


def test_language_refuses_empty(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        check_text(' ')
    with pytest.raises(ValueError):
        authored_files(tmp_path)


def test_statement_clean_pass() -> None:
    check_statement('These are demonstration documents.')


@pytest.mark.parametrize('text', ['', 'Customer invoices.'])
def test_statement_refuses_missing_or_empty(text: str) -> None:
    with pytest.raises(ValueError):
        check_statement(text)
