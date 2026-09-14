"""Chart rendering.

Charts are rendered FROM findings, never from free-floating numbers. Every chart ships
a sidecar JSON recording the finding it drew and the exact values plotted, plus a CSV.

House style, per config/chart_rules.yaml: one focal colour, everything else neutral; no
gridlines; bars start at zero; bases travel in the category label; value labels replace
the axis. Chart TYPE follows the claim: bars for comparisons, donuts for parts of one
whole, lines for ordered bands, columns for ordered scales, native tables where exact
values across several attributes matter.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image

from . import config, util
from .findings import Finding, FindingStore

IMAGE_TYPES = {"grouped_bar", "ranked_bar", "stacked_likert", "quadrant_scatter",
               "donut", "pie", "line", "column"}
ALL_TYPES = IMAGE_TYPES | {"table"}


def _setup(theme_name: str) -> dict[str, str]:
    t = config.theme(theme_name)
    fam = config.style()["typography"]["font"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    if fam not in available:
        fam = config.style()["typography"]["fallback"]
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [fam, "Helvetica", "DejaVu Sans"],
        "axes.edgecolor": "#" + t["rule"],
        "text.color": "#" + t["ink"],
        "axes.labelcolor": "#" + t["body"],
        "xtick.color": "#" + t["body"],
        "ytick.color": "#" + t["ink"],
        "savefig.transparent": True,
        "figure.facecolor": "none",
        "axes.facecolor": "none",
    })
    return t


def _clean_axes(ax, t: dict[str, str], keep=("left",)) -> None:
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(side in keep)
    for side in keep:
        ax.spines[side].set_color("#" + t["rule"])
    ax.grid(False)
    ax.set_xticks([])


def _fmt(metric: str, v: float, override: str | None = None) -> str:
    """Format a value the way its metric should be read.

    A correlation is not a percentage and must never be drawn as one; a mean on a 1-7
    scale is not a percentage either. `override` covers the case the metric cannot
    express: the mean of a variable that is itself a percentage (stored 0-100).
    """
    fmt = override or metric
    if fmt in ("percent", "proportion"):
        return f"{v:.0%}"
    if fmt == "percent_100":
        return f"{v:.0f}%"
    if fmt == "percent_100_1dp":
        return f"{v:.1f}%"
    if fmt == "correlation":
        return f"{v:.2f}"
    if fmt in ("integer", "count"):
        return f"{v:,.0f}"
    if fmt == "currency":
        return f"${v:,.0f}"
    return f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:,.0f}"


def _cat_label(g, mark: str) -> str:
    dagger = mark if g.directional_only else ""
    return f"{g.label} (n={g.n:,}){dagger}"


def _wrap(text: str, width: int) -> str:
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def _neutrals(t: dict[str, str]) -> list[str]:
    """Distinguishable non-focal shades, for charts that need more than one grey."""
    return ["#" + t[k] for k in ("neutral_series", "card_alt", "muted", "rule", "card")]


def _visible(f: Finding) -> list:
    return [g for g in f.groups if not g.suppressed]


# ---------------------------------------------------------------------------
# bar family
# ---------------------------------------------------------------------------

def grouped_bar(finding: Finding, theme_name: str, highlight: str | None = None,
                figsize=(7.3, 2.4), value_format: str | None = None) -> plt.Figure:
    """Two-or-three group comparison on one metric."""
    t = _setup(theme_name)
    cfg = config.charts()["format"]
    mark = config.rules()["bases"]["small_group_marker"]
    groups = _visible(finding)

    fig, ax = plt.subplots(figsize=figsize)
    labels = [_cat_label(g, mark) for g in groups]
    values = [g.value for g in groups]
    focal, grey = "#" + t["accent"], "#" + t["neutral_series"]
    if highlight is None:
        hi_idx = values.index(max(values))
    else:
        hi_idx = next((i for i, g in enumerate(groups) if g.label == highlight), 0)
    colours = [focal if i == hi_idx else grey for i in range(len(groups))]

    y = range(len(groups))
    ax.barh(list(y), values, color=colours, height=cfg["bars"]["height"], zorder=3)
    ax.set_yticks(list(y))
    ax.set_yticklabels([_wrap(l, cfg["labels"]["max_category_label_chars"]) for l in labels],
                       fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, max(max(values) * 1.28, 0.08))
    _clean_axes(ax, t)
    for i, v in enumerate(values):
        ax.text(v + max(values) * 0.02, i, _fmt(finding.metric, v, value_format),
                va="center", ha="left", fontsize=13, fontweight="bold",
                color=focal if i == hi_idx else "#" + t["body"], zorder=4)
    fig.tight_layout(pad=0.2)
    return fig


def ranked_bar(finding: Finding, theme_name: str, highlight: str | None = None,
               top_n: int = 8, figsize=(7.3, 3.6), value_format: str | None = None,
               sort: bool = True) -> plt.Figure:
    """Ranked list of items, sorted descending. Highlight only the one the title is about."""
    t = _setup(theme_name)
    cfg = config.charts()["format"]
    groups = _visible(finding)
    if sort:
        groups = sorted(groups, key=lambda g: -abs(g.value))
    groups = groups[:top_n]

    fig, ax = plt.subplots(figsize=figsize)
    mark = config.rules()["bases"]["small_group_marker"]
    varied = len({g.n for g in groups}) > 1
    labels = [(_cat_label(g, mark) if varied else g.label) for g in groups]
    values = [g.value for g in groups]
    focal, grey = "#" + t["accent"], "#" + t["neutral_series"]
    hi_idx = 0 if highlight is None else next(
        (i for i, g in enumerate(groups) if g.label == highlight), 0)
    colours = [focal if i == hi_idx else grey for i in range(len(groups))]

    y = range(len(groups))
    ax.barh(list(y), values, color=colours, height=0.62, zorder=3)
    ax.set_yticks(list(y))
    ax.set_yticklabels([_wrap(l, cfg["labels"]["max_category_label_chars"]) for l in labels],
                       fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, max(values) * 1.22)
    _clean_axes(ax, t)
    for i, v in enumerate(values):
        ax.text(v + max(values) * 0.015, i, _fmt(finding.metric, v, value_format),
                va="center", ha="left", fontsize=11, fontweight="bold",
                color=focal if i == hi_idx else "#" + t["body"], zorder=4)
    fig.tight_layout(pad=0.2)
    return fig


def column(findings: list[Finding], theme_name: str, labels: list[str] | None = None,
           highlight: str | None = None, figsize=(7.3, 3.4),
           value_format: str | None = None) -> plt.Figure:
    """Vertical bars in the stored (scale) order. One series, or two side by side.

    For ordered scales - 'not at all' to 'extremely', now vs in five years - where the
    left-to-right order carries meaning a sorted horizontal bar would destroy.
    """
    t = _setup(theme_name)
    mark = config.rules()["bases"]["small_group_marker"]
    base = _visible(findings[0])
    xlabels = [g.label for g in base]
    m = len(findings)
    width = 0.72 / m
    focal, neutrals = "#" + t["accent"], _neutrals(t)

    fig, ax = plt.subplots(figsize=figsize)
    vmax = 0.0
    for k, f in enumerate(findings):
        gmap = {g.label: g for g in _visible(f)}
        vals = [gmap[l].value if l in gmap else 0.0 for l in xlabels]
        vmax = max(vmax, max(vals) if vals else 0)
        xs = [i + (k - (m - 1) / 2) * width for i in range(len(xlabels))]
        if m == 1:
            colours = [focal if (highlight is None and v == max(vals)) or l == highlight
                       else neutrals[0] for l, v in zip(xlabels, vals)]
        else:
            name = labels[k] if labels and k < len(labels) else f.id
            is_focal = (highlight == name) or (highlight is None and k == m - 1)
            colours = [focal if is_focal else neutrals[0]] * len(vals)
        ax.bar(xs, vals, width=width * 0.92, color=colours, zorder=3,
               label=(labels[k] if labels and k < len(labels) else None))
        for x, v, c in zip(xs, vals, colours):
            ax.text(x, v, _fmt(f.metric, v, value_format), ha="center", va="bottom",
                    fontsize=10 if m > 1 else 11, fontweight="bold",
                    color=focal if c == focal else "#" + t["body"], zorder=4)
    varied = len({g.n for g in base}) > 1
    ticks = [(_cat_label(g, mark) if varied else g.label) for g in base]
    ax.set_xticks(range(len(xlabels)))
    ax.set_xticklabels([_wrap(x, 14) for x in ticks], fontsize=9.5)
    ax.set_ylim(0, vmax * 1.2 if vmax else 1)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#" + t["rule"])
    ax.set_yticks([])
    ax.tick_params(axis="x", length=0)
    if m > 1 and labels:
        ax.legend(frameon=False, fontsize=9, loc="upper right",
                  labelcolor="#" + t["body"])
    fig.tight_layout(pad=0.3)
    return fig


def stacked_likert(findings: list[Finding], theme_name: str,
                   labels: list[str] | None = None, figsize=(7.3, 2.6)) -> plt.Figure:
    """Stacked distribution across an ordered scale, one row per group."""
    t = _setup(theme_name)
    ramp = ["#" + c for c in config.style()["palette"]["sequential"]]
    min_share = config.charts()["format"]["likert"]["min_label_share"]

    fig, ax = plt.subplots(figsize=figsize)
    rows = []
    for i, f in enumerate(findings):
        name = (labels[i] if labels else f.question_text)
        rows.append((f"{name} (n={f.overall_n:,})", list(f.groups)))
    scale_len = max(len(r[1]) for r in rows)
    colours = [ramp[int(j * (len(ramp) - 1) / max(scale_len - 1, 1))] for j in range(scale_len)]
    for i, (name, groups) in enumerate(rows):
        left = 0.0
        for j, g in enumerate(groups):
            ax.barh(i, g.value, left=left, color=colours[j], height=0.5, zorder=3)
            if g.value >= min_share:
                ax.text(left + g.value / 2, i, f"{g.value:.0%}", ha="center", va="center",
                        fontsize=9, color="#FFFFFF" if j >= scale_len / 2 else "#121630",
                        zorder=4)
            left += g.value
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=9.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    _clean_axes(ax, t)
    handles = [plt.Rectangle((0, 0), 1, 1, color=colours[j]) for j in range(scale_len)]
    ax.legend(handles, [g.label for g in rows[0][1]], loc="upper center",
              bbox_to_anchor=(0.5, -0.06), ncol=min(scale_len, 5), frameon=False,
              fontsize=8.5, labelcolor="#" + t["body"])
    fig.tight_layout(pad=0.2)
    return fig


# ---------------------------------------------------------------------------
# share family
# ---------------------------------------------------------------------------

def _share_slices(finding: Finding, highlight: str | None):
    """Visible slices, plus one 'Other' slice for suppressed small groups so the
    drawn whole still sums to 100%."""
    vis = _visible(finding)
    hidden = sum(g.value for g in finding.groups if g.suppressed)
    slices = [(g.label, g.value) for g in sorted(vis, key=lambda g: -g.value)]
    if hidden > 0.005:
        slices.append(("Other (small groups)", hidden))
    hi = highlight or (slices[0][0] if slices else None)
    return slices, hi


def donut(finding: Finding, theme_name: str, highlight: str | None = None,
          figsize=(7.3, 3.4), value_format: str | None = None,
          centre_label: str | None = None, hole: float = 0.60) -> plt.Figure:
    """Parts of one whole. The share the title is about is focal and sits in the centre.

    McKinsey's UCA deck is the model: one saturated slice, the rest quiet, the headline
    number printed in the hole so the reader does not have to find it.
    """
    t = _setup(theme_name)
    slices, hi = _share_slices(finding, highlight)
    focal, neutrals = "#" + t["accent"], _neutrals(t)
    colours, k = [], 0
    for label, _ in slices:
        if label == hi:
            colours.append(focal)
        else:
            colours.append(neutrals[k % len(neutrals)])
            k += 1

    fig, ax = plt.subplots(figsize=figsize)
    wedges, _ = ax.pie([v for _, v in slices], colors=colours, startangle=90,
                       counterclock=False,
                       wedgeprops=dict(width=1 - hole if hole else 1,
                                       edgecolor="#" + t["background"], linewidth=2))
    for w, (label, v) in zip(wedges, slices):
        ang = math.radians((w.theta1 + w.theta2) / 2)
        cx, cy = math.cos(ang), math.sin(ang)
        is_hi = label == hi
        ax.annotate(f"{_wrap(label, 22)}\n{_fmt(finding.metric, v, value_format)}",
                    xy=(cx * 0.98, cy * 0.98), xytext=(cx * 1.30, cy * 1.20),
                    ha="left" if cx >= 0 else "right", va="center", fontsize=9.5,
                    fontweight="bold" if is_hi else "normal",
                    color=focal if is_hi else "#" + t["body"],
                    arrowprops=dict(arrowstyle="-", color="#" + t["rule"], lw=0.8))
    if hole:
        hv = next(v for l, v in slices if l == hi)
        ax.text(0, 0.10, _fmt(finding.metric, hv, value_format), ha="center",
                va="center", fontsize=24, fontweight="bold", color=focal)
        ax.text(0, -0.22, _wrap(centre_label or hi, 16), ha="center", va="center",
                fontsize=9, color="#" + t["ink"])
    ax.set_aspect("equal")
    ax.set_xlim(-2.0, 2.0)
    ax.set_ylim(-1.35, 1.35)
    ax.axis("off")
    fig.tight_layout(pad=0.2)
    return fig


def pie(finding: Finding, theme_name: str, highlight: str | None = None,
        figsize=(7.3, 3.4), value_format: str | None = None,
        centre_label: str | None = None) -> plt.Figure:
    return donut(finding, theme_name, highlight, figsize, value_format, None, hole=0.0)


# ---------------------------------------------------------------------------
# trend
# ---------------------------------------------------------------------------

def line(findings: list[Finding], theme_name: str, labels: list[str] | None = None,
         highlight: str | None = None, figsize=(7.3, 3.4),
         value_format: str | None = None) -> plt.Figure:
    """An outcome across ORDERED bands or time. One focal series, others quiet."""
    t = _setup(theme_name)
    mark = config.rules()["bases"]["small_group_marker"]
    base = _visible(findings[0])
    xlabels = [g.label for g in base]
    n = len(xlabels)
    focal, neutrals = "#" + t["accent"], _neutrals(t)

    fig, ax = plt.subplots(figsize=figsize)
    vmax = 0.0
    for k, f in enumerate(findings):
        gmap = {g.label: g for g in _visible(f)}
        ys = [gmap[l].value if l in gmap else float("nan") for l in xlabels]
        vmax = max(vmax, max(v for v in ys if v == v))
        name = labels[k] if labels and k < len(labels) else ""
        series_names = {(labels[j] if labels and j < len(labels) else "") for j in range(len(findings))} | {x.id for x in findings}
        # A highlight that names a series picks the focal series. One that names a POINT
        # (a band label, "Highest quarter") leaves the first series focal and emphasises
        # that point. Treating a point label as a series name drew the only line in grey.
        if highlight in series_names:
            is_focal = highlight in (name, f.id)
        else:
            is_focal = k == 0
        c = focal if is_focal else neutrals[(k - 1) % len(neutrals)]
        ax.plot(range(n), ys, color=c, lw=2.8 if is_focal else 1.8, marker="o",
                markersize=7 if is_focal else 5, zorder=4 if is_focal else 3)
        for i, v in enumerate(ys):
            if v != v or (not is_focal and i != n - 1):
                continue
            if is_focal and highlight == xlabels[i]:
                ax.plot([i], [v], marker="o", markersize=11, color=c, zorder=6)
            # Offset above the marker; placed on the point, the label sat on the dot.
            ax.annotate(_fmt(f.metric, v, value_format), (i, v), textcoords="offset points",
                        xytext=(0, 9), ha="center", va="bottom",
                        fontsize=11 if is_focal else 9.5, fontweight="bold", color=c, zorder=5)
        if name and len(findings) > 1:
            ax.text(n - 1 + 0.12, ys[-1], name, va="center", ha="left", fontsize=9.5,
                    color=c, fontweight="bold" if is_focal else "normal")
    varied = len({g.n for g in base}) > 1
    ticks = [(_cat_label(g, mark) if varied else g.label) for g in base]
    ax.set_xticks(range(n))
    ax.set_xticklabels([_wrap(x, 16) for x in ticks], fontsize=9.5)
    ax.set_ylim(0, vmax * 1.25 if vmax else 1)
    ax.set_xlim(-0.35, n - 1 + (1.3 if len(findings) > 1 else 0.35))
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#" + t["rule"])
    ax.set_yticks([])
    ax.tick_params(axis="x", length=0)
    fig.tight_layout(pad=0.3)
    return fig


# ---------------------------------------------------------------------------
# scatter
# ---------------------------------------------------------------------------

def quadrant_scatter(points: list[dict], theme_name: str, x_label: str, y_label: str,
                     figsize=(7.3, 4.0)) -> plt.Figure:
    """'Loud vs decisive'. Every point labelled, labels nudged apart so none collide."""
    t = _setup(theme_name)
    fig, ax = plt.subplots(figsize=figsize)
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    focal, grey = "#" + t["accent"], "#" + t["neutral_series"]
    ax.scatter(xs, ys, s=90, c=[focal if p.get("highlight") else grey for p in points],
               zorder=3, edgecolors="none")
    ax.set_xlim(0, max(xs) * 1.15)
    ax.set_ylim(0, max(ys) * 1.18)

    # Label repel: two points close together used to print their labels on top of
    # each other ("Restrooms" through "Video board"). Walk the points bottom-up and
    # push a label up one line whenever it would land on one already placed.
    xr, yr = max(xs) * 1.15, max(ys) * 1.18
    placed: list[tuple[float, float]] = []
    order = sorted(range(len(points)), key=lambda i: (ys[i], xs[i]))
    offsets = {}
    for i in order:
        dy_pts = 3
        for (px, py) in placed:
            if abs(xs[i] - px) < 0.22 * xr and abs(ys[i] + dy_pts / 300 * yr - py) < 0.055 * yr:
                dy_pts += 12
        offsets[i] = dy_pts
        placed.append((xs[i], ys[i] + dy_pts / 300 * yr))
    for i, p in enumerate(points):
        ax.annotate(p["label"], (xs[i], ys[i]), textcoords="offset points",
                    xytext=(8, offsets[i]), fontsize=9,
                    color="#" + (t["ink"] if p.get("highlight") else t["body"]),
                    fontweight="bold" if p.get("highlight") else "normal")
    ax.set_xlabel(x_label, fontsize=9.5)
    ax.set_ylabel(y_label, fontsize=9.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#" + t["rule"])
    ax.grid(False)
    fig.tight_layout(pad=0.3)
    return fig


# ---------------------------------------------------------------------------
# tables (rendered natively by deck.py; data comes from here so it stays traceable)
# ---------------------------------------------------------------------------

def table_data(spec: dict[str, Any], store: FindingStore) -> dict[str, Any]:
    """Header and rows for a native table, every cell drawn from a finding.

    Single finding: one row per group, columns chosen from value / n / count.
    Several findings: one row per group label, one column per finding.
    """
    mark = config.rules()["bases"]["small_group_marker"]
    fids = spec.get("finding_ids") or [spec["finding_id"]]
    fs = [store[x] for x in fids]
    fmts = spec.get("value_formats") or [spec.get("value_format")] * len(fs)
    row_label = spec.get("row_label", "")
    drew: dict[str, list] = {}

    if len(fs) == 1 and not spec.get("finding_ids"):
        f = fs[0]
        cols = spec.get("columns") or ["value", "n"]
        names = {"value": spec.get("value_label") or "Value", "n": "Base (n)",
                 "count": "Count"}
        header = [row_label] + [names.get(c, c) for c in cols]
        rows = []
        for g in _visible(f):
            cells = [g.label + (mark if g.directional_only else "")]
            for c in cols:
                if c == "value":
                    cells.append(_fmt(f.metric, g.value, fmts[0]))
                elif c == "n":
                    cells.append(f"{g.n:,}")
                elif c == "count":
                    cells.append(f"{g.count:,}" if g.count is not None else "-")
            rows.append(cells)
        drew[f.id] = [[g.label, g.value, g.n] for g in _visible(f)]
    else:
        order: list[str] = []
        for f in fs:
            for g in _visible(f):
                if g.label not in order:
                    order.append(g.label)
        header = [row_label] + (spec.get("column_labels") or [f.question_text for f in fs])
        rows = []
        for label in order:
            cells = [label]
            for f, fm in zip(fs, fmts):
                g = next((x for x in _visible(f) if x.label == label), None)
                cells.append(_fmt(f.metric, g.value, fm) if g else "-")
            rows.append(cells)
        for f in fs:
            drew[f.id] = [[g.label, g.value, g.n] for g in _visible(f)]

    hl = spec.get("highlight")
    hi = next((i for i, r in enumerate(rows) if r[0].rstrip(mark) == hl), None)
    return {"header": header, "rows": rows, "highlight_row": hi,
            "finding_ids": fids, "drew": drew}


def write_table_sidecar(spec: dict[str, Any], data: dict[str, Any], out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = spec.get("name") or f"{data['finding_ids'][0]}_table"
    with (out_dir / f"{stem}.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(data["header"])
        w.writerows(data["rows"])
    util.write_json(out_dir / f"{stem}.json", {
        "chart": stem, "type": "table", "finding_ids": data["finding_ids"],
        "values_drawn": data["drew"]})


# ---------------------------------------------------------------------------
# validation - is this chart type honest for this finding?
# ---------------------------------------------------------------------------

def validate(spec: dict[str, Any], store: FindingStore) -> list[tuple[str, str]]:
    """[(severity, message)]. Run by verify.py before anything is rendered."""
    typ = spec.get("type", "grouped_bar")
    if typ not in ALL_TYPES:
        return [("ERROR", f"Unknown chart type '{typ}'. Known: {', '.join(sorted(ALL_TYPES))}.")]
    fids = spec.get("finding_ids") or ([spec["finding_id"]] if spec.get("finding_id") else [])
    if not fids:
        return [("ERROR", "Chart has no finding_id - every chart is drawn from a finding.")]
    missing = [x for x in fids if store.get(x) is None]
    if missing:
        return [("ERROR", f"Chart cites finding(s) that do not exist: {', '.join(missing)}.")]
    fs = [store[x] for x in fids]
    rules = config.charts().get("validity", {})
    out: list[tuple[str, str]] = []

    if typ in ("donut", "pie"):
        f = fs[0]
        if f.metric != "percent":
            out.append(("ERROR", f"A {typ} needs a percentage finding; {f.id} is a {f.metric}."))
        elif f.kind in ("proportion_by_segment", "mean_by_segment", "correlation",
                        "ranked_items"):
            out.append(("ERROR",
                        f"{f.id} is a {f.kind}: each row has its own base, so its values "
                        f"are not slices of one whole. Use a bar chart."))
        else:
            total = sum(g.value for g in f.groups)
            if abs(total - 1.0) > rules.get("share_sum_tolerance", 0.03):
                out.append(("ERROR",
                            f"{f.id} sums to {total:.0%}, not 100% - a {typ} would misstate "
                            f"it. Multi-select answers never go in a {typ}."))
        n = len(_visible(f))
        if n > rules.get("max_share_slices", 5):
            out.append(("ERROR", f"{n} slices; a {typ} is unreadable past "
                                 f"{rules.get('max_share_slices', 5)}. Use a ranked bar."))
        if typ == "pie" and n > rules.get("max_pie_slices", 3):
            out.append(("WARN", f"{n}-slice pie. Use a donut with a centre number, or a bar."))

    if typ == "line":
        n = len(_visible(fs[0]))
        if n < rules.get("min_line_points", 3):
            out.append(("ERROR", f"A line needs {rules.get('min_line_points', 3)}+ ordered "
                                 f"points; {fs[0].id} has {n}. Use a grouped bar."))
        if fs[0].kind in ("composition", "ranked_items") and not spec.get("ordered"):
            out.append(("WARN",
                        f"A line implies an order between points, and {fs[0].id} is a "
                        f"{fs[0].kind}. Set `ordered: true` only if the categories really "
                        f"are ordered."))

    # A highlight that names no group silently lands the focal colour on the first bar -
    # the "mislabelled price group" a reviewer caught by reading, now caught by code.
    hl = spec.get("highlight")
    if hl is not None and typ != "quadrant_scatter":
        known = {g.label for f in fs for g in f.groups} | set(spec.get("labels") or []) | set(fids)
        if str(hl) not in known:
            out.append(("ERROR", f"highlight '{hl}' is not a group in {fids[0]} "
                                 f"(groups: {', '.join(sorted(g.label for g in fs[0].groups))[:160]}). "
                                 f"The focal colour would mark the wrong group."))
    if typ in ("line", "column") and spec.get("labels") and len(spec["labels"]) != len(fs):
        out.append(("ERROR", f"{len(spec['labels'])} series labels for {len(fs)} findings."))

    if typ in ("line", "column") and len(fs) > 1:
        base = [g.label for g in _visible(fs[0])]
        for f in fs[1:]:
            if [g.label for g in _visible(f)] != base:
                out.append(("WARN", f"{f.id} has different categories from {fs[0].id}; "
                                    f"missing points will be drawn as gaps."))
    return out


# ---------------------------------------------------------------------------
# dispatch + persistence
# ---------------------------------------------------------------------------

def _resolve_points(spec: dict[str, Any], store: FindingStore) -> list[dict]:
    """Quadrant coordinates, resolved from findings only - never typed by hand."""
    def lookup(ref, want: str) -> float:
        if not isinstance(ref, (list, tuple)) or not ref:
            raise SystemExit(
                f"quadrant_scatter: {want} must be [finding_id, group_label] or "
                f"[finding_id], got {ref!r}. Literal coordinates are not accepted.")
        f = store[ref[0]]
        if len(ref) == 1:
            if f.overall_value is None:
                raise SystemExit(f"quadrant_scatter: {f.id} has no overall value.")
            return float(f.overall_value)
        label = str(ref[1])
        field = ref[2] if len(ref) > 2 else "value"
        for g in f.groups:
            if g.label == label:
                v = getattr(g, field, None)
                if v is None:
                    raise SystemExit(f"quadrant_scatter: {f.id} group '{label}' has no {field}.")
                return float(v)
        raise SystemExit(f"quadrant_scatter: no group '{label}' in {f.id}. "
                         f"Groups: {[g.label for g in f.groups]}")

    out = []
    for p in spec.get("points", []):
        if "x" in p or "y" in p:
            raise SystemExit(
                f"quadrant_scatter point {p.get('label')!r} carries a literal coordinate. "
                "Use x_from / y_from so the value comes from a finding.")
        out.append({"label": p["label"], "highlight": bool(p.get("highlight")),
                    "x": lookup(p.get("x_from"), "x_from"),
                    "y": lookup(p.get("y_from"), "y_from"),
                    "x_from": p.get("x_from"), "y_from": p.get("y_from")})
    return out


def render(spec: dict[str, Any], store: FindingStore, out_dir: Path,
           theme_name: str = "light") -> dict[str, Any]:
    """Render one image chart spec. Requires a finding_id - the traceability rule."""
    fid = spec.get("finding_id") or (spec.get("finding_ids") or [None])[0]
    if not fid:
        raise SystemExit(f"Chart spec has no finding_id: {spec}.")
    ctype = spec.get("type", "grouped_bar")
    if ctype not in IMAGE_TYPES:
        raise SystemExit(f"Chart type '{ctype}' is not an image chart. Known: "
                         f"{', '.join(sorted(ALL_TYPES))}.")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    size = spec.get("figsize") or [7.3, 0]
    width = float(size[0])
    ceiling = float(size[1]) if len(size) > 1 and size[1] else 3.9
    fids = spec.get("finding_ids") or [fid]

    if ctype == "stacked_likert":
        findings = [store[f] for f in fids]
        fig = stacked_likert(findings, theme_name, spec.get("labels"),
                             (width, min(ceiling, 0.55 * len(findings) + 1.1)))
        drew = {f.id: [[g.label, g.value, g.n] for g in f.groups] for f in findings}
        primary = findings[0]
    elif ctype == "quadrant_scatter":
        points = _resolve_points(spec, store)
        fig = quadrant_scatter(points, theme_name, spec.get("x_label", ""),
                               spec.get("y_label", ""), (width, min(ceiling, 4.0)))
        drew = {"points": points}
        primary = store[fid]
    elif ctype in ("donut", "pie"):
        primary = store[fid]
        fig = (donut if ctype == "donut" else pie)(
            primary, theme_name, spec.get("highlight"),
            (width, min(ceiling, max(2.6, width * 0.52))), spec.get("value_format"),
            spec.get("centre_label"))
        drew = {primary.id: [[g.label, g.value, g.n] for g in primary.groups]}
    elif ctype in ("line", "column"):
        findings = [store[f] for f in fids]
        fig = (line if ctype == "line" else column)(
            findings, theme_name, spec.get("labels"), spec.get("highlight"),
            (width, min(ceiling, 3.6)), spec.get("value_format"))
        drew = {f.id: [[g.label, g.value, g.n] for g in f.groups] for f in findings}
        primary = findings[0]
    else:
        primary = store[fid]
        fn = grouped_bar if ctype == "grouped_bar" else ranked_bar
        kwargs = {"highlight": spec.get("highlight"), "value_format": spec.get("value_format")}
        n_bars = len(_visible(primary))
        if ctype == "ranked_bar":
            if "sort" in spec:
                kwargs["sort"] = bool(spec["sort"])
            if "top_n" in spec:
                kwargs["top_n"] = spec["top_n"]
            n_bars = min(n_bars, kwargs.get("top_n", 8))
        # Height follows the number of bars so a 2-group chart is not two slabs.
        kwargs["figsize"] = (width, min(max(0.50 * n_bars + 0.55, 1.15), max(ceiling, 1.15)))
        fig = fn(primary, theme_name, **kwargs)
        drew = {primary.id: [[g.label, g.value, g.n] for g in primary.groups]}

    stem = spec.get("name") or f"{fid}_{ctype}"
    png = out_dir / f"{stem}.png"
    fig.savefig(png, dpi=config.charts()["format"]["figure"]["dpi"],
                bbox_inches="tight", transparent=True, pad_inches=0.02)
    if config.charts()["output"].get("also_emit_svg"):
        fig.savefig(out_dir / f"{stem}.svg", bbox_inches="tight",
                    transparent=True, pad_inches=0.02)
    plt.close(fig)

    if config.charts()["output"].get("also_emit_data_csv"):
        with (out_dir / f"{stem}.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["finding_id", "series", "label", "value", "n"])
            for k, rows in drew.items():
                if isinstance(rows, list) and rows and isinstance(rows[0], list):
                    for r in rows:
                        w.writerow([k, stem, *r])

    sidecar = {"chart": stem, "type": ctype, "finding_id": fid,
               "question_text": primary.question_text,
               "base_definition": primary.base_definition,
               "values_drawn": drew, "theme": theme_name}
    util.write_json(out_dir / f"{stem}.json", sidecar)
    with Image.open(png) as im:
        px_w, px_h = im.size
    return {"png": str(png), "sidecar": sidecar,
            "aspect": float(px_h) / float(px_w), "pixels": [px_w, px_h]}
