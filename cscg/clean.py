"""Stage 2: validate and clean.

Raw data is never modified. Cleaning writes data/processed/clean.csv plus a cleaning
report that states every rule applied, how many rows it caught, and - critically -
whether excluding those rows moved any headline number. That last check comes straight
from the Coastal State workbook's 'Cleaning Checks' tab: it is how you find out you
cleaned your way to the answer you wanted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import config, ingest, util


def _dictionary(project) -> list[dict[str, Any]]:
    path = project.path("analysis/data_dictionary.json")
    if not path.exists():
        raise SystemExit("Run ingest first: no analysis/data_dictionary.json")
    return util.read_json(path)["dictionary"]


def _cols_of_role(dic, role: str) -> list[str]:
    return [e["column"] for e in dic if e["analysis_role"] == role]


def _cols_of_type(dic, *types: str) -> list[str]:
    return [e["column"] for e in dic if e["inferred_type"] in types]


def flag_duplicates(df: pd.DataFrame, id_col: str | None) -> pd.Series:
    if id_col and id_col in df.columns:
        return df[id_col].duplicated(keep="first")
    return df.duplicated(keep="first")


def flag_speeders(df: pd.DataFrame, duration_col: str | None, fraction: float) -> tuple[pd.Series, dict]:
    if not duration_col or duration_col not in df.columns:
        return pd.Series(False, index=df.index), {"applied": False, "reason": "no duration column"}
    dur = pd.to_numeric(df[duration_col], errors="coerce")
    median = float(dur.median()) if dur.notna().any() else np.nan
    if not np.isfinite(median):
        return pd.Series(False, index=df.index), {"applied": False, "reason": "duration not numeric"}
    cutoff = median * fraction
    return dur < cutoff, {"applied": True, "median_seconds": round(median, 1),
                          "cutoff_seconds": round(cutoff, 1)}


def detect_batteries(scale_cols: list[str], min_items: int) -> dict[str, list[str]]:
    """Group rating items into batteries by shared prefix.

    Straightlining has to be judged WITHIN a battery. Checking 'same answer across
    every ordinal column' spans unrelated scales (a 1-7 satisfaction grid, a 0-10 NPS,
    a count of games) and therefore catches almost nobody.
    """
    groups: dict[str, list[str]] = {}
    for c in scale_cols:
        prefix = c.split("_")[0] if "_" in c else c
        groups.setdefault(prefix, []).append(c)
    return {k: v for k, v in groups.items() if len(v) >= min_items}


def flag_straightlining(df: pd.DataFrame, scale_cols: list[str],
                        min_items: int) -> tuple[pd.Series, dict]:
    usable = [c for c in scale_cols if c in df.columns]
    batteries = detect_batteries(usable, min_items)
    if not batteries:
        return pd.Series(False, index=df.index), {
            "applied": False,
            "reason": f"no rating battery with >= {min_items} items",
        }
    flag = pd.Series(False, index=df.index)
    detail = {}
    for name, cols in batteries.items():
        block = df[cols].apply(pd.to_numeric, errors="coerce")
        answered = block.notna().sum(axis=1)
        nunique = block.nunique(axis=1, dropna=True)
        hit = (nunique == 1) & (answered >= min_items)
        detail[name] = {"items": len(cols), "rows_flagged": int(hit.sum())}
        flag |= hit
    return flag, {"applied": True, "batteries": detail}


def flag_impossible(df: pd.DataFrame, dic, bounds: dict[str, list]) -> tuple[pd.Series, dict]:
    """Out-of-range values.

    Only bounds DECLARED in project.yaml (`value_bounds`) are used. The scale ranges in
    the data dictionary are inferred from the data itself, so testing the data against
    them is circular and can never fail. If you want impossible values caught, declare
    the real instrument bounds.
    """
    flag = pd.Series(False, index=df.index)
    checked = {}
    for e in dic:
        col = e["column"]
        if col not in df.columns or col not in bounds:
            continue
        lo, hi = bounds[col][0], bounds[col][1]
        if lo is None:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        bad = vals.notna() & ((vals < lo) | (vals > hi))
        if bad.any():
            checked[col] = {"bounds": [lo, hi], "n_bad": int(bad.sum())}
        flag |= bad
    return flag, {
        "applied": bool(bounds),
        "columns": checked,
        "reason": ("no value_bounds declared in project.yaml - inferred ranges are "
                   "circular and are not used") if not bounds else "",
    }


def flag_incomplete(df: pd.DataFrame, measure_cols: list[str], min_fraction: float) -> tuple[pd.Series, dict]:
    usable = [c for c in measure_cols if c in df.columns]
    if not usable:
        return pd.Series(False, index=df.index), {"applied": False, "reason": "no measure columns"}
    completion = df[usable].notna().mean(axis=1)
    return completion < min_fraction, {"applied": True, "items": len(usable),
                                       "min_fraction": min_fraction}


def derive_columns(df: pd.DataFrame, specs: list[dict[str, Any]]) -> tuple[pd.DataFrame, list[dict]]:
    """Add declared band columns to the cleaned frame.

    Bands over a continuous or ordinal variable are declared in project.yaml before
    analysis, for the same reason segments are: cut points chosen after seeing the
    outcome are how a finding gets manufactured. Quantile bands are computed on the
    rows that survived cleaning, so each band's base is the analysed sample.

    Every spec records the edges actually used and the resulting band sizes in the
    cleaning report, because a band label like "Very often" is only honest if the
    range behind it is written down somewhere a reader can find.
    """
    out = df.copy()
    records: list[dict] = []
    for spec in specs or []:
        name, src = spec.get("name"), spec.get("from")
        if not name or src not in out.columns:
            records.append({"name": name, "applied": False,
                            "reason": f"source column '{src}' not in the cleaned data"})
            continue
        labels = list(spec.get("labels") or [])
        vals = pd.to_numeric(out[src], errors="coerce")

        eligible = vals.notna()
        where = spec.get("where") or {}
        if where.get("column") in out.columns:
            eligible &= out[where["column"]].astype(str) == str(where.get("equals"))

        method = spec.get("method", "quantile_bands")
        if method == "quantile_bands":
            n_bands = int(spec.get("bands", 4))
            if len(labels) != n_bands:
                raise SystemExit(
                    f"derived_columns: '{name}' declares {n_bands} bands but "
                    f"{len(labels)} labels.")
            edges = (vals[eligible]
                     .quantile([i / n_bands for i in range(n_bands + 1)])
                     .tolist())
            edges[0], edges[-1] = -np.inf, np.inf
            if len(set(edges)) != len(edges):
                records.append({"name": name, "applied": False,
                                "reason": "tied quantile edges - the source column is "
                                          "too coarse to split into this many bands"})
                continue
            banded = pd.cut(vals.where(eligible), bins=edges, labels=labels,
                            right=True, include_lowest=True)
        elif method == "value_bands":
            edges = [float(e) for e in (spec.get("edges") or [])]
            if len(edges) != len(labels) + 1:
                raise SystemExit(
                    f"derived_columns: '{name}' needs {len(labels) + 1} edges for "
                    f"{len(labels)} labels, got {len(edges)}.")
            banded = pd.cut(vals.where(eligible), bins=edges, labels=labels,
                            right=False)
        else:
            raise SystemExit(f"derived_columns: '{name}' has unknown method '{method}'")

        out[name] = banded.astype(object).where(banded.notna(), np.nan)
        counts = out[name].value_counts(dropna=True)
        records.append({
            "name": name,
            "applied": True,
            "from": src,
            "method": method,
            "where": where or None,
            "edges": [round(e, 4) if np.isfinite(e) else ("-inf" if e < 0 else "inf")
                      for e in edges],
            "bands": [{"label": lab, "n": int(counts.get(lab, 0))} for lab in labels],
            "n_banded": int(out[name].notna().sum()),
        })
    return out, records


def exclusion_impact(df: pd.DataFrame, keep: pd.Series, check_cols: list[str]) -> list[dict]:
    """Did dropping these rows move anything? The check the workbook ran by hand."""
    rows = []
    for col in check_cols:
        if col not in df.columns:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        if vals.notna().sum() < 10:
            continue
        all_mean = float(vals.mean())
        kept_mean = float(vals[keep].mean()) if keep.any() else float("nan")
        drop_mean = float(vals[~keep].mean()) if (~keep).any() else float("nan")
        rows.append({
            "column": col,
            "all_rows": round(all_mean, 3),
            "kept": round(kept_mean, 3),
            "excluded": round(drop_mean, 3),
            "shift_from_cleaning": round(kept_mean - all_mean, 3),
        })
    # Surface the biggest movers first - those are the ones worth arguing about.
    rows.sort(key=lambda r: abs(r["shift_from_cleaning"]), reverse=True)
    return rows


def _register_derived(project, dic: list[dict[str, Any]], clean: pd.DataFrame,
                      specs: list[dict[str, Any]], records: list[dict]) -> None:
    """Give each derived band an entry in the data dictionary.

    Without this a band column reaches `analyse` with no question text and no declared
    role, and the slide that cites it has nothing to put on its source line.
    """
    path = project.path("analysis/data_dictionary.json")
    prof = util.read_json(path)
    by_name = {r.get("name"): r for r in records}
    existing = {e["column"] for e in prof["dictionary"]}
    added = 0
    for spec in specs or []:
        name = spec.get("name")
        rec = by_name.get(name, {})
        if not name or name in existing or not rec.get("applied"):
            continue
        col = clean[name]
        prof["dictionary"].append({
            "column": name,
            "inferred_type": "categorical",
            "question_text": spec.get("question_text") or name.replace("_", " ").capitalize(),
            "analysis_role": "segment_candidate",
            "derived_from": spec.get("from"),
            "derivation": {k: rec[k] for k in ("method", "edges", "where") if k in rec},
            "n_non_null": int(col.notna().sum()),
            "n_missing": int(col.isna().sum()),
            "missing_pct": round(float(col.isna().mean()), 4),
            "n_unique": int(col.nunique()),
            "levels": [{"value": b["label"], "n": b["n"]} for b in rec.get("bands", [])],
        })
        added += 1
    if added:
        prof["columns"] = int(prof["columns"]) + added
        prof.setdefault("columns_by_type", {}).setdefault("categorical", [])
        util.write_json(path, prof)


def run(project, force: bool = False) -> dict[str, Any]:
    rules = config.rules()
    screens = rules["quality_screens"]
    dic = _dictionary(project)
    data_cfg = project.cfg.get("data", {}) or {}

    src = project.path("data/raw", data_cfg["survey_file"])
    df = ingest.read_any(src, data_cfg.get("survey_sheet") or None)
    n_start = len(df)

    id_col = data_cfg.get("id_column") or next(iter(_cols_of_role(dic, "identifier")), None)
    duration_col = data_cfg.get("duration_column") or next(
        (c for c in df.columns if "duration" in str(c).lower() or "time_sec" in str(c).lower()), None
    )
    scale_cols = [e["column"] for e in dic if e["inferred_type"] == "ordinal"]
    measure_cols = _cols_of_role(dic, "measure")

    flags = pd.DataFrame(index=df.index)
    detail: dict[str, Any] = {}

    if screens["duplicates"]["enabled"]:
        flags["duplicate"] = flag_duplicates(df, id_col)
        detail["duplicates"] = {"applied": True, "id_column": id_col}
    if screens["speeders"]["enabled"]:
        flags["speeder"], detail["speeders"] = flag_speeders(
            df, duration_col, screens["speeders"]["fraction"])
    if screens["straightlining"]["enabled"]:
        flags["straightlining"], detail["straightlining"] = flag_straightlining(
            df, scale_cols, screens["straightlining"]["min_scale_items"])
    if screens["impossible_values"]["enabled"]:
        flags["impossible"], detail["impossible_values"] = flag_impossible(
            df, dic, (project.cfg.get("value_bounds") or {}))
    if screens["incompletes"]["enabled"]:
        flags["incomplete"], detail["incompletes"] = flag_incomplete(
            df, measure_cols, screens["incompletes"]["min_completion_fraction"])

    flags = flags.fillna(False).astype(bool)
    any_flag = flags.any(axis=1)
    keep = ~any_flag

    clean = df[keep].copy()
    derived_specs = project.cfg.get("derived_columns") or []
    clean, derived = derive_columns(clean, derived_specs)
    _register_derived(project, dic, clean, derived_specs, derived)
    out_csv = project.path("data/processed/clean.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(out_csv, index=False)

    flags_out = flags.copy()
    flags_out.insert(0, "_row", df.index)
    if id_col and id_col in df.columns:
        flags_out.insert(1, id_col, df[id_col])
    flags_out["keep"] = keep
    flags_out.to_csv(project.path("data/processed/quality_flags.csv"), index=False)

    impact_cols = measure_cols[:12] or scale_cols[:12]
    report = {
        "run_id": util.run_id(),
        "source_file": str(src),
        "source_sha256_16": util.file_digest(src),
        "rows_in": n_start,
        "rows_kept": int(keep.sum()),
        "rows_excluded": int(any_flag.sum()),
        "excluded_pct": round(float(any_flag.mean()), 4),
        "screens": {
            name: {"rows_flagged": int(flags[name].sum()),
                   "pct": round(float(flags[name].mean()), 4),
                   **detail.get(_screen_key(name), {})}
            for name in flags.columns
        },
        "exclusion_impact": exclusion_impact(df, keep, impact_cols),
        "derived_columns": derived,
        "note": (
            "Rows are excluded only by the rules above, applied before any result was "
            "looked at. exclusion_impact shows whether cleaning moved a headline number."
        ),
    }
    util.write_json(project.path("analysis/cleaning_report.json"), report)
    _write_markdown(project, report)
    return report


def _screen_key(flag_name: str) -> str:
    return {
        "duplicate": "duplicates", "speeder": "speeders",
        "straightlining": "straightlining", "impossible": "impossible_values",
        "incomplete": "incompletes",
    }.get(flag_name, flag_name)


def _write_markdown(project, r: dict[str, Any]) -> None:
    lines = [
        f"# Cleaning report - {project.cfg.get('title', project.slug)}",
        "",
        f"**{r['rows_in']} rows in -> {r['rows_kept']} analysed** "
        f"({r['rows_excluded']} excluded, {r['excluded_pct']:.1%}).",
        "",
        "Raw file is unmodified. Cleaned data: `data/processed/clean.csv`. "
        "Per-row flags: `data/processed/quality_flags.csv`.",
        "",
        "## Screens applied",
        "",
        "| Screen | Rows flagged | % | Detail |",
        "|---|---|---|---|",
    ]
    for name, s in r["screens"].items():
        det = {k: v for k, v in s.items() if k not in ("rows_flagged", "pct")}
        if det.get("applied") is False:
            det_s = f"not applied - {det.get('reason', '')}"
        else:
            det_s = ", ".join(f"{k}={v}" for k, v in det.items() if k != "applied")
        lines.append(f"| {name} | {s['rows_flagged']} | {s['pct']:.1%} | {det_s[:80]} |")

    lines += [
        "", "## Did cleaning change the answer?", "",
        "If a number moves a lot between 'all rows' and 'kept', say so in the deck's "
        "limitations. Rows removed for quality often differ systematically.", "",
        "| Measure | All rows | Kept | Excluded | Shift |",
        "|---|---|---|---|---|",
    ]
    for row in r["exclusion_impact"][:12]:
        lines.append(
            f"| `{row['column']}` | {row['all_rows']} | {row['kept']} | "
            f"{row['excluded']} | {row['shift_from_cleaning']:+} |"
        )
    if r.get("derived_columns"):
        lines += [
            "", "## Derived band columns", "",
            "Declared in `project.yaml` before analysis. Cut points come from the "
            "instrument or from quantiles of the cleaned sample, never from the "
            "outcome.", "",
            "| Column | From | Method | Edges | Bands (n) |",
            "|---|---|---|---|---|",
        ]
        for d in r["derived_columns"]:
            if not d.get("applied"):
                lines.append(f"| `{d.get('name')}` | - | - | - | not applied - "
                             f"{d.get('reason', '')} |")
                continue
            bands = ", ".join(f"{b['label']} ({b['n']})" for b in d["bands"])
            lines.append(
                f"| `{d['name']}` | `{d['from']}` | {d['method']} | "
                f"{d['edges']} | {bands} |"
            )

    lines += ["", "## Decide", "",
              "- Are these the right screens for this instrument?",
              "- Any screen you need to add (attention checks, off-target respondents)?",
              "- Does any shift above need to appear in the deck's limitations?", ""]
    project.path("analysis/cleaning_report.md").write_text("\n".join(lines))
