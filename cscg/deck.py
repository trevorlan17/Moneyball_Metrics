"""Deck builder: storyline.yaml -> .pptx.

No LLM runs in here. The storyline agent writes structured YAML; this module renders it
against config/presentation_style.yaml. That separation keeps the deck restyleable
without regenerating the argument.

Layout discipline, all of it learned from decks that came out wrong:

* ONE spacing model. Every text box is created with a line-spacing multiple and measured
  with the same multiple (`self._h`). Measuring at 1.14 x size while PowerPoint renders
  1.14 x single spacing (~1.37 x size) is what made paragraphs run into each other.
* The evidence zone starts under the MEASURED title and ends above the MEASURED source
  line. No fixed body_top, so no dead band under one-line titles.
* Type never shrinks below `min_readable`. When text will not fit at the floor the
  builder records an overflow - the fix is fewer words, not smaller ones.
* Logos, not names: CSCG mark and client logo on the cover and in every footer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from . import charts as chartlib, config, textfit as tf, util
from .findings import FindingStore


def _rgb(hexstr: str) -> RGBColor:
    return RGBColor.from_string(hexstr.lstrip("#").upper())


def _luminance(hexstr: str) -> float:
    h = hexstr.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def resolve_asset(path: str | None, project) -> Path | None:
    if not path:
        return None
    p = Path(path)
    # Repo root first: resolving against the working directory made logos vanish
    # whenever the CLI was run from anywhere but the repo.
    for cand in (config.ROOT / p, project.root / p, p):
        if cand.exists():
            return cand
    return None


def client_logo_for(project, meta: dict | None = None) -> Path | None:
    meta = meta or {}
    brand = config.style().get("brand", {})
    client = meta.get("client") or project.cfg.get("client", "")
    ref = (meta.get("client_logo") or project.cfg.get("client_logo")
           or brand.get("known_client_logos", {}).get(client))
    return resolve_asset(ref, project)


class DeckBuilder:
    def __init__(self, project, store: FindingStore, storyline: dict[str, Any]):
        self.project = project
        self.store = store
        self.sl = storyline
        self.style = config.style()
        self.grid = self.style["grid"]
        self.type = self.style["typography"]
        self.sizes = self.type["sizes"]
        self.floor = self.type.get("min_readable", {})
        meta = storyline.get("meta", {}) or {}
        self.theme_name = (meta.get("theme") or project.cfg.get("theme")
                           or self.style.get("default_theme", "light"))
        self.t = dict(config.theme(self.theme_name))
        accent = meta.get("accent_override") or project.cfg.get("accent_override")
        if accent:
            self.t["accent"] = accent.lstrip("#")
        self.dark = _luminance(self.t["background"]) < 0.4
        self.label_colour = self.t["pill"] if self.dark else self.t["accent_deep"]

        brand = self.style.get("brand", {})
        self.brand = brand
        self.cscg_logo = resolve_asset(
            brand.get("cscg_logo", {}).get("dark" if self.dark else "light"), project)
        self.client = meta.get("client") or project.cfg.get("client", "")
        self.client_logo = client_logo_for(project, meta)

        self.synthetic = bool(meta.get("synthetic", project.cfg.get("synthetic_data", False)))
        self.term = meta.get("term") or project.cfg.get("term", "")
        self.prs = Presentation()
        self.prs.slide_width = Inches(self.style["canvas"]["width_in"])
        self.prs.slide_height = Inches(self.style["canvas"]["height_in"])
        self.page = self.style["footer"]["page_number_starts_at"] - 1
        self.chart_dir = project.path("charts")

        self.sections: list[str] = []
        for sp in storyline.get("slides", []):
            if sp.get("layout") == "agenda":
                self.sections = [str(x) for x in sp.get("items", [])]
                break
        self.current_section: str | None = None
        self.slide_no = 0
        self.overflows: list[dict[str, Any]] = []

    # -- measurement -------------------------------------------------------
    def _h(self, text, size, width, bold=False, mult=1.0) -> float:
        """Rendered height of a text box created with line-spacing multiple `mult`."""
        return tf.height(str(text or ""), size, width, bold, spacing=tf.LINE_H * mult)

    def _overflow(self, element: str, need: float, have: float) -> None:
        self.overflows.append({
            "slide": self.slide_no, "kind": "text_overflow",
            "detail": f"{element}: needs {need:.2f}in, has {have:.2f}in at the minimum "
                      f"readable size - cut words",
            "overflow_in": round(need - have, 2)})

    def _fit_sizes(self, texts, width, max_h, sizes, bold=False, mult=1.0, gap=0.0):
        """Largest size at which all `texts` stacked fit `max_h`. Records overflow at floor."""
        for size in sizes:
            need = sum(self._h(x, size, width, bold, mult) for x in texts) + gap * max(len(texts) - 1, 0)
            if need <= max_h:
                return size, need
        return sizes[-1], need

    # -- primitives --------------------------------------------------------
    def _blank(self):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        bg = s.background.fill
        bg.solid()
        bg.fore_color.rgb = _rgb(self.t["background"])
        return s

    def _text(self, slide, x, y, w, h, text, *, size=None, bold=False, colour=None,
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, mult=1.0, caps=False):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(max(h, 0.1)))
        frame = box.text_frame
        frame.word_wrap = True
        frame.vertical_anchor = anchor
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        lines = str(text).strip().split("\n")
        for i, line in enumerate(lines):
            p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
            p.alignment = align
            p.line_spacing = mult
            r = p.add_run()
            r.text = line.upper() if caps else line
            r.font.name = self.type["font"]
            r.font.size = Pt(size or self.sizes["body"])
            r.font.bold = bold
            r.font.color.rgb = _rgb(colour or self.t["ink"])
        return box

    def _rich(self, slide, x, y, w, h, segments, *, size=None, align=PP_ALIGN.LEFT, mult=1.0):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(max(h, 0.1)))
        frame = box.text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        p = frame.paragraphs[0]
        p.alignment = align
        p.line_spacing = mult
        for text, fmt in segments:
            r = p.add_run()
            r.text = str(text).replace("\n", " ").rstrip() if fmt is segments[-1][1] else str(text).replace("\n", " ")
            r.font.name = self.type["font"]
            r.font.size = Pt(fmt.get("size", size or self.sizes["body"]))
            r.font.bold = fmt.get("bold", False)
            r.font.color.rgb = _rgb(fmt.get("colour", self.t["card_body"]))
        return box

    def _card(self, slide, x, y, w, h, fill=None, radius=0.06, line=None):
        shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y),
                                     Inches(w), Inches(h))
        if fill == "none":
            shp.fill.background()
        else:
            shp.fill.solid()
            shp.fill.fore_color.rgb = _rgb(fill or self.t["card"])
        if line:
            shp.line.color.rgb = _rgb(line)
            shp.line.width = Pt(0.75)
        else:
            shp.line.fill.background()
        shp.shadow.inherit = False
        try:
            shp.adjustments[0] = radius
        except (IndexError, KeyError):
            pass
        return shp

    def _rect(self, slide, x, y, w, h, fill):
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                     Inches(w), Inches(h))
        shp.fill.solid()
        shp.fill.fore_color.rgb = _rgb(fill)
        shp.line.fill.background()
        shp.shadow.inherit = False
        return shp

    def _badge(self, slide, x, y, size, n):
        shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y),
                                     Inches(size), Inches(size))
        shp.fill.solid()
        shp.fill.fore_color.rgb = _rgb(self.t["pill"])
        shp.line.fill.background()
        shp.shadow.inherit = False
        frame = shp.text_frame
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = str(n)
        r.font.name = self.type["font"]
        r.font.size = Pt(14)
        r.font.bold = True
        r.font.color.rgb = _rgb(self.t["pill_ink"])
        return shp

    def _logo(self, slide, path: Path, x: float, y: float, h: float) -> float:
        with Image.open(path) as im:
            aspect = im.width / im.height
        slide.shapes.add_picture(str(path), Inches(x), Inches(y), height=Inches(h))
        return h * aspect

    # -- chrome ------------------------------------------------------------
    def _head(self, slide, kicker, title) -> float:
        """Eyebrow, optional kicker, action title. Returns the title's measured bottom."""
        g, s = self.grid, self.sizes
        cw = g["content_width"]
        self._text(slide, g["margin_left"], g["eyebrow_y"], 5.0, 0.2,
                   self.style["footer"]["eyebrow_template"].format(term=self.term).strip(),
                   size=s["eyebrow"], colour=self.t["muted"])
        if self.synthetic:
            self._text(slide, 7.8, g["eyebrow_y"], 4.98, 0.2,
                       self.style["footer"]["watermark_when_synthetic"], size=7.5,
                       bold=True, colour=self.t["warning"], align=PP_ALIGN.RIGHT)
        y = g["title_y"]
        if kicker:
            self._text(slide, g["margin_left"], g["kicker_y"], cw, 0.22, kicker,
                       size=s["kicker"], bold=True, colour=self.label_colour, caps=True)
            y = g["kicker_y"] + 0.30
        if not title:
            return y
        size = s["title_min"]
        for sz in (s["title"], s["title"] - 2, s["title_min"]):
            if len(tf.wrap(title, sz, cw, True)) <= g["title_max_lines"]:
                size = sz
                break
        h = self._h(title, size, cw, True)
        if len(tf.wrap(title, size, cw, True)) > g["title_max_lines"]:
            self._overflow("action title runs past two lines", h,
                           self._h("x\nx", size, cw, True))
        self._text(slide, g["margin_left"], y, cw, h + 0.04, title, size=size, bold=True,
                   colour=self.t["ink"])
        return y + h

    def _source(self, slide, source) -> float:
        """Source line anchored above the footer. Returns its top."""
        g = self.grid
        cw = g["content_width"]
        size = self.sizes["source"]
        h = self._h(source, size, cw)
        if len(tf.wrap(source, size, cw)) > 2:
            size = self.floor.get("source", 7.5)
            h = self._h(source, size, cw)
            if len(tf.wrap(source, size, cw)) > 2:
                self._overflow("source line longer than two lines", h,
                               self._h("x\nx", size, cw))
        top = g["footer_y"] - 0.10 - h
        self._text(slide, g["margin_left"], top, cw, h + 0.03, source, size=size,
                   colour=self.t["muted"])
        return top

    def _chrome(self, slide, kicker, title, subtitle=None, source=None):
        """Head + footer + source. Returns (body_top, body_bottom) - the evidence zone."""
        g = self.grid
        cw = g["content_width"]
        bottom = self._head(slide, kicker, title)
        if subtitle:
            sh = self._h(subtitle, 12, cw)
            self._text(slide, g["margin_left"], bottom + 0.10, cw, sh + 0.03, subtitle,
                       size=12, colour=self.t["muted"])
            bottom += 0.10 + sh
        body_top = max(bottom + g["title_to_body_gap"], g["body_top_min"])
        src_top = self._source(slide, source) if source else g["footer_y"] - 0.10
        body_bottom = min(g["body_bottom"], src_top - 0.14)
        self._footer(slide)
        return body_top, body_bottom

    def _footer(self, slide, numbered: bool = True):
        g, b, f = self.grid, self.brand, self.style["footer"]
        y = g["footer_y"] - 0.02
        x = b.get("footer_logo_x", 0.40)
        h = b.get("footer_logo_height", 0.40)
        if self.cscg_logo:
            x += self._logo(slide, self.cscg_logo, x, y, h) + b.get("footer_logo_gap", 0.22)
        if self.client_logo:
            self._logo(slide, self.client_logo, x, y + 0.02, h - 0.04)
        if f.get("confidential_on_every_slide"):
            self._text(slide, 10.6, g["footer_y"] + 0.08, 1.6, 0.2, f["confidential_label"],
                       size=self.sizes["footer"], colour=self.t["muted"], align=PP_ALIGN.RIGHT)
        if f.get("section_tabs") and self.sections and self.current_section:
            n = len(self.sections)
            tx, tw, th = f["section_tabs_x"], f["section_tabs_width"], f["section_tabs_height"]
            each = tw / n
            size = 9.5
            while size > 7.5 and any(tf.measure(s_, size, True) > each - 0.12 for s_ in self.sections):
                size -= 0.5
            for i, name in enumerate(self.sections):
                cur = name.strip().lower() == str(self.current_section).strip().lower()
                bx = tx + i * each
                self._card(slide, bx + 0.03, g["footer_y"] + 0.05, each - 0.06, th,
                           fill=self.t["pill"] if cur else "none", radius=0.1,
                           line=None if cur else self.t["rule"])
                self._text(slide, bx + 0.03, g["footer_y"] + 0.05, each - 0.06, th, name,
                           size=size, bold=cur, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                           colour=self.t["pill_ink"] if cur else self.t["muted"])
        if numbered and f["show_page_numbers"]:
            self.page += 1
            self._text(slide, 12.28, g["footer_y"] + 0.06, 0.55, 0.25, str(self.page),
                       size=self.sizes["footer"] + 2, colour=self.t["muted"], align=PP_ALIGN.RIGHT)

    # -- stacked cards -------------------------------------------------------
    def _stack_cards(self, slide, items, *, lead_key, detail_key, detail_label, top, bottom):
        g = self.grid
        pad = g["card_pad"]
        text_x = g["margin_left"] + 0.95
        text_w = g["content_width"] - 0.95 - pad
        available = bottom - top
        card_gap = 0.14
        pairs = [(15, 12.5), (14, 12), (13, 11.5), (self.floor.get("card_head", 12.5),
                                                    self.floor.get("body", 10.5))]
        for hs, ds in pairs:
            plans = []
            for it in items:
                lead = str(it.get(lead_key, "")).strip()
                detail = str(it.get(detail_key, "")).strip()
                lh = self._h(lead, hs, text_w, True)
                dh = self._h(f"{detail_label} {detail}", ds, text_w)
                plans.append((lead, detail, lh, dh, pad + lh + 0.08 + dh + pad))
            total = sum(p[4] for p in plans) + card_gap * (len(items) - 1)
            if total <= available:
                break
        else:
            self._overflow(f"{len(items)} stacked cards", total, available)

        n = max(len(items), 1)
        slack = max(available - total, 0.0)
        bonus = min(slack / n, 0.28)
        gap = card_gap + (min((slack - bonus * n) / (n - 1), 0.30) if n > 1 else 0)
        y = top
        for i, (lead, detail, lh, dh, h) in enumerate(plans):
            hf = h + bonus
            self._card(slide, g["margin_left"], y, g["content_width"], hf)
            self._badge(slide, g["margin_left"] + 0.25, y + pad, 0.44, i + 1)
            inner_top = y + (hf - (lh + 0.08 + dh)) / 2
            self._text(slide, text_x, inner_top, text_w, lh + 0.03, lead, size=hs, bold=True,
                       colour=self.t["card_ink"])
            self._rich(slide, text_x, inner_top + lh + 0.08, text_w, dh + 0.03, [
                (detail_label + " ", {"bold": True, "colour": self.label_colour, "size": ds}),
                (detail, {"colour": self.t["card_body"], "size": ds})])
            y += hf + gap

    # -- charts & tables ------------------------------------------------------
    def _place_chart(self, slide, res, x, y, max_w, max_h):
        """Fit a rendered chart to BOTH dimensions of its zone, centred horizontally."""
        aspect = res.get("aspect") or 0.5
        w = max_w
        h = w * aspect
        if h > max_h:
            h = max_h
            w = h / aspect
        slide.shapes.add_picture(res["png"], Inches(x + (max_w - w) / 2), Inches(y),
                                 width=Inches(w))
        return h

    def _draw_chart(self, slide, spec, x, y, w, h):
        spec = dict(spec)
        if spec.get("type") == "table":
            data = chartlib.table_data(spec, self.store)
            chartlib.write_table_sidecar(spec, data, self.chart_dir)
            return self._table(slide, data, x, y, w, h)
        spec["figsize"] = [w, h]
        res = chartlib.render(spec, self.store, self.chart_dir, self.theme_name)
        return self._place_chart(slide, res, x, y, w, h)

    def _table(self, slide, data, x, y, w, max_h):
        header, rows, hi = data["header"], data["rows"], data.get("highlight_row")
        ncols = len(header)
        first = w * (0.40 if ncols > 2 else 0.55)
        col_w = [first] + [(w - first) / max(ncols - 1, 1)] * (ncols - 1)
        cell_pad_x, cell_pad_y = 0.10, 0.07

        def row_h(cells, size, bold):
            return max(self._h(c, size, cw - 2 * cell_pad_x, bold) for c, cw in zip(cells, col_w)) + 2 * cell_pad_y

        for size in (12, 11.5, 11, self.floor.get("body", 10.5)):
            heights = [row_h(header, size, True)] + [row_h(r, size, False) for r in rows]
            if sum(heights) <= max_h:
                break
        else:
            self._overflow(f"table of {len(rows)} rows", sum(heights), max_h)

        gf = slide.shapes.add_table(len(rows) + 1, ncols, Inches(x), Inches(y),
                                    Inches(w), Inches(sum(heights)))
        tbl = gf.table
        tbl.first_row = True
        tbl.horz_banding = False
        for j, cw in enumerate(col_w):
            tbl.columns[j].width = Inches(cw)
        for i, rh in enumerate(heights):
            tbl.rows[i].height = Inches(rh)
        for i, cells in enumerate([header] + rows):
            is_head = i == 0
            is_hi = hi is not None and i == hi + 1
            fill = (self.t["pill"] if is_head else self.t["accent"] if is_hi
                    else self.t["card"] if i % 2 else self.t["card_alt"])
            ink = (self.t["pill_ink"] if is_head or is_hi else self.t["card_body"])
            for j, value in enumerate(cells):
                cell = tbl.cell(i, j)
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(fill)
                cell.margin_left = cell.margin_right = Inches(cell_pad_x)
                cell.margin_top = cell.margin_bottom = Inches(cell_pad_y)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                frame = cell.text_frame
                frame.word_wrap = True
                p = frame.paragraphs[0]
                p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
                r = p.add_run()
                r.text = str(value)
                r.font.name = self.type["font"]
                r.font.size = Pt(size)
                r.font.bold = is_head or is_hi or j == 0
                r.font.color.rgb = _rgb(self.t["card_ink"] if (j == 0 and not (is_head or is_hi)) else ink)
        return sum(heights)

    # -- layouts -----------------------------------------------------------
    def layout_title(self, sp):
        slide = self._blank()
        b, s, g = self.brand, self.sizes, self.grid
        h = b.get("title_lockup_height", 1.55)
        x, y = 0.95, 1.30
        if self.cscg_logo:
            x += self._logo(slide, self.cscg_logo, x, y, h)
        else:
            x += 0.0
        client_w = 0.0
        if self.client_logo or self.client:
            div_x = x + 0.40
            self._rect(slide, div_x, y + 0.08, 0.025, h - 0.16, self.t["ink"])
            cx = div_x + 0.42
            if self.client_logo:
                client_w = self._logo(slide, self.client_logo, cx, y + h * 0.08, h * 0.84)
            else:
                # No logo on file: the name stands in, sized to the lockup.
                self._text(slide, cx, y, 6.0, h, self.client, size=34, bold=True,
                           colour=self.t["ink"], anchor=MSO_ANCHOR.MIDDLE)
        subject = sp.get("subject", "")
        sy = y + h + 0.60
        size = 32
        for sz in (40, 36, 32):
            if len(tf.wrap(subject, sz, 11.4, True)) <= 2:
                size = sz
                break
        sh = self._h(subject, size, 11.4, True)
        self._text(slide, 0.95, sy, 11.4, sh + 0.05, subject, size=size, bold=True,
                   colour=self.t["ink"])
        sy += sh + 0.18
        if sp.get("descriptor"):
            dh = self._h(sp["descriptor"], 17, 11.4)
            self._text(slide, 0.95, sy, 11.4, dh + 0.03, sp["descriptor"], size=17,
                       colour=self.t["muted"])
            sy += dh + 0.14
        if sp.get("date"):
            self._text(slide, 0.95, sy, 8.0, 0.3, str(sp["date"]), size=13,
                       colour=self.t["muted"])
        self._text(slide, 0.95, 6.95, 8.0, 0.2, self.style["footer"]["confidential_label"],
                   size=8, colour=self.t["muted"])
        if self.synthetic:
            self._text(slide, 0.95, 7.15, 8.0, 0.2,
                       self.style["footer"]["watermark_when_synthetic"], size=8,
                       bold=True, colour=self.t["warning"])

    def layout_agenda(self, sp):
        """Slide 2: 3-6 short sections in a row of boxes (Peter Millar final)."""
        slide = self._blank()
        top, bottom = self._chrome(slide, None, sp.get("title", "Agenda"))
        g = self.grid
        items = [str(x) for x in sp.get("items", [])][:6]
        if not items:
            return
        n = len(items)
        gap = 0.30
        w = (g["content_width"] - gap * (n - 1)) / n
        box_h = min(1.75, bottom - top)
        y = top + (bottom - top - box_h) / 2 - 0.15
        inner = w - 0.36
        size, need = self._fit_sizes(items, inner, box_h - 0.70, [18, 16, 15, 14, 12.5], True)
        if max(self._h(x, size, inner, True) for x in items) > box_h - 0.70:
            self._overflow("agenda item", need, box_h - 0.70)
        # Connector behind the boxes.
        self._rect(slide, g["margin_left"] + w / 2, y + box_h / 2 - 0.012,
                   g["content_width"] - w, 0.024, self.t["rule"])
        for i, label in enumerate(items):
            bx = g["margin_left"] + i * (w + gap)
            self._card(slide, bx, y, w, box_h, fill=self.t["pill"], radius=0.12)
            self._text(slide, bx, y + 0.18, w, 0.25, f"{i + 1:02d}", size=11, bold=True,
                       colour=self.t["pill_ink"], align=PP_ALIGN.CENTER)
            lh = self._h(label, size, inner, True)
            self._text(slide, bx + 0.18, y + 0.45 + (box_h - 0.60 - lh) / 2, inner, lh + 0.04,
                       label, size=size, bold=True, colour=self.t["pill_ink"],
                       align=PP_ALIGN.CENTER)

    def layout_executive_summary(self, sp):
        slide = self._blank()
        top, bottom = self._chrome(slide, sp.get("kicker"), sp.get("title"),
                                   source=sp.get("source"))
        self._stack_cards(slide, sp.get("findings", []), lead_key="statement",
                          detail_key="so_what", detail_label="So what:", top=top, bottom=bottom)

    def layout_discussion_questions(self, sp):
        slide = self._blank()
        top, bottom = self._chrome(slide, sp.get("kicker"), sp.get("title"),
                                   source=sp.get("source"))
        self._stack_cards(slide, sp.get("questions", []), lead_key="question",
                          detail_key="why", detail_label="Why it matters:", top=top, bottom=bottom)

    def _stat_cards(self, slide, stats, top, max_h):
        g, s = self.grid, self.sizes
        pad = g["card_pad"]
        n = len(stats)
        w = (g["content_width"] - g["gutter"] * (n - 1)) / n
        inner = w - 2 * pad
        hero_size, _ = tf.fit(max((str(x.get("value", "")) for x in stats), key=len),
                              inner, 0.85, [s["stat_hero"], 36, 32, 28], bold=True)
        hero_h = max(self._h(str(x.get("value", "")), hero_size, inner, True) for x in stats)
        for cap_size in (12.5, 12, 11.5, self.floor.get("body", 10.5)):
            cap_h = max(self._h(x.get("label", ""), cap_size, inner) for x in stats)
            card_h = pad + hero_h + 0.10 + cap_h + pad
            if card_h <= max_h:
                break
        else:
            self._overflow("stat captions", card_h, max_h)
        for i, st in enumerate(stats):
            x = g["margin_left"] + i * (w + g["gutter"])
            self._card(slide, x, top, w, card_h)
            self._text(slide, x + pad, top + pad, inner, hero_h + 0.04, str(st.get("value", "")),
                       size=hero_size, bold=True, colour=self.t["pill"] if self.dark else self.t["accent"])
            self._text(slide, x + pad, top + pad + hero_h + 0.10, inner, cap_h + 0.03,
                       st.get("label", ""), size=cap_size, colour=self.t["card_body"])
        return card_h

    def layout_how_to_read(self, sp):
        slide = self._blank()
        top, bottom = self._chrome(slide, sp.get("kicker"), sp.get("title"),
                                   source=sp.get("source"))
        g = self.grid
        stats = sp.get("stats", [])[:4]
        y = top
        if stats:
            y += self._stat_cards(slide, stats, top, (bottom - top) * 0.42) + 0.28
        bullets = sp.get("bullets", [])
        if not bullets:
            return
        text_w = g["content_width"] - 0.32
        room = bottom - y
        for size in (12.5, 12, 11.5, 11, self.floor.get("body", 10.5)):
            need = sum(self._h(bl, size, text_w) + 0.12 for bl in bullets)
            if need <= room:
                break
        else:
            self._overflow(f"{len(bullets)} bullets", need, room)
        for bl in bullets:
            bh = self._h(bl, size, text_w)
            self._text(slide, g["margin_left"], y, 0.3, bh, "•", size=size, bold=True,
                       colour=self.label_colour)
            self._text(slide, g["margin_left"] + 0.32, y, text_w, bh + 0.03, bl, size=size,
                       colour=self.t["body"])
            y += bh + 0.12

    def _notes(self, slide, notes, x, w, top, bottom):
        pad = self.grid["card_pad"]
        inner = w - 2 * pad
        n = len(notes)
        gap = 0.16
        avail = bottom - top - gap * (n - 1)
        for size in (12.5, 12, 11.5, 11, self.floor.get("note", 10.5)):
            hs = [pad + 0.24 + 0.08 + self._h(nt.get("text", ""), size, inner) + pad for nt in notes]
            if sum(hs) <= avail:
                break
        else:
            self._overflow(f"{n} annotation boxes", sum(hs), avail)
        slack = max(avail - sum(hs), 0)
        bonus = min(slack / max(n, 1), 0.45)
        extra_gap = min((slack - bonus * n) / max(n - 1, 1), 0.30) if n > 1 else 0
        y = top
        for nt, h in zip(notes, hs):
            hf = h + bonus
            self._card(slide, x, y, w, hf)
            self._text(slide, x + pad, y + pad, inner, 0.24, nt.get("label", ""), size=10,
                       bold=True, colour=self.label_colour, caps=True)
            th = self._h(nt.get("text", ""), size, inner)
            self._text(slide, x + pad, y + pad + 0.32, inner, th + 0.03, nt.get("text", ""),
                       size=size, colour=self.t["card_body"])
            y += hf + gap + extra_gap

    def layout_chart_with_notes(self, sp):
        slide = self._blank()
        top, bottom = self._chrome(slide, sp.get("kicker"), sp.get("title"),
                                   subtitle=sp.get("subtitle"), source=sp.get("source"))
        g = self.grid
        geom = self.style["layouts"]["chart_with_notes"]["geometry"]
        notes = sp.get("notes", [])[:3]
        cx = geom["chart_x"]
        cw = geom["chart_width"] if notes else g["content_width"]
        y = top
        if sp.get("chart_caption"):
            ch = self._h(sp["chart_caption"], 12, cw, True)
            self._text(slide, cx, y, cw, ch + 0.03, sp["chart_caption"], size=12, bold=True,
                       colour=self.t["ink"])
            y += ch + 0.12
        if sp.get("chart"):
            self._draw_chart(slide, sp["chart"], cx, y, cw, bottom - y)
        if notes:
            self._notes(slide, notes, geom["notes_x"], geom["notes_width"], top, bottom)

    def layout_comparison_pair(self, sp):
        slide = self._blank()
        top, bottom = self._chrome(slide, sp.get("kicker"), sp.get("title"),
                                   subtitle=sp.get("subtitle"), source=sp.get("source"))
        g = self.grid
        cw = g["content_width"]
        specs = sp.get("charts", [])[:2]
        cap_text = sp.get("caption")
        cap_size = 12
        cap_h = self._h(cap_text, cap_size, cw) if cap_text else 0.0
        floor = bottom - (cap_h + 0.14 if cap_text else 0)
        side_by_side = sp.get("arrangement") == "side_by_side" or any(
            s.get("type") in ("donut", "pie", "column", "table") for s in specs)
        content_bottom = top
        if side_by_side:
            w = (cw - 0.40) / max(len(specs), 1)
            for i, spec in enumerate(specs):
                x = g["margin_left"] + i * (w + 0.40)
                y = top
                if spec.get("caption"):
                    hh = self._h(spec["caption"], 12, w, True)
                    self._text(slide, x, y, w, hh + 0.03, spec["caption"], size=12, bold=True,
                               colour=self.t["ink"])
                    y += hh + 0.10
                ch = self._draw_chart(slide, spec, x, y, w, floor - y)
                content_bottom = max(content_bottom, y + (ch or 0))
        else:
            n = max(len(specs), 1)
            each = (floor - top) / n
            for i, spec in enumerate(specs):
                y = top + i * each
                hh = 0.0
                if spec.get("caption"):
                    hh = self._h(spec["caption"], 12, cw, True) + 0.08
                    self._text(slide, g["margin_left"], y, cw, hh, spec["caption"], size=12,
                               bold=True, colour=self.t["ink"])
                ch = self._draw_chart(slide, spec, g["margin_left"], y + hh, cw, each - hh - 0.10)
                content_bottom = max(content_bottom, y + hh + (ch or 0))
        if cap_text:
            # Directly under what was drawn. Pinning the caption to the floor left a
            # hole under any chart shorter than its zone - a two-row table especially.
            cap_y = min(floor + 0.10, content_bottom + 0.30)
            self._text(slide, g["margin_left"], cap_y, cw, cap_h + 0.03, cap_text,
                       size=cap_size, colour=self.t["body"])

    def layout_quotes_themes(self, sp):
        slide = self._blank()
        top, bottom = self._chrome(slide, sp.get("kicker"), sp.get("title"),
                                   source=sp.get("source"))
        g = self.grid
        pad = g["card_pad"]
        themes = sp.get("themes", [])[:4]
        if not themes:
            return
        w = (g["content_width"] - g["gutter"] * (len(themes) - 1)) / len(themes)
        inner = w - 2 * pad
        head_size, _ = tf.fit(max((x.get("name", "") for x in themes), key=len), inner, 0.62,
                              [15, 14, 13, self.floor.get("card_head", 12.5)], bold=True)
        for qsize in (12, 11.5, 11, self.floor.get("body", 10.5)):
            needs = []
            for th in themes:
                need = pad + self._h(th.get("name", ""), head_size, inner, True) + 0.12
                need += self._h(th.get("prevalence", ""), 10.5, inner, True) + 0.22
                for q in th.get("quotes", [])[:2]:
                    need += self._h(f"“{q.get('text', '')}”", qsize, inner) + 0.06
                    need += self._h(f"— {q.get('attribution', '')}", 9.5, inner) + 0.22
                needs.append(need + pad)
            if max(needs) <= bottom - top:
                break
        else:
            self._overflow("theme column", max(needs), bottom - top)
        card_h = min(max(needs), bottom - top) if needs else bottom - top
        for i, th in enumerate(themes):
            x = g["margin_left"] + i * (w + g["gutter"])
            self._card(slide, x, top, w, card_h)
            y = top + pad
            nh = self._h(th.get("name", ""), head_size, inner, True)
            self._text(slide, x + pad, y, inner, nh + 0.03, th.get("name", ""), size=head_size,
                       bold=True, colour=self.t["card_ink"])
            y += nh + 0.12
            ph = self._h(th.get("prevalence", ""), 10.5, inner, True)
            self._text(slide, x + pad, y, inner, ph + 0.03, th.get("prevalence", ""), size=10.5,
                       bold=True, colour=self.label_colour)
            y += ph + 0.22
            for q in th.get("quotes", [])[:2]:
                text = f"“{q.get('text', '')}”"
                qh = self._h(text, qsize, inner)
                self._text(slide, x + pad, y, inner, qh + 0.03, text, size=qsize,
                           colour=self.t["card_body"])
                y += qh + 0.06
                attr = f"— {q.get('attribution', '')}"
                ah = self._h(attr, 9.5, inner)
                self._text(slide, x + pad, y, inner, ah + 0.03, attr, size=9.5,
                           colour=self.t["muted"] if not self.dark else self.t["pill"])
                y += ah + 0.22

    def layout_stat_row(self, sp):
        slide = self._blank()
        top, bottom = self._chrome(slide, sp.get("kicker"), sp.get("title"),
                                   source=sp.get("source"))
        stats = sp.get("stats", [])[:4]
        if stats:
            self._stat_cards(slide, stats, top, bottom - top)

    def layout_three_cards(self, sp):
        slide = self._blank()
        top, bottom = self._chrome(slide, sp.get("kicker"), sp.get("title"),
                                   source=sp.get("source"))
        g = self.grid
        pad = g["card_pad"]
        cards = sp.get("cards", [])[:4]
        if not cards:
            return
        w = (g["content_width"] - g["gutter"] * (len(cards) - 1)) / len(cards)
        inner = w - 2 * pad
        for hs, bs in ((16, 12.5), (15, 12), (14, 11.5), (self.floor.get("card_head", 12.5),
                                                         self.floor.get("body", 10.5))):
            needs = []
            for c in cards:
                need = pad + 0.50 + 0.18 + self._h(c.get("head", ""), hs, inner, True)
                if c.get("sub"):
                    need += 0.08 + self._h(c["sub"], bs, inner, True)
                need += sum(0.12 + self._h(b_, bs, inner) for b_ in c.get("bullets", [])[:4])
                needs.append(need + pad)
            if max(needs) <= bottom - top:
                break
        else:
            self._overflow("card column", max(needs), bottom - top)
        card_h = min(max(needs) + 0.2, bottom - top)
        for i, c in enumerate(cards):
            x = g["margin_left"] + i * (w + g["gutter"])
            self._card(slide, x, top, w, card_h)
            y = top + pad
            self._badge(slide, x + pad, y, 0.50, c.get("n", i + 1))
            y += 0.68
            hh = self._h(c.get("head", ""), hs, inner, True)
            self._text(slide, x + pad, y, inner, hh + 0.03, c.get("head", ""), size=hs,
                       bold=True, colour=self.t["card_ink"])
            y += hh
            if c.get("sub"):
                sh = self._h(c["sub"], bs, inner, True)
                self._text(slide, x + pad, y + 0.08, inner, sh + 0.03, c["sub"], size=bs,
                           bold=True, colour=self.label_colour)
                y += 0.08 + sh
            for b_ in c.get("bullets", [])[:4]:
                bh = self._h(b_, bs, inner)
                self._text(slide, x + pad, y + 0.12, inner, bh + 0.03, b_, size=bs,
                           colour=self.t["card_body"])
                y += 0.12 + bh

    def layout_recommendation_table(self, sp):
        slide = self._blank()
        top, bottom = self._chrome(slide, sp.get("kicker"), sp.get("title"),
                                   subtitle=sp.get("lead"), source=sp.get("source"))
        g = self.grid
        pad = g["card_pad"]
        x0 = g["margin_left"] + 0.80
        widths = [3.75, 4.55, 3.13]
        keys = ["recommendation", "evidence", "implication"]
        hx = x0
        for name, w in zip(("RECOMMENDATION", "EVIDENCE", "IMPLICATION"), widths):
            self._text(slide, hx, top, w, 0.22, name, size=10, bold=True,
                       colour=self.label_colour, caps=True)
            hx += w
        top += 0.34
        rows = sp.get("rows", [])[:5]
        gap = 0.14
        avail = bottom - top - gap * max(len(rows) - 1, 0)
        for size in (12.5, 12, 11.5, 11, self.floor.get("body", 10.5)):
            hs = []
            for r in rows:
                hs.append(2 * pad + max(self._h(r.get(k, ""), size, w - 0.30, k == "recommendation")
                                        for k, w in zip(keys, widths)))
            if sum(hs) <= avail:
                break
        else:
            self._overflow(f"{len(rows)} recommendation rows", sum(hs), avail)
        bonus = min(max(avail - sum(hs), 0) / max(len(rows), 1), 0.35)
        y = top
        for i, (r, h) in enumerate(zip(rows, hs)):
            hf = h + bonus
            self._card(slide, g["margin_left"], y, g["content_width"], hf)
            self._badge(slide, g["margin_left"] + 0.20, y + pad, 0.42, i + 1)
            cx = x0
            for k, w in zip(keys, widths):
                self._text(slide, cx, y + pad, w - 0.30, hf - 2 * pad, r.get(k, ""), size=size,
                           bold=(k == "recommendation"),
                           colour=self.t["card_ink"] if k == "recommendation" else self.t["card_body"])
                cx += w
            y += hf + gap

    def layout_section(self, sp):
        slide = self._blank()
        g, s = self.grid, self.sizes
        title = sp.get("title", "")
        th = self._h(title, s["section"], 10.5, True)
        y = 3.0 - th / 2
        if sp.get("label"):
            self._text(slide, 1.4, y - 0.40, 10.5, 0.3, sp["label"], size=s["kicker"], bold=True,
                       colour=self.label_colour, caps=True, align=PP_ALIGN.CENTER)
        self._text(slide, 1.4, y, 10.5, th + 0.05, title, size=s["section"], bold=True,
                   colour=self.t["ink"], align=PP_ALIGN.CENTER)
        if sp.get("subtitle"):
            sh = self._h(sp["subtitle"], 15, 10.5)
            self._text(slide, 1.4, y + th + 0.20, 10.5, sh + 0.03, sp["subtitle"], size=15,
                       colour=self.t["muted"], align=PP_ALIGN.CENTER)
        self._footer(slide)

    # -- drive -------------------------------------------------------------
    LAYOUTS = {
        "title": "layout_title",
        "agenda": "layout_agenda",
        "executive_summary": "layout_executive_summary",
        "how_to_read": "layout_how_to_read",
        "chart_with_notes": "layout_chart_with_notes",
        "comparison_pair": "layout_comparison_pair",
        "quotes_themes": "layout_quotes_themes",
        "stat_row": "layout_stat_row",
        "three_cards": "layout_three_cards",
        "recommendation_table": "layout_recommendation_table",
        "discussion_questions": "layout_discussion_questions",
        "section": "layout_section",
    }

    def build(self, out_path: Path) -> Path:
        for i, sp in enumerate(self.sl.get("slides", [])):
            layout = sp.get("layout")
            method = self.LAYOUTS.get(layout)
            if method is None:
                raise SystemExit(f"Slide {i + 1}: unknown layout '{layout}'. "
                                 f"Available: {', '.join(sorted(self.LAYOUTS))}")
            if layout in ("title", "agenda"):
                self.current_section = None
            elif layout == "section":
                self.current_section = sp.get("section") or sp.get("title")
            elif sp.get("section"):
                self.current_section = sp["section"]
            self.slide_no = i + 1
            getattr(self, method)(sp)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(str(out_path))
        return out_path


def load_storyline(project) -> dict[str, Any]:
    path = project.path("storyline/storyline.yaml")
    if not path.exists():
        raise SystemExit(f"No storyline at {path}. Run the storyteller agent first.")
    with path.open() as fh:
        return yaml.safe_load(fh)


def run(project, force: bool = False) -> dict[str, Any]:
    store = FindingStore.load(project.path("analysis/findings.json"))
    sl = load_storyline(project)
    meta = sl.get("meta", {})
    name = meta.get("filename") or f"CSCG_{project.slug}_{util.run_id()}.pptx"
    out = project.path("decks", name)
    builder = DeckBuilder(project, store, sl)
    builder.build(out)
    return {"deck": str(out), "slides": len(sl.get("slides", [])),
            "overflows": builder.overflows, "theme": builder.theme_name,
            "client_logo": str(builder.client_logo) if builder.client_logo else None}
