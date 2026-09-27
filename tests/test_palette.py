import pytest

from scripts.validate_palette import LIGHT, actual_interface, contrast, validate


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


def test_actual_css_theme_text_contrast() -> None:
    css = ':root{--bg:#fff;--surface:#fff;--surface-alt:#fff;--ink:#000;--secondary:#444;--muted:#555;}'
    css += ':root[data-theme=dark]{--bg:#000;--surface:#111;--surface-alt:#222;--ink:#fff;--secondary:#ddd;--muted:#ccc;}'
    assert len(actual_interface(css)) == 6
    with pytest.raises(ValueError):
        actual_interface(css.replace('--muted:#555', '--muted:#ddd'))
    with pytest.raises(ValueError):
        actual_interface('')
