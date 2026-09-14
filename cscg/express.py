"""Express mode: data files in, deck-ready brief out, in ONE command.

Why this exists. A timed run (Sept 14, 2026) took 28 minutes and 7.4M tokens. The
Python was ~2s per build; the rest was agent turns: 15 hand edits to project.yaml,
reading engine source to learn the config syntax, reading a 71k-character briefing,
a blocking approval, four reviewer agents, 13 storyline edits, 12 preview images.
Every turn re-reads the whole conversation, so turns x context is the cost.

Express moves everything mechanical into this command and prints a compact brief
(< ~6k tokens) that already contains slide-ready numbers, chart specs and a storyline
skeleton. The agent reads nothing else.

Analytical discipline is kept: the analysis plan is declared from the STRUCTURE of the
data (column types, names, level counts) before any result is computed, and recorded
as `auto_declared` in project.yaml. Nothing here looks at a result to decide what to
test. Tailored cuts (e.g. a price band for one account type) are full-mode work.
"""
from __future__ import annotations

import csv
import re
import shutil
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from . import analyze, clean, config, ingest, intake, project as proj, qualitative, util
from .findings import Finding, FindingStore

OUTCOME_RE = re.compile(r"(renew|retain|retention|churn|lapse|attend|return|purchas|bought|"
                        r"convert|subscrib|repeat|actual)", re.I)
FLAG_RE = re.compile(r"(^keep$|too_fast|straight|same_answer|impossible|_flag$|^flag_|"
                     r"duplicate|^_)", re.I)
PARADATA_RE = re.compile(r"(duration|seconds|_sec$|timestamp|device|browser|ip_addr|"
                         r"recorded|start_?date|end_?date)", re.I)
SEGMENT_RE = re.compile(r"(type|segment|tier|level|class|status|member|group|account|"
                        r"year|student|plan|cohort)", re.I)
BEHAVIOUR_RE = re.compile(r"(pct|share|games|scanned|visits|tenure|spend|price|distance|"
                          r"frequency|left|arrival|transfer)", re.I)
ITEM_RE = re.compile(r"(^sat_|satisf|rating|likely|intent|nps|recommend|overall)", re.I)
DEMOG_RE = re.compile(r"(gender|income|^age$|ethnic|race|zip|postal|kids|children|alum|"
                      r"marital)", re.I)
TEXT_COLS = ("verbatim", "quote", "comment", "excerpt", "text", "response")
BAND_LABELS = ["Lowest quarter", "Second quarter", "Third quarter", "Highest quarter"]

MAX_LEADS, MAX_NULLS, MAX_THEMES = 10, 6, 4
BRIEF_CHAR_CAP = 24000


# ---------------------------------------------------------------------------
# 1. pick the sources
# ---------------------------------------------------------------------------

