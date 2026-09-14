"""Open-text and focus-group handling.

Division of labour: the qualitative-analyst AGENT reads the comments and assigns theme
codes (judgement). This module does everything else deterministically - extracting the
comments, counting the codes, computing prevalence, and turning it into findings.

Counts of open-text themes are never expressed as survey percentages. A comment theme
tells you what people who chose to write said, not what the population thinks.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import pandas as pd

from . import config, util
from .findings import Finding, FindingStore, Group

MIN_COMMENT_CHARS = 12


def extract(project) -> dict[str, Any]:
    """Pull open-text responses out of the cleaned data into a codeable CSV."""
    data_cfg = project.cfg.get("data", {}) or {}
    cols = data_cfg.get("open_text_columns") or []
    clean_path = project.path("data/processed/clean.csv")
    if not clean_path.exists():
        raise SystemExit("Run clean first.")
    df = pd.read_csv(clean_path, dtype=object)

    if not cols:
        dic = util.read_json(project.path("analysis/data_dictionary.json"))["dictionary"]
        cols = [e["column"] for e in dic if e["analysis_role"] == "qualitative"]

    id_col = data_cfg.get("id_column")
    segments = [s["column"] for s in (project.cfg.get("segments") or [])
                if s.get("column") in df.columns]

    rows = []
    for col in cols:
        if col not in df.columns:
            continue
        for idx, val in df[col].items():
            text = str(val).strip() if pd.notna(val) else ""
            if len(text) < MIN_COMMENT_CHARS or text.lower() in ("nan", "n/a", "na", "none"):
                continue
            row = {
                "comment_id": f"{col}:{idx}",
                "respondent_id": df.at[idx, id_col] if id_col and id_col in df.columns else idx,
                "source": "survey_open_text",
                "question": col,
                "verbatim": text,
                "theme_code": "",        # <- the agent fills these three
                "sentiment": "",
                "is_representative": "",
            }
            for s in segments:
                row[f"seg_{s}"] = df.at[idx, s]
            rows.append(row)

    # Focus-group notes, if supplied as a pre-coded CSV.
    fg_file = data_cfg.get("focus_group_file")
    n_fg_sessions = 0
    if fg_file:
        fg_path = project.path("data/raw", fg_file)
        if fg_path.exists():
            fg = pd.read_csv(fg_path, dtype=object) if fg_path.suffix == ".csv" \
                else pd.read_excel(fg_path, sheet_name=data_cfg.get("focus_group_sheet") or 0, dtype=object)
            gcol = data_cfg.get("focus_group_id_column", "group_id")
            n_fg_sessions = fg[gcol].nunique() if gcol in fg.columns else 0
            for idx, r in fg.iterrows():
                rows.append({
                    "comment_id": f"fg:{idx}",
                    "respondent_id": r.get(data_cfg.get("focus_group_participant_column", "participant_id"), idx),
                    "source": "focus_group",
                    "question": r.get(gcol, ""),
                    "verbatim": str(r.get(data_cfg.get("focus_group_text_column", "verbatim"), "")).strip(),
                    "theme_code": str(r.get("theme_code", "") or ""),
                    "sentiment": str(r.get("sentiment", "") or ""),
                    "is_representative": "",
                    **{f"seg_{s}": r.get("group_segment", "") for s in segments[:1]},
                })

    out = project.path("analysis/comments_to_code.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fieldnames = list(rows[0].keys())
        for r in rows:
            for k in r:
                if k not in fieldnames:
                    fieldnames.append(k)
        with out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    summary = {
        "comments_extracted": len([r for r in rows if r["source"] == "survey_open_text"]),
        "focus_group_excerpts": len([r for r in rows if r["source"] == "focus_group"]),
        "focus_group_sessions": int(n_fg_sessions),
        "columns_used": cols,
        "file": str(out),
        "already_coded": len([r for r in rows if r["theme_code"]]),
    }
    util.write_json(project.path("analysis/qualitative_extract.json"), summary)
    return summary


def tally(project, store: FindingStore | None = None) -> dict[str, Any]:
    """Count coded themes deterministically and emit theme_prevalence findings.

    Expects analysis/comments_coded.csv - the same file as comments_to_code.csv with
    theme_code filled in by the qualitative-analyst agent.
    """
    coded_path = project.path("analysis/comments_coded.csv")
    if not coded_path.exists():
        raise SystemExit(
            "No analysis/comments_coded.csv. The qualitative-analyst agent must code "
            "analysis/comments_to_code.csv and save it under that name."
        )
    df = pd.read_csv(coded_path, dtype=object)
    df["theme_code"] = df["theme_code"].fillna("").astype(str).str.strip()
    coded = df[df["theme_code"] != ""]

    survey = coded[coded["source"] == "survey_open_text"]
    fg = coded[coded["source"] == "focus_group"]
    base_comments = int((df["source"] == "survey_open_text").sum())
    fg_sessions = int(fg["question"].nunique()) if not fg.empty else 0

    themes = []
    for theme, grp in coded.groupby("theme_code"):
        s_count = int((grp["source"] == "survey_open_text").sum())
        f_rows = grp[grp["source"] == "focus_group"]
        f_sessions = int(f_rows["question"].nunique()) if not f_rows.empty else 0
        quotes = grp[grp["verbatim"].notna()].copy()
        # Prefer quotes the coder marked representative.
        rep = quotes[quotes.get("is_representative", "").astype(str).str.lower().isin(["1", "true", "yes", "y"])]
        chosen = (rep if not rep.empty else quotes).head(
            config.rules()["qualitative"]["max_quotes_per_theme"])
        themes.append({
            "theme": theme,
            "survey_comments": s_count,
            "comment_base": base_comments,
            "focus_group_sessions": f_sessions,
            "focus_group_total_sessions": fg_sessions,
            "_fg_excerpts": int(len(f_rows)),
            "prevalence": _prevalence(s_count, base_comments, len(f_rows),
                                      f_sessions, fg_sessions),
            "sentiment_mix": grp["sentiment"].fillna("").value_counts().to_dict(),
            "quotes": [
                {"text": str(r["verbatim"]).strip(),
                 "attribution": _attribution(r),
                 "source": r["source"]}
                for _, r in chosen.iterrows()
            ],
        })
    themes.sort(key=lambda t: (-t["survey_comments"], -t["focus_group_sessions"]))

    if store is not None:
        # Re-running the tally replaces the previous themes rather than appending.
        store.drop_kind("theme_prevalence")
        rid = util.run_id(project.slug)
        for t in themes:
            fg_excerpts_t = sum(1 for _ in range(0))  # placeholder, set below
            fg_excerpts_t = t["_fg_excerpts"]
            if base_comments:
                grp = Group(label=t["theme"], n=base_comments,
                            value=t["survey_comments"] / base_comments,
                            count=t["survey_comments"])
                o_n, o_v = base_comments, float(t["survey_comments"])
            else:
                # Focus-group-only evidence. The citable quantities are sessions and
                # excerpt counts, never a percentage - 6 sessions is not a sample.
                total = max(fg_sessions, 1)
                grp = Group(label=t["theme"], n=fg_sessions,
                            value=t["focus_group_sessions"] / total,
                            count=t["focus_group_sessions"])
                o_n, o_v = fg_sessions, float(fg_excerpts_t)
            store.add(Finding(
                # Derived from the theme name, not a counter: a storyline citation must
                # keep pointing at the same theme when the tally is re-run.
                id="Q_" + util.slugify(t["theme"])[:28],
                kind="theme_prevalence",
                metric="count",
                question_id=f"theme:{t['theme']}",
                question_text=t["theme"],
                base_definition=(f"{base_comments} coded open-text comments"
                                 if base_comments else "")
                                + (f"{'; ' if base_comments else ''}"
                                   f"{fg_sessions} focus-group sessions" if fg_sessions else ""),
                groups=[grp],
                overall_n=o_n,
                overall_value=o_v,
                caveats=[config.rules()["qualitative"]["focus_group_caveat"].strip()],
                tags=["qualitative", "theme"],
                provenance={"code": "cscg.qualitative.tally",
                            "file": str(coded_path), "run_id": rid},
            ))

    result = {
        "coded_comments": int(len(survey)),
        "uncoded_comments": int(base_comments - len(survey)),
        "comment_base": base_comments,
        "focus_group_excerpts": int(len(fg)),
        "focus_group_sessions": fg_sessions,
        "themes": themes,
    }
    util.write_json(project.path("analysis/themes.json"), result)
    _write_markdown(project, result)
    return result


def _prevalence(survey_count: int, comment_base: int, fg_excerpts: int,
                fg_sessions: int, fg_total_sessions: int) -> str:
    """State prevalence in the terms the evidence actually supports.

    Open-text comments get a count over the comment base. Focus groups get sessions
    over total sessions - never a percentage, because 6 sessions is not a sample.
    """
    parts = []
    if comment_base:
        parts.append(config.rules()["qualitative"]["prevalence_format"].format(
            count=survey_count, base=comment_base))
    if fg_total_sessions:
        parts.append(f"{fg_excerpts} excerpt{'s' if fg_excerpts != 1 else ''} "
                     f"in {fg_sessions} of {fg_total_sessions} focus groups")
    return "; ".join(parts) or "no coded evidence"


def _attribution(row) -> str:
    seg_cols = [c for c in row.index if c.startswith("seg_")]
    seg = next((str(row[c]) for c in seg_cols if pd.notna(row[c]) and str(row[c]).strip()), "")
    src = "focus group" if row["source"] == "focus_group" else "survey"
    return f"{seg}, {src}".strip(", ") if seg else src


def _write_markdown(project, r: dict[str, Any]) -> None:
    lines = [
        f"# Qualitative themes - {project.cfg.get('title', project.slug)}",
        "",
        (f"{r['coded_comments']} of {r['comment_base']} open-text comments coded. "
         if r["comment_base"] else "No open-text survey comments in this dataset. ")
        + (f"{r['focus_group_excerpts']} focus-group excerpts across "
           f"{r['focus_group_sessions']} sessions." if r["focus_group_excerpts"] else ""),
        "",
        f"> {config.rules()['qualitative']['focus_group_caveat'].strip()}",
        "",
        "| Theme | Comments | Focus groups | Sentiment |",
        "|---|---|---|---|",
    ]
    for t in r["themes"]:
        sm = ", ".join(f"{k}:{v}" for k, v in t["sentiment_mix"].items() if k)
        fgs = (f"{t['focus_group_sessions']} of {t['focus_group_total_sessions']}"
               if t["focus_group_total_sessions"] else "-")
        lines.append(f"| {t['theme']} | {t['prevalence']} | {fgs} | {sm} |")

    lines += ["", "## Evidence", ""]
    for t in r["themes"]:
        lines.append(f"### {t['theme']}")
        lines.append(f"_{t['prevalence']}_"
                     + (f"; {t['focus_group_sessions']} of {t['focus_group_total_sessions']} focus groups"
                        if t["focus_group_total_sessions"] else ""))
        for q in t["quotes"]:
            lines.append(f"> “{q['text']}”")
            lines.append(f"> — {q['attribution']}")
            lines.append("")
    project.path("analysis/themes.md").write_text("\n".join(lines))
