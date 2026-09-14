"""Stage 0: look at whatever files arrived and work out what each one is.

A CSCG cycle rarely starts with one clean CSV. It starts with a folder: a survey export,
a PDF report from the client, a spreadsheet with three tabs of someone else's pivot
tables, a Google Forms summary, a Word doc of the team's opinions.

This module inspects each file and routes it, because the routing determines whether a
number gets computed or declared:

  raw_respondent_data  one row per respondent  -> the analysis pipeline (computed)
  summary_table        already aggregated      -> declared.yaml (the base must be found)
  document             prose, PDF, notes       -> read for insights; numbers need a source
  chart_image          a picture of a chart    -> place it; declare its numbers separately

It does not decide anything irreversible. It writes an intake report for a human to
correct, because misclassifying an aggregated table as respondent data is how a deck ends
up reporting percentages of rows that are already percentages.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from . import util

DATA_EXT = {".csv", ".tsv", ".xlsx", ".xlsm", ".xls"}
DOC_EXT = {".pdf", ".docx", ".txt", ".md", ".rtf"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}

# Column names that mean "one row is one respondent".
RESPONDENT_HINTS = re.compile(
    r"(respondent|response_?id|submission|timestamp|email|participant|user_?id|"
    r"started|completed|duration|finished)", re.I)
# Column names that mean "this is already aggregated".
SUMMARY_HINTS = re.compile(
    r"^(count|n|total|percent|pct|%|share|mean|average|median|sum|freq|responses)$|"
    r"(_count|_pct|_percent|_total|_share|_mean)$", re.I)


def _read_tabular(path: Path, sheet=None) -> pd.DataFrame:
    if path.suffix.lower() in (".csv", ".txt"):
        return pd.read_csv(path, dtype=object, nrows=400)
    if path.suffix.lower() == ".tsv":
        return pd.read_csv(path, sep="\t", dtype=object, nrows=400)
    return pd.read_excel(path, sheet_name=sheet or 0, dtype=object, nrows=400)


def classify_table(df: pd.DataFrame) -> tuple[str, str]:
    """(kind, why). Conservative: when unsure, say so rather than guessing."""
    cols = [str(c) for c in df.columns]
    rows = len(df)
    if rows == 0 or not cols:
        return "empty", "no rows or no columns"

    has_resp = any(RESPONDENT_HINTS.search(c) for c in cols)
    n_summary = sum(1 for c in cols if SUMMARY_HINTS.search(c.strip()))
    wide = len(cols) >= 8

    if has_resp and rows >= 20:
        return ("raw_respondent_data",
                f"{rows}+ rows and a respondent-level column; one row looks like one person")
    if n_summary >= 1 and rows < 60 and len(cols) <= 8:
        return ("summary_table",
                f"{rows} rows, {n_summary} aggregate column(s) - already counted or averaged")
    if wide and rows >= 50:
        return ("raw_respondent_data",
                f"{rows} rows x {len(cols)} columns, no aggregate columns - probably one row per respondent")
    if rows < 60:
        return ("summary_table",
                f"only {rows} rows - too few to be a respondent file, treat as aggregated until confirmed")
    return ("unclear", f"{rows} rows x {len(cols)} columns, no clear signal - a human must decide")


def inspect_pdf(path: Path) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"pages": None, "note": "pypdf not installed; run pip install -r requirements.txt"}
    try:
        reader = PdfReader(str(path))
        pages = len(reader.pages)
        text = "\n".join((p.extract_text() or "") for p in reader.pages[:6])
        chars = len(text.strip())
        return {
            "pages": pages,
            "extractable_chars_first_6_pages": chars,
            "scanned_or_image_only": chars < 200,
            "preview": text.strip()[:600],
        }
    except Exception as e:
        return {"pages": None, "note": f"could not read: {e}"}


def inspect_file(path: Path) -> dict[str, Any]:
    ext = path.suffix.lower()
    info: dict[str, Any] = {
        "file": path.name,
        "ext": ext,
        "size_kb": round(path.stat().st_size / 1024, 1),
        "sha256_16": util.file_digest(path),
    }

    if ext in DATA_EXT:
        try:
            if ext in (".xlsx", ".xlsm", ".xls"):
                xl = pd.ExcelFile(path)
                info["sheets"] = []
                for name in xl.sheet_names:
                    df = _read_tabular(path, name)
                    kind, why = classify_table(df)
                    info["sheets"].append({
                        "sheet": name, "rows_sampled": len(df),
                        "columns": len(df.columns),
                        "column_names": [str(c) for c in df.columns][:12],
                        "kind": kind, "why": why,
                    })
                kinds = {s["kind"] for s in info["sheets"]}
                info["kind"] = ("raw_respondent_data" if "raw_respondent_data" in kinds
                                else ("summary_table" if "summary_table" in kinds else "unclear"))
                info["why"] = f"{len(info['sheets'])} sheet(s): " + ", ".join(
                    f"{s['sheet']}={s['kind']}" for s in info["sheets"])
            else:
                df = _read_tabular(path)
                info["kind"], info["why"] = classify_table(df)
                info["columns"] = len(df.columns)
                info["column_names"] = [str(c) for c in df.columns][:12]
                info["rows_sampled"] = len(df)
        except Exception as e:
            info["kind"], info["why"] = "unreadable", str(e)

    elif ext == ".pdf":
        info["kind"] = "document"
        info.update(inspect_pdf(path))
        info["why"] = ("scanned PDF: no extractable text, needs OCR or manual reading"
                       if info.get("scanned_or_image_only")
                       else f"{info.get('pages')}-page PDF with extractable text")

    elif ext in DOC_EXT:
        info["kind"] = "document"
        info["why"] = "prose or notes: read for insights, not for numbers"

    elif ext in IMG_EXT:
        info["kind"] = "chart_image"
        info["why"] = "image: can be placed on a slide, but its numbers must be declared separately"

    else:
        info["kind"] = "unknown"
        info["why"] = f"unrecognised extension {ext}"

    info["route"] = ROUTES.get(info["kind"], ROUTES["unknown"])
    return info


ROUTES = {
    "raw_respondent_data": "cscg ingest -> clean -> analyse   (numbers are COMPUTED)",
    "summary_table":       "analysis/declared.yaml            (numbers are DECLARED, need base + source)",
    "document":            "read for insights; any number needs a source in declared.yaml",
    "chart_image":         "place on a slide; declare its numbers separately",
    "empty":               "ignore",
    "unclear":             "a human must classify this before it is used",
    "unreadable":          "could not open - check the file",
    "unknown":             "a human must classify this before it is used",
}


def run(project, force: bool = False) -> dict[str, Any]:
    raw = project.path("data/raw")
    files = sorted(f for f in raw.glob("*") if f.is_file() and f.name != ".gitkeep")
    if not files:
        raise SystemExit(f"No files in {raw}. Put the client's material there first.")

    results = [inspect_file(f) for f in files]
    util.write_json(project.path("analysis/intake.json"),
                    {"run_id": util.run_id(project.slug), "files": results})
    _write_markdown(project, results)
    return {"files": len(results), "results": results}


def _write_markdown(project, results: list[dict[str, Any]]) -> None:
    lines = [
        f"# Intake - {project.cfg.get('title', project.slug)}",
        "",
        f"{len(results)} file(s) in `data/raw/`. Raw files are never modified.",
        "",
        "**Check the routing before running anything.** Treating an already-aggregated "
        "table as respondent data produces percentages of percentages, and nothing "
        "downstream will catch it.",
        "",
        "| File | Kind | Route | Why |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| `{r['file']}` | **{r['kind']}** | {r['route']} | {r['why'][:90]} |")

    sheets = [(r, s) for r in results for s in r.get("sheets", [])]
    if sheets:
        lines += ["", "## Spreadsheet tabs", "",
                  "| File | Sheet | Rows | Cols | Kind | Columns |", "|---|---|---|---|---|---|"]
        for r, s in sheets:
            lines.append(
                f"| `{r['file']}` | {s['sheet']} | {s['rows_sampled']} | {s['columns']} | "
                f"{s['kind']} | {', '.join(s['column_names'][:6])} |")

    pdfs = [r for r in results if r["ext"] == ".pdf"]
    if pdfs:
        lines += ["", "## PDFs", ""]
        for r in pdfs:
            lines.append(f"### `{r['file']}` ({r.get('pages')} pages)")
            if r.get("scanned_or_image_only"):
                lines.append("**No extractable text.** Scanned or image-only: read it "
                             "manually, or OCR it. Do not guess at its numbers.")
            elif r.get("preview"):
                lines.append("```\n" + r["preview"][:500] + "\n```")
            lines.append("")

    computed = [r for r in results if r["kind"] == "raw_respondent_data"]
    declared = [r for r in results if r["kind"] in ("summary_table", "document", "chart_image")]
    unclear = [r for r in results if r["kind"] in ("unclear", "unknown", "unreadable")]

    lines += ["", "## Next", ""]
    if computed:
        lines.append(f"**Computed path** ({len(computed)} file(s)): set `data.survey_file` "
                     f"in `project.yaml`, then `cscg ingest -> clean -> analyse`.")
        lines += [f"- `{r['file']}`" for r in computed]
    if declared:
        lines.append("")
        lines.append(f"**Declared path** ({len(declared)} file(s)): every number taken from "
                     f"these needs an entry in `analysis/declared.yaml` with a base and a "
                     f"source, then `cscg declare`. They will be marked `verified: false` "
                     f"and the linter will warn on every slide that uses them.")
        lines += [f"- `{r['file']}` - {r['why'][:80]}" for r in declared]
    if unclear:
        lines.append("")
        lines.append(f"**Needs a human** ({len(unclear)} file(s)):")
        lines += [f"- `{r['file']}` - {r['why'][:80]}" for r in unclear]
    lines.append("")
    project.path("analysis/intake.md").write_text("\n".join(lines))