def _choose_sources(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Survey sheet = widest respondent-level table that is not someone's cleaned copy
    (our cleaning must run on raw rows). Focus groups = a respondent-level table with a
    verbatim/quote column."""
    survey, fg = None, None
    for r in results:
        sheets = r.get("sheets") or ([{"sheet": "", "kind": r.get("kind"),
                                       "columns": r.get("columns", 0),
                                       "column_names": r.get("column_names", []),
                                       "rows_sampled": r.get("rows_sampled", 0)}]
                                     if r.get("kind") else [])
        for s in sheets:
            names = [c.lower() for c in s.get("column_names", [])]
            is_text = any(any(t in c for t in TEXT_COLS) for c in names)
            if is_text and s.get("columns", 0) <= 12:
                if fg is None or s.get("rows_sampled", 0) > fg["rows"]:
                    fg = {"file": r["file"], "sheet": s["sheet"], "names": s.get("column_names", []),
                          "rows": s.get("rows_sampled", 0)}
                continue
            if s.get("kind") != "raw_respondent_data":
                continue
            score = (0 if "clean" in str(s["sheet"]).lower() else 1, s.get("columns", 0),
                     s.get("rows_sampled", 0))
            if survey is None or score > survey["score"]:
                survey = {"file": r["file"], "sheet": s["sheet"], "score": score}
    if survey is None:
        raise SystemExit("express: no respondent-level table found. Run `cscg intake` and "
                         "read analysis/intake.md - this data needs full mode.")
    return {"survey": survey, "fg": fg}


def _fg_columns(names: list[str]) -> dict[str, str]:
    def pick(keys, text=False):
        for k in keys:
            for n in names:
                nl = n.lower()
                if k in nl and not (text and nl.endswith("_id")):
                    return n
        return ""
    return {"focus_group_id_column": pick(("group_id", "session", "group")),
            "focus_group_participant_column": pick(("participant", "speaker", "person")),
            "focus_group_text_column": pick(("verbatim", "quote", "comment", "text",
                                             "response", "excerpt"), text=True)}


# ---------------------------------------------------------------------------
# 2. declare the analysis from structure
# ---------------------------------------------------------------------------

BEHAV_PRIORITY = ("left", "scan", "price_change", "change", "transfer", "tenure", "arrival",
                  "games", "spend", "visits", "distance")


def humanise(col: str) -> str:
    """Column name -> the words a slide can show. Finding labels inherit this, so it
    has to happen before analysis: 'sat_crowd_atmosphere' must never reach a chart."""
    low = col.strip().lower()
    if low.startswith("sat_"):
        base = "satisfaction with " + low[4:]
    elif low.startswith("imp_"):
        base = "importance of " + low[4:]
    else:
        base = low
    base = re.sub(r"_pct$", " (%)", base)
    base = base.replace("_", " ")
    base = re.sub(r"\bpct\b", "share", base)
    base = re.sub(r"\bqtr\b", "quarter", base)
    base = re.sub(r"\bself report\b", "(self-reported)", base)
    base = re.sub(r"\bactual\b", "(recorded)", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base[:1].upper() + base[1:]


def _redundant(df: pd.DataFrame, a: str, b: str) -> bool:
    """Two segment columns that split the sample the same way (e.g. respondent_type and
    account_type) double every finding and every test. Structure only - no outcome used."""
    if a not in df.columns or b not in df.columns:
        return False
    sub = df[[a, b]].dropna().astype(str)
    if len(sub) < 30:
        return False
    purity = sub.groupby(a)[b].agg(lambda x: x.value_counts(normalize=True).iloc[0])
    weights = sub[a].value_counts(normalize=True).reindex(purity.index)
    return float((purity * weights).sum()) > 0.98


def autoconfig(project, outcome: str | None, population: str | None) -> dict[str, Any]:
    path = project.path("analysis/data_dictionary.json")
    prof = util.read_json(path)
    dic = prof["dictionary"]
    by = {e["column"]: e for e in dic}
    data = project.cfg.get("data") or {}
    df = ingest.read_any(project.path("data/raw", data["survey_file"]),
                         data.get("survey_sheet") or None)

    for e in dic:
        c, t = e["column"], e["inferred_type"]
        default_qt = c.replace("_", " ").strip().capitalize()
        if not e.get("question_text") or e["question_text"] == default_qt:
            e["question_text"] = humanise(c)
        if t in ("id", "empty", "open_text") or FLAG_RE.search(c) or PARADATA_RE.search(c):
            e["analysis_role"] = "exclude"

    if outcome and outcome not in by:
        raise SystemExit(f"express: --outcome '{outcome}' is not a column. Columns: "
                         f"{', '.join(list(by)[:40])}")
    if not outcome:
        cands = [e["column"] for e in dic if e["inferred_type"] == "binary"
                 and OUTCOME_RE.search(e["column"]) and e["analysis_role"] != "exclude"]
        cands.sort(key=lambda c: (0 if "actual" in c.lower() else 1, len(c)))
        outcome = cands[0] if cands else None

    items = [e["column"] for e in dic if e["inferred_type"] == "ordinal"
             and ITEM_RE.search(e["column"]) and e["analysis_role"] != "exclude"
             and e["column"] != outcome][:14]
    behav = [e["column"] for e in dic if e["inferred_type"] in ("numeric", "ordinal")
             and BEHAVIOUR_RE.search(e["column"]) and not ITEM_RE.search(e["column"])
             and e["analysis_role"] != "exclude" and e.get("n_unique", 0) >= 5
             and not DEMOG_RE.search(e["column"]) and e["column"] != outcome]
    prio = lambda c: next((i for i, k in enumerate(BEHAV_PRIORITY) if k in c.lower()), 99)
    behav.sort(key=prio)

    # Measures compared across segments: the outcome and the rated items. Behavioural
    # numbers (price, tenure, distance...) are predictors - banded into segments and
    # correlated with the outcome - not things to compare across account types.
    measures = ([outcome] if outcome else []) + items
    for e in dic:
        e["analysis_role"] = ("measure" if e["column"] in measures
                              else "exclude" if e["analysis_role"] == "measure"
                              else e["analysis_role"])

    segs = []
    for e in dic:
        c = e["column"]
        if c == outcome or e["analysis_role"] == "exclude" or \
                e["inferred_type"] not in ("binary", "categorical"):
            continue
        levels = e.get("levels") or []
        if not 2 <= len(levels) <= 6 or sum(1 for l in levels if l.get("n", 0) >= 30) < 2:
            continue
        pri = 2 if DEMOG_RE.search(c) else (0 if SEGMENT_RE.search(c) else 1)
        segs.append((pri, len(levels), c, e))
    segs.sort(key=lambda x: (x[0], x[1]))
    chosen: list[str] = []
    for _, _, c, _ in segs:
        if any(_redundant(df, k, c) for k in chosen):
            continue
        chosen.append(c)
        if len(chosen) == 3:
            break
    segments = [{"column": c, "label": by[c]["question_text"]} for c in chosen]

    derived = []
    for c in [b for b in behav if by[b].get("n_unique", 0) >= 8][:4]:
        name = f"{c}_band"
        qt = f"{by[c]['question_text']} (quartiles)"
        derived.append({"name": name, "from": c, "method": "quantile_bands", "bands": 4,
                        "labels": BAND_LABELS, "question_text": qt})
        segments.append({"column": name, "label": qt, "order": BAND_LABELS})

    correlations = ([{"x": m, "y": outcome} for m in items + behav[:6]][:18]
                    if outcome else [])

    util.write_json(path, prof)
    rl = (f"Respondents, not all {population}." if population
          else config.rules()["bases"]["respondent_language"])
    return {"outcome": outcome, "segments": segments, "derived_columns": derived,
            "correlations": correlations, "measures": measures, "respondent_language": rl}


# ---------------------------------------------------------------------------
# 3. the brief
# ---------------------------------------------------------------------------

def _fmt(f: Finding, v: float) -> str:
    if f.metric == "percent":
        return f"{v:.0%}"
    if f.metric == "correlation":
        return f"{v:.2f}"
    if f.metric == "count":
        return f"{v:,.0f}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def _claim(f: Finding) -> str:
    gs = [g for g in f.groups if not g.suppressed]
    parts = [f"{g.label} {_fmt(f, g.value)} (n={g.n:,}){'†' if g.directional_only else ''}"
             for g in gs]
    s = " | ".join(parts)
    if f.gap_pp is not None:
        s += f" | gap {round(f.gap_pp):.0f} points"
    return s


def _q(s: str) -> str:
    return '"' + str(s).replace('"', "'") + '"'


def _chart_spec(f: Finding, ordered: bool) -> str:
    gs = [g for g in f.groups if not g.suppressed]
    hi = max(gs, key=lambda g: g.value).label if gs else ""
    fmt = ", value_format: percent" if f.metric == "percent" else ""
    if len(gs) >= 3 and ordered:
        typ = "line" if str(f.provenance.get("segment_column", "")).endswith("_band") else "column"
    elif len(gs) >= 4:
        typ = "ranked_bar"
    else:
        typ = "grouped_bar"
    return f"{{finding_id: {f.id}, type: {typ}, highlight: {_q(hi)}{fmt}}}"


def write_brief(project) -> str:
    cfg = project.cfg
    ex = cfg.get("auto_declared") or {}
    outcome = ex.get("outcome")
    store = FindingStore.load(project.path("analysis/findings.json"))
    cr = util.read_json(project.path("analysis/cleaning_report.json"))
    rl = cfg.get("respondent_language") or config.rules()["bases"]["respondent_language"]
    seg_by = {s["column"]: s for s in cfg.get("segments") or []}

    tested = [f for f in store if f.kind in ("proportion_by_segment", "mean_by_segment")
              and f.test and f.test.p_adj is not None]
    eff = lambda f: abs(f.test.effect_value or 0)
    first = lambda f: 0 if outcome and f.question_id == outcome else 1
    on_outcome = sorted([f for f in tested if f.callable_difference and first(f) == 0],
                        key=lambda f: -eff(f))
    others = sorted([f for f in tested if f.callable_difference and first(f) == 1],
                    key=lambda f: -eff(f))[:3]
    leads = (on_outcome + others)[:MAX_LEADS]
    nulls = sorted([f for f in tested if not f.callable_difference
                    and (f.overall_n or 0) >= 300
                    and f.test.effect_reading in ("negligible", None)],
                   key=lambda f: (first(f), -(f.overall_n or 0)))[:MAX_NULLS]
    ranks = [f for f in store if f.kind == "ranked_items" and f.metric == "correlation"]
    comps = [f for f in store if f.kind == "composition"]
    outcome_f = next((f for f in leads + nulls if f.question_id == outcome
                      and f.overall_value is not None), None)

    screens = {k: v["rows_flagged"] for k, v in cr.get("screens", {}).items() if v["rows_flagged"]}
    allow = sorted({cr["rows_in"], cr["rows_excluded"], cr["rows_kept"], 10, *screens.values()})

    L = [f"# Express brief: {cfg.get('title', project.slug)}",
         f"Question: {str(cfg.get('business_question', '')).strip()}",
         f"Client: {cfg.get('client')} | Audience: {cfg.get('audience')} | "
         f"{cr['rows_kept']:,} of {cr['rows_in']:,} rows analysed "
         f"({cr['rows_excluded']:,} excluded: {', '.join(f'{k} {v}' for k, v in screens.items()) or 'none'})",
         f"Outcome: {outcome or 'none detected - comparisons only'}"
         + (f" (overall {_fmt(outcome_f, outcome_f.overall_value)}, cite {outcome_f.id})" if outcome_f else ""),
         f"Segments (auto-declared from column structure, before results): "
         f"{'; '.join(s['label'] for s in cfg.get('segments') or []) or 'none'}",
         "Not run in express: tailored bands, conditioning checks, value bounds, open-text coding.",
         "",
         "Copy numbers EXACTLY as written below. Every slide's `cites:` must list the IDs whose numbers it uses.",
         "",
         "## Leads (callable: may be written as differences), strongest effect first"]
    for i, f in enumerate(leads, 1):
        seg = str(f.provenance.get("segment_column", ""))
        L += [f"L{i} {f.id}",
              f"   {f.question_text} by {seg_by.get(seg, {}).get('label', seg)}",
              f"   {_claim(f)}",
              f"   chart: {_chart_spec(f, bool(seg_by.get(seg, {}).get('order')))}",
              f"   source: Source: {f.question_text}, by {seg_by.get(seg, {}).get('label', seg)}. "
              f"n={f.overall_n:,}. {f.test.name}, BH-adjusted. {rl}"]
    if not leads:
        L.append("_None. Say so: nothing separates the declared segments._")

    if ranks:
        r = ranks[0]
        top = [g for g in r.groups if not g.suppressed][:8]
        L += ["", f"## What tracks the outcome ({r.id}; correlations, not causes)",
              "   " + " | ".join(f"{g.label} {g.value:.2f}" for g in top),
              f"   chart: {{finding_id: {r.id}, type: ranked_bar, highlight: {_q(top[0].label if top else '')}, value_format: correlation}}"]

    L += ["", "## Well-powered nulls (no difference: write 'similar' / 'nothing separates', never 'vs' or 'gap')"]
    for f in nulls:
        L.append(f"N {f.id}: {f.question_text}: {_claim(f).split(' | gap')[0]}")
    if not nulls:
        L.append("_None._")

    themes_path = project.path("analysis/themes.json")
    if themes_path.exists():
        th = util.read_json(themes_path).get("themes", [])[:MAX_THEMES]
        if th:
            L += ["", "## Focus-group themes (voice, not prevalence; cite the Q_ id)"]
            for t in th:
                qid = "Q_" + util.slugify(t["theme"])[:28]
                q = (t.get("quotes") or [{}])[0]
                words = str(q.get("text", "")).split()
                quote = " ".join(words[:28]) + ("..." if len(words) > 28 else "")
                L.append(f"{qid}: {t['prevalence']} | \"{quote}\" ({q.get('attribution', '')})")

    comp_line = "; ".join(f"{f.id}: " + ", ".join(f"{g.label} {_fmt(f, g.value)}"
                                                 for g in f.groups if not g.suppressed)[:160]
                          for f in comps[:3])
    L += ["", "## Composition (how_to_read stats; composition findings may be donuts)", comp_line or "_none_"]

    agenda_hint = '["Pillar one", "Pillar two", "Pillar three"]'
    cites_htr = ", ".join([f.id for f in comps[:3]] + ([outcome_f.id] if outcome_f else []))
    stat2 = (f'      - {{value: "{_fmt(outcome_f, outcome_f.overall_value)}", label: {_q(outcome_f.question_text[:60])}}}\n'
             if outcome_f else "")
    L += ["", "## Storyline skeleton - write the whole file once to projects/"
          f"{project.slug}/storyline/storyline.yaml",
          "```yaml",
          "meta: {" f"client: {_q(cfg.get('client'))}, term: {_q(cfg.get('term'))}, theme: dark, "
          f"synthetic: {str(bool(cfg.get('synthetic_data'))).lower()}, "
          f"filename: \"CSCG_{project.slug}.pptx\"" "}",
          "governing_thought: \"<one claim someone could disagree with>\"",
          "slides:",
          f"  - {{layout: title, subject: {_q(cfg.get('title') if cfg.get('title') not in (None, '', project.slug) else '<deck subject>')}, date: \"<month year>\"}}",
          f"  - {{layout: agenda, items: {agenda_hint}}}      # 3 pillars, <=4 words each; = section tabs",
          "  - layout: executive_summary",
          "    title: \"<governing thought, with its number>\"",
          "    cites: [<every id used below>]",
          "    findings:                                     # 3-4 items; statement ~25 words, so_what ~12",
          "      - {statement: \"...\", so_what: \"...\"}",
          "    source: \"Source: ...\"",
          "  - layout: how_to_read",
          "    section: \"Pillar one\"",
          f"    title: \"{cr['rows_kept']:,} responses analysed after quality screens, {cr['rows_excluded']:,} excluded before any result was read.\"",
          f"    cites: [{cites_htr}]",
          f"    allow_numbers: {allow}",
          "    stats:",
          f"      - {{value: \"{cr['rows_kept']:,}\", label: \"responses analysed\"}}",
          stat2.rstrip("\n") if stat2 else "      # add a composition share from the section above",
          "    bullets:",
          f"      - \"{cr['rows_excluded']:,} of {cr['rows_in']:,} responses excluded before analysis.\"",
          "      - \"Results are unweighted: read each group on its own base.\"",
          "      - \"A difference is called only if it clears an adjusted test and a 10-point floor.\"",
          f"    source: \"Source: {Path(str(cr.get('source_file', ''))).name}. {rl}\"",
          "  # body: 4-7 slides, one lead each. chart_with_notes = {section, kicker, title, cites, chart, chart_caption, notes: [2-3 {label, text}], source}",
          "  # close: recommendation_table {title, cites, rows: [{recommendation, evidence, implication}]} or discussion_questions",
          "```",
          "",
          "Rules: titles carry their number, sentence case, <=2 lines. Notes <=35 words, labels from: "
          "SO WHAT, WATCH-OUT, IMPLICATION, WHO CITES IT, ACROSS GROUPS, CONTEXT. Sources <=40 words. "
          "Chart `highlight` must be a group label exactly as written above. "
          "No test names or p-values outside `source:`. No causal verbs."]

    text = "\n".join(L)
    if len(text) > BRIEF_CHAR_CAP:
        text = text[:BRIEF_CHAR_CAP] + "\n[brief truncated at cap]"
    out = project.path("insights/brief.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n")
    return text


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def run(slug: str, files: list[str], question: str = "", client: str = "UNC Athletics",
        audience: str = "", title: str = "", outcome: str | None = None,
        population: str | None = None, synthetic: bool = False) -> dict[str, Any]:
    t0 = time.time()
    root = config.PROJECTS_DIR / util.slugify(slug)
    p = proj.load(str(root)) if root.exists() else proj.create(
        slug, title=title or slug, client=client, question=question, audience=audience)

    raw = p.path("data/raw")
    for f in files or []:
        src = Path(f).expanduser()
        if not src.exists():
            raise SystemExit(f"express: file not found: {src}")
        dst = raw / src.name
        if not dst.exists():
            shutil.copy2(src, dst)

    ir = intake.run(p)
    src = _choose_sources(ir["results"])

    cfg = dict(p.cfg)
    cfg["title"] = title or cfg.get("title") or slug
    cfg["client"] = client or cfg.get("client")
    if question:
        cfg["business_question"] = question
    if audience:
        cfg["audience"] = audience
    data = dict(cfg.get("data") or {})
    data.update({"survey_file": src["survey"]["file"], "survey_sheet": src["survey"]["sheet"],
                 "open_text_columns": []})
    if src["fg"]:
        data.update({"focus_group_file": src["fg"]["file"],
                     "focus_group_sheet": src["fg"]["sheet"], **_fg_columns(src["fg"]["names"])})
    cfg["data"] = data
    cfg["synthetic_data"] = bool(synthetic or cfg.get("synthetic_data"))
    cfg["theme"] = "dark"
    _save(p, cfg)
    p = proj.load(str(p.root))

    ingest.run(p)
    ac = autoconfig(p, outcome, population)
    cfg = dict(p.cfg)
    cfg.update({"segments": ac["segments"], "derived_columns": ac["derived_columns"],
                "correlations": ac["correlations"], "respondent_language": ac["respondent_language"],
                "nonrandom_sample": True,
                "auto_declared": {"outcome": ac["outcome"], "measures": ac["measures"],
                                  "declared_at": util.run_id(),
                                  "rule": "declared from column structure before any result was computed"}})
    _save(p, cfg)
    p = proj.load(str(p.root))

    clean.run(p)
    meta = analyze.run(p)

    themes = 0
    if src["fg"]:
        try:
            qualitative.extract(p)
            coded = pd.read_csv(p.path("analysis/comments_to_code.csv"), dtype=object)
            if "theme_code" in coded and coded["theme_code"].fillna("").astype(str).str.strip().ne("").mean() > 0.5:
                shutil.copy2(p.path("analysis/comments_to_code.csv"), p.path("analysis/comments_coded.csv"))
                store = FindingStore.load(p.path("analysis/findings.json"))
                themes = len(qualitative.tally(p, store)["themes"])
                store.save(p.path("analysis/findings.json"), {"note": "express: analysis + pre-coded themes"})
        except SystemExit:
            pass

    brief = write_brief(proj.load(str(p.root)))
    return {"slug": p.slug, "seconds": round(time.time() - t0, 1), "brief": brief,
            "findings": meta.get("tests_run"), "callable": meta.get("callable_differences"),
            "themes": themes, "outcome": ac["outcome"]}


def _save(p, cfg: dict[str, Any]) -> None:
    header = ("# CSCG engagement configuration. Written by `cscg express`; segments, bands and\n"
              "# correlations under auto_declared were chosen from column structure before any\n"
              "# result was computed. Edit and re-run for tailored cuts (full mode).\n")
    p.path("project.yaml").write_text(header + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=100))
