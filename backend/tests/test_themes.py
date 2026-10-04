"""Accessibility guard for the decorative book themes.

The palettes live in frontend/src/styles/themes.css (the rendering source of
truth). This parses that file directly rather than duplicating the colours, so
a theme can never drift out of WCAG AA without a test failing.
"""

import re
from pathlib import Path

import pytest

THEMES_CSS = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "styles" / "themes.css"
)
SEED_BOOKS_PY = Path(__file__).resolve().parents[1] / "scripts" / "seed_books.py"

AA_NORMAL_TEXT = 4.5

BLOCK_RE = re.compile(r'\[data-theme="([a-z]+)"\]\s*\{([^}]*)\}', re.MULTILINE)
VAR_RE = re.compile(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})")
DARK_MARKER = "@media (prefers-color-scheme: dark)"


def _srgb_channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _srgb_channel(r) + 0.7152 * _srgb_channel(g) + 0.0722 * _srgb_channel(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def parse_themes() -> dict[str, dict[str, str]]:
    """{'meadow (light)': {'bg': '#...', 'text': '#...'}, ...}"""
    css = THEMES_CSS.read_text(encoding="utf-8")
    light_css, _, dark_css = css.partition(DARK_MARKER)

    themes: dict[str, dict[str, str]] = {}
    for scheme, chunk in (("light", light_css), ("dark", dark_css)):
        for name, body in BLOCK_RE.findall(chunk):
            themes[f"{name} ({scheme})"] = dict(VAR_RE.findall(body))
    return themes


THEMES = parse_themes()


def test_themes_css_was_parsed():
    assert THEMES, "no themes parsed - did themes.css move or change format?"
    # every theme should exist in both schemes
    light = {k.split(" ")[0] for k in THEMES if "light" in k}
    dark = {k.split(" ")[0] for k in THEMES if "dark" in k}
    assert light == dark, f"themes missing a dark variant: {light ^ dark}"


def test_contrast_helpers_are_correct():
    assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
    assert round(contrast_ratio("#ffffff", "#ffffff"), 1) == 1.0


@pytest.mark.parametrize("theme", sorted(THEMES))
@pytest.mark.parametrize("fg,bg", [("text", "bg"), ("text", "surface"),
                                   ("text-muted", "bg"), ("text-muted", "surface")])
def test_text_meets_wcag_aa(theme, fg, bg):
    palette = THEMES[theme]
    if fg not in palette or bg not in palette:
        pytest.skip(f"{theme} does not define --{fg}/--{bg}")
    ratio = contrast_ratio(palette[fg], palette[bg])
    assert ratio >= AA_NORMAL_TEXT, (
        f"{theme}: --{fg} on --{bg} is {ratio:.2f}:1, below WCAG AA {AA_NORMAL_TEXT}:1"
    )


def test_seed_themes_all_exist_in_css():
    """Every theme assigned to a seed book must be a real theme."""
    assigned = set(re.findall(r'"theme":\s*"([a-z]+)"', SEED_BOOKS_PY.read_text(encoding="utf-8")))
    known = {k.split(" ")[0] for k in THEMES}
    assert assigned, "no themes assigned in seed_books.py"
    assert assigned <= known, f"seed books use unknown themes: {assigned - known}"
