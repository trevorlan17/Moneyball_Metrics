"""Render a built .pptx to PNG previews, and check text for overflow.

Two jobs:
  1. Give anyone without PowerPoint open a look at what was built.
  2. Catch the failure mode a claim linter cannot see - text that runs out of its box,
     or boxes that collide. A slide can be factually perfect and still unreadable.

The renderer approximates PowerPoint's text layout using matplotlib font metrics. It is
close enough to catch overflow; it is not a pixel-accurate substitute for opening the
file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager
import matplotlib.textpath
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch, Rectangle
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR
from pptx import Presentation
from pptx.util import Emu

from . import config, textfit as tf, util

EMU_IN = 914400.0
LINE_H = tf.LINE_H


def _shape_text(shape) -> list[dict[str, Any]]:
    # Table cells have a text_frame but no has_text_frame flag.
    if not getattr(shape, "has_text_frame", hasattr(shape, "text_frame")):
        return []
    out = []
    for p in shape.text_frame.paragraphs:
        text = "".join(r.text for r in p.runs)
        if not text.strip():
            continue
        r0 = p.runs[0]
        size = r0.font.size.pt if r0.font.size else 12
        colour = "#333333"
        try:
            if r0.font.color is not None and r0.font.color.type is not None:
                colour = "#" + str(r0.font.color.rgb)
        except (AttributeError, TypeError, ValueError):
            pass
        # The paragraph's line-spacing multiple. Measuring every box at single spacing
        # while the deck asked for 1.14 is how the checker passed slides whose
        # paragraphs visibly ran into each other.
        mult = p.line_spacing if isinstance(p.line_spacing, float) else 1.0
        out.append({"text": text, "size": size, "bold": bool(r0.font.bold),
                    "colour": colour, "mult": mult,
                    "align": str(p.alignment).split(".")[-1] if p.alignment else "LEFT"})
    return out


def _wrap_lines(text: str, size_pt: float, width_in: float, bold: bool = False) -> list[str]:
    return tf.wrap(text, size_pt, width_in, bold) or [text]


def _wrap_count(text: str, size_pt: float, width_in: float, bold: bool = False) -> int:
    return len(_wrap_lines(text, size_pt, width_in, bold))


def analyse(pptx_path: Path) -> dict[str, Any]:
    """Geometry check: text overflow and off-canvas shapes."""
    prs = Presentation(str(pptx_path))
    W = prs.slide_width / EMU_IN
    H = prs.slide_height / EMU_IN
    issues = []
    for i, slide in enumerate(prs.slides, 1):
        boxes: list[tuple] = []
        for shape in slide.shapes:
            try:
                x, y = shape.left / EMU_IN, shape.top / EMU_IN
                w, h = shape.width / EMU_IN, shape.height / EMU_IN
            except TypeError:
                continue
            if x < -0.05 or y < -0.05 or x + w > W + 0.05 or y + h > H + 0.05:
                issues.append({
                    "slide": i, "kind": "off_canvas",
                    "detail": f"shape at [{x:.2f},{y:.2f} {w:.2f}x{h:.2f}] "
                              f"extends past the {W:.2f}x{H:.2f} canvas",
                })
            paras = _shape_text(shape)
            if not paras:
                continue
            needed = sum(_wrap_count(p["text"], p["size"], w, p["bold"])
                         * p["size"] * LINE_H * p.get("mult", 1.0) / 72 for p in paras)
            # Textboxes auto-grow downward in PowerPoint, so only flag a real overrun.
            if needed > h + 0.14:
                issues.append({
                    "slide": i, "kind": "text_overflow",
                    "detail": f"needs ~{needed:.2f}in in a {h:.2f}in box: "
                              f"\"{paras[0]['text'][:58]}...\"",
                    "overflow_in": round(needed - h, 2),
                })
            # Collision is judged on the area the text actually occupies. A text box
            # taller than its content does not collide with anything - PowerPoint
            # renders from the top and does not clip.
            boxes.append((x, y, w, needed, paras[0]["text"]))

        issues.extend(_overlaps(i, boxes))
    return {"deck": str(pptx_path), "slides": len(prs.slides), "issues": issues}


def _overlaps(slide_no: int, boxes: list[tuple]) -> list[dict[str, Any]]:
    """Text blocks that land on top of each other.

    Overflow-within-a-box is not enough: two correctly sized boxes placed at fixed
    offsets still collide once one of them wraps. That is the classic generated-deck
    failure, so it is checked explicitly.
    """
    out = []
    tol = 0.05          # ignore hairline touches
    for a in range(len(boxes)):
        ax, ay, aw, ah, atext = boxes[a]
        for b in range(a + 1, len(boxes)):
            bx, by, bw, bh, btext = boxes[b]
            ox = min(ax + aw, bx + bw) - max(ax, bx)
            oy = min(ay + ah, by + bh) - max(ay, by)
            if ox > tol and oy > tol:
                out.append({
                    "slide": slide_no, "kind": "text_overlap",
                    "detail": f"\"{atext[:30]}\" overlaps \"{btext[:30]}\" "
                              f"by {ox:.2f}x{oy:.2f}in",
                    "overlap_in": round(oy, 2),
                })
    return out


def render(pptx_path: Path, out_dir: Path, theme_name: str = "light") -> list[str]:
    prs = Presentation(str(pptx_path))
    W = prs.slide_width / EMU_IN
    H = prs.slide_height / EMU_IN
    t = config.theme(theme_name)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    for i, slide in enumerate(prs.slides, 1):
        # Paint the slide's OWN background. Using the project's configured theme drew a
        # dark deck on white, which hid every title and logo in the preview.
        bg = "#" + t["background"]
        try:
            if slide.background.fill.type == 1:
                bg = "#" + str(slide.background.fill.fore_color.rgb)
        except (AttributeError, TypeError, ValueError):
            pass
        fig, ax = plt.subplots(figsize=(W, H))
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.axis("off")
        fig.patch.set_facecolor(bg)

        for shape in slide.shapes:
            try:
                x, y = shape.left / EMU_IN, shape.top / EMU_IN
                w, h = shape.width / EMU_IN, shape.height / EMU_IN
            except TypeError:
                continue

            fill = None
            try:
                if shape.fill.type is not None and shape.fill.type == 1:
                    fill = "#" + str(shape.fill.fore_color.rgb)
            except (AttributeError, TypeError, ValueError):
                pass
            is_oval = False
            try:
                is_oval = shape.auto_shape_type == MSO_SHAPE.OVAL
            except (AttributeError, ValueError, NotImplementedError):
                pass
            if fill and is_oval:
                ax.add_patch(Ellipse((x + w / 2, y + h / 2), w, h, facecolor=fill,
                                     edgecolor="none", zorder=1))
            elif fill:
                ax.add_patch(FancyBboxPatch(
                    (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.04",
                    facecolor=fill, edgecolor="none", zorder=1))

            if getattr(shape, "has_table", False) and shape.has_table:
                _draw_table(ax, shape, x, y)
                continue

            if shape.shape_type == 13:  # picture
                try:
                    img = plt.imread(shape.image.blob and __import__("io").BytesIO(shape.image.blob))
                    ax.imshow(img, extent=(x, x + w, y + h, y), zorder=2, aspect="auto")
                except Exception:
                    ax.add_patch(Rectangle((x, y), w, h, facecolor="none",
                                           edgecolor="#" + t["rule"], ls="--", zorder=2))
                continue

            paras = _shape_text(shape)
            ty = y
            try:
                if shape.text_frame.vertical_anchor == MSO_ANCHOR.MIDDLE and paras:
                    block = sum(len(_wrap_lines(q["text"], q["size"], w, q["bold"]))
                                * q["size"] * LINE_H * q.get("mult", 1.0) / 72 for q in paras)
                    ty = y + (h - block) / 2
            except AttributeError:
                pass
            for p in paras:
                wrapped = _wrap_lines(p["text"], p["size"], w, p["bold"])
                lines = len(wrapped)
                ha = "center" if "CENTER" in p["align"] else ("right" if "RIGHT" in p["align"] else "left")
                tx = x + w / 2 if ha == "center" else (x + w if ha == "right" else x)
                # va="top" already anchors at the top edge; the old proportional
                # offset pushed large text down and made correct layouts look broken.
                # A dollar sign in slide text ("$715 a seat") opens matplotlib
                # mathtext, which swallows everything up to the next "$" and renders it
                # italic without the signs. The preview is how a human checks the deck,
                # so it has to show what PowerPoint will show.
                ax.text(tx, ty + 0.02, "\n".join(wrapped).replace("$", r"\$"),
                        fontsize=p["size"] * 0.98, color=p["colour"],
                        fontweight="bold" if p["bold"] else "normal",
                        va="top", ha=ha, zorder=5, linespacing=1.18 * p.get("mult", 1.0),
                        fontproperties=tf._font(p["bold"]))
                ty += lines * p["size"] * LINE_H * p.get("mult", 1.0) / 72

        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        out = out_dir / f"slide_{i:02d}.png"
        fig.savefig(out, dpi=110, facecolor=bg)
        plt.close(fig)
        written.append(str(out))
    return written


def _draw_table(ax, shape, x0, y0):
    """Approximate a native table: cell fills and first-run text, so reviewers see it."""
    tbl = shape.table
    y = y0
    for r_i, row in enumerate(tbl.rows):
        rh = row.height / EMU_IN
        x = x0
        for c_i, col in enumerate(tbl.columns):
            cw = col.width / EMU_IN
            cell = tbl.cell(r_i, c_i)
            fill = "#223355"
            try:
                fill = "#" + str(cell.fill.fore_color.rgb)
            except (AttributeError, TypeError, ValueError):
                pass
            ax.add_patch(Rectangle((x, y), cw, rh, facecolor=fill, edgecolor="#FFFFFF",
                                   lw=0.6, zorder=1))
            paras = _shape_text(cell) if hasattr(cell, "text_frame") else []
            if paras:
                pr = paras[0]
                ax.text(x + 0.08 if c_i == 0 else x + cw / 2, y + rh / 2,
                        "\n".join(_wrap_lines(pr["text"], pr["size"], cw - 0.2, pr["bold"])).replace("$", r"\$"),
                        fontsize=pr["size"] * 0.98, color=pr["colour"], va="center",
                        ha="left" if c_i == 0 else "center", zorder=5,
                        fontweight="bold" if pr["bold"] else "normal",
                        fontproperties=tf._font(pr["bold"]))
            x += cw
        y += rh


def run(project, deck_path: Path | None = None) -> dict[str, Any]:
    if deck_path is None:
        decks = sorted(project.path("decks").glob("*.pptx"),
                       key=lambda p: p.stat().st_mtime)
        if not decks:
            raise SystemExit("No deck built yet.")
        deck_path = decks[-1]
    theme = project.cfg.get("theme", "light")
    result = analyse(Path(deck_path))
    result["previews"] = render(Path(deck_path), project.path("decks/preview"), theme)
    util.write_json(project.path("qa/layout_report.json"), result)
    return result
