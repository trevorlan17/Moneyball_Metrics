"""Text measurement and fitting.

PowerPoint text boxes grow to fit their content, so a layout that assumes a fixed
number of lines will silently overlap the block beneath it. Every stacked layout in
deck.py measures its text first and lays out from the measured heights.

Measurement sums per-glyph ADVANCE widths read once from the deck's font file. The
previous version built a matplotlib TextPath for every word: accurate, but ~10 seconds
per build and another ~10 per layout check, in every CLI process, because the cache
starts cold each time. Advance widths are also what a text engine uses to break lines
(ink extents are not), so this is both faster and closer to PowerPoint.
"""
from __future__ import annotations

import functools

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager
from matplotlib.ft2font import FT2Font, LOAD_NO_HINTING

LINE_H = 1.22          # line box as a multiple of point size
PT_PER_IN = 72.0
_REF_PT = 1000.0       # glyphs are loaded once at this size and scaled


@functools.lru_cache(maxsize=4)
def _font(bold: bool) -> "matplotlib.font_manager.FontProperties":
    """The deck's actual face, resolved once and pinned.

    Resolving 'sans-serif' goes through matplotlib's global rcParams, which chart
    rendering mutates - so the same string could measure differently depending on
    whether a chart had been drawn yet. Metrics must not depend on call order.
    """
    from . import config
    typ = config.style()["typography"]
    available = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
    family = next((f for f in (typ["font"], typ["fallback"], "DejaVu Sans")
                   if f in available), "DejaVu Sans")
    return matplotlib.font_manager.FontProperties(
        family=family, weight="bold" if bold else "normal")


def font_in_use() -> str:
    return _font(False).get_family()[0]


@functools.lru_cache(maxsize=4)
def _face(bold: bool) -> FT2Font:
    path = matplotlib.font_manager.findfont(_font(bold), fallback_to_default=True)
    face = FT2Font(path)
    face.set_size(_REF_PT, 72)
    return face


@functools.lru_cache(maxsize=4096)
def _advance(ch: str, bold: bool) -> float:
    """Advance width of one character at 1pt, in points."""
    face = _face(bold)
    try:
        glyph = face.load_char(ord(ch), flags=LOAD_NO_HINTING)
    except (RuntimeError, ValueError):
        glyph = face.load_char(ord("n"), flags=LOAD_NO_HINTING)
    # linearHoriAdvance is 16.16 fixed point, in pixels at _REF_PT and 72 dpi,
    # which is points at _REF_PT.
    return glyph.linearHoriAdvance / 65536.0 / _REF_PT


@functools.lru_cache(maxsize=20000)
def measure(text: str, size_pt: float, bold: bool = False) -> float:
    """Width of one line of text, in inches."""
    if not text:
        return 0.0
    return sum(_advance(c, bold) for c in text) * size_pt / PT_PER_IN


@functools.lru_cache(maxsize=200)
def _space_width(size_pt: float, bold: bool) -> float:
    return _advance(" ", bold) * size_pt / PT_PER_IN


def wrap(text: str, size_pt: float, width_in: float, bold: bool = False) -> list[str]:
    """Greedy wrap to a width, the way a text box does it. Honours explicit newlines."""
    # Folded YAML strings (`title: >`) end in a newline. Counting the empty paragraph
    # after it measured every such title, note and source one line too tall.
    text = str(text).strip() if text else ""
    if width_in <= 0 or not text:
        return [text] if text else []
    lines: list[str] = []
    sw = _space_width(size_pt, bold)
    for para in str(text).split("\n"):
        cur_words: list[str] = []
        cur_w = 0.0
        for word in para.split():
            ww = measure(word, size_pt, bold)
            add = ww + (sw if cur_words else 0.0)
            if cur_words and cur_w + add > width_in:
                lines.append(" ".join(cur_words))
                cur_words, cur_w = [word], ww
            else:
                cur_words.append(word)
                cur_w += add
        lines.append(" ".join(cur_words))
    return lines


def height(text: str, size_pt: float, width_in: float, bold: bool = False,
           spacing: float = LINE_H) -> float:
    """Height this text needs at this size and width, in inches."""
    return len(wrap(text, size_pt, width_in, bold)) * size_pt * spacing / PT_PER_IN


def fit(text: str, width_in: float, max_height_in: float, sizes: list[float],
        bold: bool = False, spacing: float = LINE_H) -> tuple[float, float]:
    """Largest size from `sizes` whose text fits the box. Returns (size, height).

    Falls back to the smallest size if nothing fits. Callers that must not go below a
    readable floor should treat `height > max_height_in` as an overflow, not shrink.
    """
    for size in sorted(sizes, reverse=True):
        h = height(text, size, width_in, bold, spacing)
        if h <= max_height_in:
            return size, h
    smallest = min(sizes)
    return smallest, height(text, smallest, width_in, bold, spacing)


def stack(blocks: list[tuple[str, float, bool]], width_in: float,
          spacing: float = LINE_H, gap_in: float = 0.0) -> float:
    """Total height of several text blocks laid out one under another."""
    total = 0.0
    for text, size, bold in blocks:
        total += height(text, size, width_in, bold, spacing) + gap_in
    return max(total - gap_in, 0.0)
