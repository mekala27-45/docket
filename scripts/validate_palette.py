"""Measure contrast on the fixed field overlays and interface surfaces."""
from __future__ import annotations

import json
import re
from pathlib import Path

LIGHT = ['#4F46C8', '#B4561E', '#0C9174', '#95561F', '#2457A6', '#A8780A', '#B8306E', '#5E8A1A']
DARK = ['#8B85F0', '#D97538', '#1FA69E', '#BE7D3E', '#5B8DEF', '#B98A14', '#DA4F94', '#80A126']
ROOT = Path(__file__).resolve().parents[1]


def luminance(value: str) -> float:
    values = [int(value[i:i+2], 16) / 255 for i in [1, 3, 5]]
    values = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
    return sum(a * b for a, b in zip(values, [0.2126, 0.7152, 0.0722], strict=True))


def contrast(a: str, b: str) -> float:
    x, y = sorted([luminance(a), luminance(b)])
    return (y + 0.05) / (x + 0.05)


def validate(colors: list[str], surface: str, minimum: float = 3) -> list[float]:
    if not colors:
        raise ValueError('Refusing empty palette')
    ratios = [contrast(color, surface) for color in colors]
    if min(ratios) < minimum:
        raise ValueError(f'Contrast below {minimum}: {ratios}')
    return ratios


def actual_interface(css: str) -> dict[str, list[float]]:
    output = {}
    patterns = {'light': r':root\s*\{([^}]+)\}',
                'dark': r':root\[data-theme=[\"\x27]?dark[\"\x27]?\]\s*\{([^}]+)\}'}
    for theme, pattern in patterns.items():
        match = re.search(pattern, css)
        if match is None:
            raise ValueError(f'Missing actual {theme} CSS theme')
        tokens = dict(re.findall(r'--([a-z-]+):\s*(#[a-fA-F0-9]{3,6})(?:;|\s)', match.group(1)))
        tokens = {k: '#' + ''.join(c * 2 for c in v[1:]) if len(v) == 4 else v for k, v in tokens.items()}
        for background in ['bg', 'surface', 'surface-alt']:
            if background not in tokens or any(k not in tokens for k in ['ink', 'secondary', 'muted']):
                raise ValueError(f'Incomplete actual {theme} CSS tokens')
            output[f'{theme}_{background}_text'] = validate(
                [tokens[k] for k in ['ink', 'secondary', 'muted']], tokens[background], 4.5)
    return output


if __name__ == '__main__':
    css_checks = actual_interface((ROOT / 'web/app/globals.css').read_text(encoding='utf-8'))
    types = (ROOT / 'web/lib/types.ts').read_text(encoding='utf-8')
    fields = re.search(r'FIELD_COLORS[^=]*=\s*\{([^}]+)\}', types)
    if fields is None or set(re.findall(r'#[a-fA-F0-9]{6}', fields.group(1))) != set(LIGHT):
        raise ValueError('Actual field overlay colors differ from the validated palette')
    print(json.dumps({
        'actual_interface': css_checks,
        'light_fields': validate(LIGHT, '#F3F4F6'),
        'dark_fields': validate(DARK, '#12151C'),
        'white_paper_overlays': validate(LIGHT, '#FFFFFF'),
        'light_text': validate(['#15181F', '#4B5262'], '#F3F4F6', 4.5),
        'dark_text': validate(['#ECEEF2', '#A8AFBD'], '#12151C', 4.5),
        'scope': 'WCAG contrast; labels supplement hue; CVD distance is not asserted',
    }, indent=2))
