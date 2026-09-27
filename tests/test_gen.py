from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from packages import gen


def test_seed_truth_and_layout_coverage() -> None:
    docs = [gen.make_document(i, 'train') for i in range(12)]
    assert docs == [gen.make_document(i, 'train') for i in range(12)]
    assert {d['layout'] for d in docs} == {0, 1, 2, 3}
    assert {d['type'] for d in docs} == {'invoice', 'purchase_order'}
    for doc in docs:
        assert doc['subtotal'] == round(sum(row['amount'] for row in doc['line_items']), 2)
        assert all(row['amount'] == round(row['quantity'] * row['unit_price'], 2) for row in doc['line_items'])
        if 'arithmetic' not in doc['defects']:
            assert doc['total'] == round(doc['subtotal'] + doc['tax'], 2)


def test_defects_change_truth_against_independent_master() -> None:
    currency = gen.make_document(1, 'test')
    assert currency['currency'] in {'USD', 'EUR', 'GBP'}
    assert currency['currency'] != currency['vendor_currencies'][currency['vendor']]
    assert currency['defects'] == ['currency']
    arithmetic = gen.make_document(3, 'test')
    assert arithmetic['total'] != arithmetic['expected_po_total']
    vendor = gen.make_document(5, 'test')
    assert vendor['vendor'] not in vendor['vendor_master']
    po = gen.make_document(7, 'test')
    assert po['po_number'] != po['po_reference']['number']
    duplicate = gen.make_document(9, 'test')
    original = gen.make_document(8, 'test')
    assert duplicate['duplicate_of'] == original['id']
    assert duplicate['number'] == original['number']
    dates = gen.make_document(11, 'test')
    assert dates['due_date'] < dates['date']


@pytest.mark.parametrize('layout', range(4))
def test_generated_page_contains_bounded_truth_boxes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: int) -> None:
    monkeypatch.setattr(gen, 'ROOT', tmp_path)
    doc = gen.render_document(gen.make_document(layout, 'test'), tmp_path / 'pages')
    assert (tmp_path / doc['pdf_path']).read_bytes().startswith(b'%PDF')
    with Image.open(tmp_path / doc['image_path']) as image:
        assert image.width > 900 and image.height > image.width
    assert {'vendor', 'number', 'date', 'total', 'description'} <= {token['label'] for token in doc['tokens']}
    for token in doc['tokens']:
        x, y, w, h = token['box']
        assert 0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1
        assert x + w <= 1 and y + h <= 1


@pytest.mark.parametrize(('kind', 'level'), [('skew', 7), ('blur', 2), ('noise', 20), ('jpeg', 8),
                                            ('downscale', .2), ('photograph', 1), ('threshold', 3)])
def test_degradation_changes_pixels_reproducibly(kind: str, level: float) -> None:
    original = Image.new('RGB', (160, 200), '#dadada')
    draw = ImageDraw.Draw(original)
    draw.rectangle((15, 30, 100, 70), fill='#678192')
    draw.text((20, 100), 'Invoice 127.50', fill='black')
    first = gen.degrade(original, kind, level)
    second = gen.degrade(original, kind, level)
    assert first.size == original.size
    assert np.array_equal(np.asarray(first), np.asarray(second))
    assert not np.array_equal(np.asarray(first), np.asarray(original))


def test_degradation_zero_and_invalid() -> None:
    original = Image.new('RGB', (10, 20), 'white')
    unchanged = gen.degrade(original, 'blur', 0)
    assert unchanged is not original
    assert unchanged.tobytes() == original.tobytes()
    with pytest.raises(ValueError):
        gen.degrade(original, 'missing', 1)


def test_generation_split_membership(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen, 'ROOT', tmp_path)
    monkeypatch.setattr(gen, 'render_document', lambda doc, _: doc)
    docs = gen.generate(8, tmp_path / 'pages')
    assert [doc['split'] for doc in docs] == ['train'] * 4 + ['validation'] * 2 + ['test'] * 2
    assert (tmp_path / 'data/vendors/master.json').exists()
