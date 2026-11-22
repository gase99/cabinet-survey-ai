"""Deterministic fonts and Persian/Arabic text shaping for exported PDFs/PNGs.

Only the bundled Vazirmatn TTFs (SIL OFL 1.1, `app/assets/fonts`) are used, embedded in
every PDF. No system font and no PDF standard-14 font (e.g. Helvetica, which has no
Persian glyphs and is not embedded) is relied on. ReportLab and Pillow's basic layout do
not shape complex scripts, so RTL text is converted here: `arabic_reshaper` selects the
contextual presentation forms (initial/medial/final/isolated, lam-alef ligatures) and
`python-bidi` applies the Unicode Bidirectional Algorithm to produce visual order. Latin
digits and units such as "3000 mm" keep their left-to-right order inside RTL text.
"""
from __future__ import annotations

import hashlib
import re
import threading
import unicodedata
from functools import lru_cache
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import ImageFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONT_NAME = "Vazirmatn"
FONT_NAME_BOLD = "Vazirmatn-Bold"
# Pinned digests: a substituted or corrupted font must fail loudly, not render boxes.
FONT_FILES = {
    FONT_NAME: ("Vazirmatn-Regular.ttf", "b69fd4c680b8f3f225feabcc655a2c585d97627b8f5f5c0f9985e894069f3a56"),
    FONT_NAME_BOLD: ("Vazirmatn-Bold.ttf", "f635fdbea28f265de395ba83b4b1570dcf2f58d13c65469e61903b1c2d2ae723"),
}

_RTL_CHARS = re.compile("[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]")
# A dimension expression such as "3000 mm", "900×1200" or "3000 mm × 2700 mm". Inside RTL
# text the plain bidi algorithm splits these (e.g. "mm × 2700 mm 3000"); each match is
# wrapped in LRE..PDF so it stays one left-to-right unit, read like on a drawing.
_DIMENSION = re.compile(r"\d+(?:[.,]\d+)?(?:\s?mm)?(?:\s?[×xX*]\s?\d+(?:[.,]\d+)?(?:\s?mm)?)*")
_LRE, _PDF = "\u202a", "\u202c"
_register_lock = threading.Lock()


class FontUnavailableError(RuntimeError):
    """The bundled export font is missing or does not match its pinned digest."""


def font_path(name: str = FONT_NAME) -> Path:
    filename, digest = FONT_FILES[name]
    path = FONT_DIR / filename
    if not path.is_file():
        raise FontUnavailableError(f"Bundled export font missing: {path}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise FontUnavailableError(f"Bundled export font does not match its pinned SHA-256: {path}")
    return path


def register_fonts() -> None:
    """Register the bundled fonts with ReportLab (idempotent, verified every call)."""
    with _register_lock:
        for name in FONT_FILES:
            path = font_path(name)
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(path)))


def has_rtl(text: str) -> bool:
    return bool(_RTL_CHARS.search(text or ""))


def is_rtl(text: str) -> bool:
    """Paragraph base direction from the first strong character (UBA rules P2/P3)."""
    for char in text or "":
        direction = unicodedata.bidirectional(char)
        if direction in ("R", "AL"):
            return True
        if direction == "L":
            return False
    return False


@lru_cache(maxsize=4096)
def shape(text: str) -> str:
    """Return text in visual order with contextual glyph forms; Latin-only text unchanged."""
    if not has_rtl(text):
        return text
    embedded = _DIMENSION.sub(lambda match: f"{_LRE}{match.group(0)}{_PDF}", text)
    # bidi.algorithm is python-bidi's pure-Python UBA: it mirrors brackets and removes the
    # explicit embedding marks (rule X9); the Rust `bidi.get_display` does not mirror.
    return str(get_display(arabic_reshaper.reshape(embedded)))


def missing_glyphs(text: str, name: str = FONT_NAME) -> list[str]:
    """Code points of the shaped text that the bundled font cannot draw."""
    register_fonts()
    face = pdfmetrics.getFont(name).face  # type: ignore[attr-defined]
    return sorted({f"U+{ord(c):04X}" for c in shape(text) if ord(c) not in face.charToGlyph and not c.isspace()})


@lru_cache(maxsize=32)
def pil_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Pillow font from the bundled file with the basic (non-raqm) layout engine."""
    path = font_path(FONT_NAME_BOLD if bold else FONT_NAME)
    return ImageFont.truetype(str(path), size=size, layout_engine=ImageFont.Layout.BASIC)
