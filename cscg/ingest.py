"""Stage 1: inspect a new dataset and build a data dictionary.

Reads raw data (never writes to it), infers what each column is, and produces a
data dictionary plus a profile the analyst reviews before any cleaning happens.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import util

LIKERT_HINTS = [
    "strongly agree", "somewhat agree", "neither", "strongly disagree",
    "very satisfied", "very dissatisfied", "not at all", "extremely",
]
OPEN_TEXT_MIN_MEAN_CHARS = 25
OPEN_TEXT_MIN_UNIQUE_RATIO = 0.6


def read_any(path: Path, sheet: str | None = None) -> pd.DataFrame:
    """Load csv/tsv/xlsx without guessing dtypes destructively."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".csv", ".txt"):
        return pd.read_csv(path, dtype=object, keep_default_na=True)
    if suffix in (".tsv",):
        return pd.read_csv(path, sep="\t", dtype=object)
    if suffix in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path, sheet_name=sheet or 0, dtype=object)
    raise SystemExit(f"Unsupported data file type: {path.suffix}")


def _numeric_view(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def infer_type(name: str, s: pd.Series) -> tuple[str, dict[str, Any]]:
    """Classify a column. Returns (type, detail).

    Types: id | numeric | ordinal | categorical | binary | open_text | datetime | empty
    Deliberately conservative: anything ambiguous is flagged for the analyst rather
    than silently coerced.
    """
    non_null = s.dropna()
    detail: dict[str, Any] = {
        "n_non_null": int(non_null.size),
        "n_missing": int(s.size - non_null.size),
        "missing_pct": round(float(1 - non_null.size / max(s.size, 1)), 4),
        "n_unique": int(non_null.nunique()),
    }
    if non_null.empty:
        return "empty", detail

    lname = name.lower()
    nums = _numeric_view(non_null)
    numeric_share = float(nums.notna().mean())
    uniq = non_null.astype(str).str.strip()
    n_unique = uniq.nunique()

    # Identifier: unique-ish and named like one
    if re.search(r"(^|_)(id|uuid|respondent|response)(_|$)", lname) and n_unique > 0.9 * non_null.size:
        detail["example"] = str(uniq.iloc[0])
        return "id", detail

    if numeric_share > 0.95:
        vals = nums.dropna()
        detail.update(
            min=float(vals.min()), max=float(vals.max()),
            mean=round(float(vals.mean()), 4), median=float(vals.median()),
        )
        uniq_vals = sorted(vals.unique().tolist())
        detail["distinct_values"] = uniq_vals[:15]
        if set(uniq_vals) <= {0.0, 1.0}:
            return "binary", detail
        # Small integer range with a full ladder -> a rating scale
        if len(uniq_vals) <= 11 and all(float(v).is_integer() for v in uniq_vals):
            span = max(uniq_vals) - min(uniq_vals)
            if 2 <= span <= 10:
                detail["scale_points"] = len(uniq_vals)
                detail["scale_range"] = [min(uniq_vals), max(uniq_vals)]
                return "ordinal", detail
        return "numeric", detail

    if re.search(r"(date|time|timestamp|submitted|fielded)", lname):
        parsed = pd.to_datetime(non_null, errors="coerce")
        if parsed.notna().mean() > 0.8:
            detail["min"] = str(parsed.min())
            detail["max"] = str(parsed.max())
            return "datetime", detail

    mean_chars = float(uniq.str.len().mean())
    unique_ratio = n_unique / max(non_null.size, 1)
    if mean_chars >= OPEN_TEXT_MIN_MEAN_CHARS and unique_ratio >= OPEN_TEXT_MIN_UNIQUE_RATIO:
        detail["mean_chars"] = round(mean_chars, 1)
        detail["example"] = uniq.iloc[0][:160]
        return "open_text", detail

    counts = uniq.value_counts()
    detail["levels"] = [
        {"value": str(k), "n": int(v), "pct": round(float(v / non_null.size), 4)}
        for k, v in counts.head(25).items()
    ]
    if n_unique == 2:
        return "binary", detail
    lowered = " ".join(str(x).lower() for x in counts.index[:12])
    if any(h in lowered for h in LIKERT_HINTS):
        return "ordinal", detail
    if n_unique <= 25:
        return "categorical", detail

    detail["note"] = "High-cardinality text that is not clearly open-ended. Review."
    detail["example"] = uniq.iloc[0][:160]
    return "open_text", detail


def build_dictionary(df: pd.DataFrame) -> list[dict[str, Any]]:
    entries = []
    for col in df.columns:
        ctype, detail = infer_type(str(col), df[col])
        entries.append({
            "column": str(col),
            "inferred_type": ctype,
            # Question text defaults to the column name; the analyst edits this file
            # so that slides can quote real question wording.
            "question_text": str(col).replace("_", " ").strip().capitalize(),
            "analysis_role": _default_role(ctype, str(col)),
            **detail,
        })
    return entries


def _default_role(ctype: str, name: str) -> str:
    """Suggested role. The analyst confirms or overrides in the data dictionary."""
    if ctype == "id":
        return "identifier"
    if ctype == "open_text":
        return "qualitative"
    if ctype in ("categorical", "binary"):
        return "segment_candidate"
    if ctype in ("ordinal", "numeric"):
        return "measure"
    return "exclude"


def profile(df: pd.DataFrame, source: Path, sheet: str | None = None) -> dict[str, Any]:
    dictionary = build_dictionary(df)
    by_type: dict[str, list[str]] = {}
    for e in dictionary:
        by_type.setdefault(e["inferred_type"], []).append(e["column"])

    high_missing = [
        {"column": e["column"], "missing_pct": e["missing_pct"]}
        for e in dictionary if e["missing_pct"] > 0.2
    ]
    constant = [e["column"] for e in dictionary if e["n_unique"] <= 1]

    return {
        "source_file": str(source),
        "source_sheet": sheet,
        "source_sha256_16": util.file_digest(source),
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "columns_by_type": by_type,
        "warnings": {
            "high_missing_over_20pct": high_missing,
            "constant_columns": constant,
            "duplicate_column_names": [
                c for c in df.columns if list(df.columns).count(c) > 1
            ],
        },
        "dictionary": dictionary,
    }


def run(project, force: bool = False) -> dict[str, Any]:
    """Stage entrypoint: profile the raw survey file and write the data dictionary."""
    data_cfg = project.cfg.get("data", {}) or {}
    fname = data_cfg.get("survey_file")
    if not fname:
        raise SystemExit(
            "project.yaml: data.survey_file is empty. Put the raw file in data/raw/ "
            "and name it there."
        )
    src = project.path("data/raw", fname)
    if not src.exists():
        raise SystemExit(f"Raw data file not found: {src}")

    sheet = data_cfg.get("survey_sheet") or None
    df = read_any(src, sheet)
    prof = profile(df, src, sheet)

    out = project.path("analysis/data_dictionary.json")
    util.write_json(out, prof)
    _write_markdown(project, prof)
    return prof


def _write_markdown(project, prof: dict[str, Any]) -> None:
    """Human-readable dictionary. This is what the analyst actually reads."""
    lines = [
        f"# Data dictionary - {project.cfg.get('title', project.slug)}",
        "",
        f"Source: `{Path(prof['source_file']).name}`"
        + (f" (sheet `{prof['source_sheet']}`)" if prof["source_sheet"] else ""),
        f"SHA-256 (16): `{prof['source_sha256_16']}`",
        f"Shape: **{prof['rows']} rows x {prof['columns']} columns**",
        "",
        "> Edit `question_text` and `analysis_role` below in "
        "`analysis/data_dictionary.json`. Slides quote `question_text` verbatim in "
        "source lines, so it should match the instrument.",
        "",
        "## Columns",
        "",
        "| Column | Type | Role | Missing | Unique | Detail |",
        "|---|---|---|---|---|---|",
    ]
    for e in prof["dictionary"]:
        detail = ""
        if e["inferred_type"] in ("ordinal", "numeric"):
            if "min" in e:
                detail = f"range {e['min']:g}-{e['max']:g}, mean {e.get('mean', float('nan')):g}"
        elif e["inferred_type"] in ("categorical", "binary"):
            lv = e.get("levels", [])[:4]
            detail = ", ".join(f"{l['value']} ({l['n']})" for l in lv)
        elif e["inferred_type"] == "open_text":
            detail = f"~{e.get('mean_chars', '?')} chars avg"
        lines.append(
            f"| `{e['column']}` | {e['inferred_type']} | {e['analysis_role']} | "
            f"{e['missing_pct']:.0%} | {e['n_unique']} | {detail[:70]} |"
        )

    w = prof["warnings"]
    lines += ["", "## Warnings", ""]
    if w["high_missing_over_20pct"]:
        lines.append("**Columns over 20% missing** - decide whether these are skip-logic "
                     "(fine, but the base changes) or genuine non-response:")
        lines += [f"- `{x['column']}`: {x['missing_pct']:.0%} missing"
                  for x in w["high_missing_over_20pct"]]
    else:
        lines.append("- No column exceeds 20% missing.")
    if w["constant_columns"]:
        lines.append(f"- Constant columns (no variation, drop them): "
                     f"{', '.join('`%s`' % c for c in w['constant_columns'])}")
    if w["duplicate_column_names"]:
        lines.append(f"- **Duplicate column names**: {set(w['duplicate_column_names'])}")

    lines += ["", "## Next", "",
              "1. Fix `question_text` for anything that will be quoted on a slide.",
              "2. Set `analysis_role`: `identifier` / `segment_candidate` / `measure` / "
              "`qualitative` / `exclude`.",
              "3. Declare your segments in `project.yaml` **before** analysis.",
              ""]
    project.path("analysis/data_dictionary.md").write_text("\n".join(lines))
