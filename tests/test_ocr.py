import io
from typing import Any

import pytest
from PIL import Image
from reportlab.pdfgen.canvas import Canvas

from packages import ocr


def test_engine_step_ran_independently_of_correctness(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def recognize(image: Image.Image, **kwargs: Any) -> dict[str, list[Any]]:
        calls.append((image.size, kwargs))
        return {'text': ['', 'WRONG'], 'left': [0, 90], 'top': [0, 45], 'width': [0, 180],
                'height': [0, 90], 'conf': [-1, 175], 'block_num': [0, 1], 'par_num': [0, 1], 'line_num': [0, 1]}

    monkeypatch.setattr(ocr.pytesseract, 'image_to_data', recognize)
    monkeypatch.setattr(ocr.pytesseract, 'get_tesseract_version', lambda: 'test-engine')
    monkeypatch.setenv('TESSERACT_CMD', 'test-command')
    result = ocr.recognize(Image.new('RGB', (100, 200)), binarize=True)
    assert len(calls) == 1
    assert calls[0][0] == (900, 1800)
    assert result['tokens'][0]['text'] == 'WRONG'
    assert result['tokens'][0]['confidence'] == 1
    assert result['tokens'][0]['box'] == pytest.approx([.1, .025, .2, .05])
    assert result['engine'] == 'tesseract' and result['version'] == 'test-engine'
    assert 'threshold 170' in result['preprocessing']
    assert result['elapsed_ms'] >= 0


def test_gold_words_never_calls_engine_and_strips_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_: Any, **__: Any) -> None:
        raise AssertionError('Gold input must not call OCR')
    monkeypatch.setattr(ocr.pytesseract, 'image_to_data', forbidden)
    result = ocr.gold_words({'tokens': [{'text': '1.25', 'box': [.1, .2, .3, .1], 'label': 'total', 'bio': 'B-total'}]})
    assert result['engine'] == 'gold'
    assert 'label' not in result['tokens'][0] and 'bio' not in result['tokens'][0]
    assert ocr.gold_words({})['tokens'] == []


def test_preprocess_preserves_large_page_and_thresholds() -> None:
    image = Image.new('RGB', (1000, 200), '#444444')
    assert ocr.preprocess(image).size == image.size
    assert ocr.preprocess(image, True).getpixel((0, 0)) == (0, 0, 0)


def test_image_decode_and_pdf_page_limit() -> None:
    stream = io.BytesIO()
    Image.new('RGB', (30, 50), 'white').save(stream, format='PNG')
    assert ocr.image_from_bytes(stream.getvalue(), 'page.png').size == (30, 50)
    pdf = io.BytesIO()
    canvas = Canvas(pdf, pagesize=(100, 100))
    canvas.drawString(10, 40, 'Invoice')
    canvas.save()
    assert ocr.image_from_bytes(pdf.getvalue(), 'page.pdf').width == 170
    multi = io.BytesIO()
    canvas = Canvas(multi)
    canvas.showPage()
    canvas.showPage()
    canvas.save()
    with pytest.raises(ValueError, match='single-page'):
        ocr.image_from_bytes(multi.getvalue(), 'two.pdf')


def test_engine_failure_is_not_a_gold_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_: Any, **__: Any) -> None:
        raise RuntimeError('engine timeout')
    monkeypatch.setattr(ocr.pytesseract, 'image_to_data', fail)
    with pytest.raises(RuntimeError, match='timeout'):
        ocr.recognize(Image.new('RGB', (900, 900)))
