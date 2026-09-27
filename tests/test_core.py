from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from packages.core import (
    StrictModel,
    amount,
    matches,
    normalize,
    read_json,
    required_fields,
    union_box,
    write_json,
)


@pytest.mark.parametrize(('raw', 'expected'), [('Rp 15.000', '15000.00'), ('$1,234.56', '1234.56'),
                                             ('12,50', '12.50'), ('-25.40', '-25.40')])
def test_amount_locale_and_sign(raw: str, expected: str) -> None:
    assert amount(raw) == Decimal(expected)


@pytest.mark.parametrize('raw', [None, True, '', 'invalid', 'NaN', 'Infinity'])
def test_invalid_amount_refuses(raw: object) -> None:
    assert amount(raw) is None


@given(st.decimals(min_value='-99999', max_value='99999', places=2, allow_nan=False, allow_infinity=False))
def test_amount_format_round_trip(value: Decimal) -> None:
    assert amount(f'{value:.2f}') == value


@pytest.mark.parametrize(('raw', 'expected'), [('09/25/2026', '2026-09-25'), ('25/09/2026', '2026-09-25'),
                                             ('25.09.2026', '2026-09-25'), ('2026-09-25', '2026-09-25')])
def test_date_normalization_is_idempotent(raw: str, expected: str) -> None:
    assert normalize(raw, 'date') == expected
    assert normalize(normalize(raw, 'date'), 'date') == expected


def test_match_policy() -> None:
    assert matches('  NORTHLINE  PAPER ', 'northline paper', 'vendor')
    assert matches('1,234.50', '1234.50', 'total')
    assert matches('1234.50', '1,234.50', 'total')
    assert not matches(None, None, 'total')
    assert normalize(None) == ''
    assert normalize('bad', 'total') == ''
    assert normalize('bad', 'date') == 'bad'


def test_required_fields_respect_document_population() -> None:
    assert required_fields('receipt') == ('total',)
    assert 'due_date' in required_fields('invoice')
    assert 'due_date' not in required_fields('purchase_order')
    assert required_fields('other') == ()


def test_union_box_and_json(tmp_path: Path) -> None:
    assert union_box([]) is None
    box = union_box([{'box': [.1, .2, .3, .1]}, {'box': [.2, .1, .5, .4]}])
    assert box == pytest.approx([.1, .1, .6, .4])
    path = tmp_path / 'nested' / 'evidence.json'
    write_json(path, {'text': 'receipt', 'value': 2})
    assert read_json(path) == {'text': 'receipt', 'value': 2}
    with pytest.raises(ValueError):
        write_json(path, {'value': float('nan')})


def test_strict_contract_rejects_extra() -> None:
    with pytest.raises(ValidationError):
        StrictModel(unexpected=1)
