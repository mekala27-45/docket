import pytest

from scripts.validate_palette import LIGHT, contrast, validate


def test_white_paper_palette_passes() -> None:
    assert min(validate(LIGHT, '#FFFFFF')) >= 3


def test_palette_catches_invisible_overlay() -> None:
    with pytest.raises(ValueError):
        validate(['#FFFFFF'], '#FFFFFF')


def test_palette_refuses_empty() -> None:
    with pytest.raises(ValueError):
        validate([], '#FFFFFF')


def test_contrast_symmetric() -> None:
    assert contrast('#123456', '#FFFFFF') == contrast('#FFFFFF', '#123456')
