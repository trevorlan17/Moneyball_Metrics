"""Stage 3: exploratory analysis -> findings.json.

Produces the descriptive and comparative results that a deck can be built from.
What it deliberately does NOT do: fit models nobody asked for. The rule from
config/analysis_rules.yaml is that analysis follows the question. This stage runs
the analyses that are always justified (composition, distributions, declared-segment
comparisons, declared self-report checks) and then *suggests* deeper work for a human
to approve rather than running it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import config, stats as st, util
from .findings import Finding, FindingStore, Group, Test


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _dic(project) -> list[dict[str, Any]]:
    return util.read_json(project.path("analysis/data_dictionary.json"))["dictionary"]


def _entry(dic, col: str) -> dict[str, Any]:
    for e in dic:
        if e["column"] == col:
            return e
    return {}


def _qtext(dic, col: str) -> str:
    return _entry(dic, col).get("question_text", col)


def _numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _group_flags(n: int) -> tuple[bool, bool, list[str]]:
    b = config.rules()["bases"]
    directional = n < b["small_group_threshold"]
    suppressed = n < b["suppress_below"]
    flags = []
    if suppressed:
        flags.append("suppressed_small_base")
    elif directional:
        flags.append("directional_small_base")
    return directional, suppressed, flags


def _positive_mask(s: pd.Series, entry: dict) -> pd.Series | None:
    """Define 'agrees / selected / top-box' for a column, so a proportion is well defined.

    Returns None when the column has no defensible binary reading - in which case we
    do not invent one.
    """
    non_null = s.dropna()
    if non_null.empty:
        return None
    itype = entry.get("inferred_type")

    nums = _numeric(s)
    if nums.notna().mean() > 0.95:
        vals = sorted(nums.dropna().unique().tolist())
        if set(vals) <= {0.0, 1.0}:
            return nums == 1
        if itype == "ordinal" and "scale_range" in entry:
            lo, hi = entry["scale_range"]
            # Top-two-box on a 5+ point scale, top box on a 3-4 point scale.
            width = hi - lo + 1
            cut = hi - 1 if width >= 5 else hi
            return nums >= cut
        return None

    text = s.astype(str).str.strip().str.lower()
    yes = {"yes", "true", "1", "y", "selected", "checked"}
    if set(text.dropna().unique()) <= yes | {"no", "false", "0", "n", "not selected", "unchecked", "nan", ""}:
        return text.isin(yes)
    agree = text.str.contains("strongly agree|somewhat agree", regex=True, na=False)
    if agree.any():
        return agree
    return None


# ---------------------------------------------------------------------------
# finding builders
# ---------------------------------------------------------------------------

def _display(lv, labels: dict | None) -> str:
    """Map a raw segment value to the label that should appear on a slide."""
    if labels and str(lv) in labels:
        return str(labels[str(lv)])
    return str(lv)


def proportion_by_segment(store: FindingStore, df: pd.DataFrame, dic,
                          measure: str, segment: str, seg_label: str,
                          order: list[str] | None, run_meta: dict,
                          labels: dict | None = None) -> Finding | None:
    entry = _entry(dic, measure)
    pos = _positive_mask(df[measure], entry)
    if pos is None:
        return None

    valid = df[measure].notna() & df[segment].notna()
    sub = df[valid]
    if sub.empty:
        return None

    levels = order or sorted(sub[segment].dropna().astype(str).unique().tolist())
    groups, counts, totals, flags = [], [], [], []
    for lv in levels:
        mask = sub[segment].astype(str) == str(lv)
        n = int(mask.sum())
        if n == 0:
            continue
        k = int(pos[sub.index][mask].sum())
        directional, suppressed, gf = _group_flags(n)
        flags += [f"{f}:{lv}" for f in gf]
        if suppressed:
            continue
        groups.append(Group(label=_display(lv, labels), n=n, value=k / n, count=k,
                            directional_only=directional))
        counts.append(k)
        totals.append(n)

    if len(groups) < 2:
        return None

    res = st.compare_proportions(counts, totals)
    values = [g.value for g in groups]
    gap_pp = round((max(values) - min(values)) * 100, 1)

    f = Finding(
        id=store.stable_id(measure, "by", segment),
        kind="proportion_by_segment",
        metric="percent",
        question_id=measure,
        question_text=_qtext(dic, measure),
        base_definition=f"Respondents answering '{_qtext(dic, measure)}', split by {seg_label}",
        groups=groups,
        overall_n=int(sum(totals)),
        overall_value=float(sum(counts) / sum(totals)),
        test=Test(name=res.name, statistic=res.statistic, p_raw=res.p_value,
                  effect_name=res.effect_name, effect_value=res.effect_value,
                  effect_reading=st.effect_reading(res.effect_name, res.effect_value),
                  note=res.note),
        gap_pp=gap_pp,
        flags=sorted(set(flags)),
        tags=["segment", seg_label, measure],
        provenance={"code": "cscg.analyze.proportion_by_segment",
                    "segment_column": segment, "measure_column": measure, **run_meta},
    )
    return store.add(f)


def mean_by_segment(store: FindingStore, df: pd.DataFrame, dic, measure: str,
                    segment: str, seg_label: str, order: list[str] | None,
                    run_meta: dict, labels: dict | None = None) -> Finding | None:
    entry = _entry(dic, measure)
    vals = _numeric(df[measure])
    if vals.notna().sum() < 20:
        return None
    ordinal = entry.get("inferred_type") == "ordinal"

    levels = order or sorted(df[segment].dropna().astype(str).unique().tolist())
    groups, arrays, flags = [], [], []
    for lv in levels:
        mask = (df[segment].astype(str) == str(lv)) & vals.notna()
        n = int(mask.sum())
        if n == 0:
            continue
        directional, suppressed, gf = _group_flags(n)
        flags += [f"{f}:{lv}" for f in gf]
        if suppressed:
            continue
        arr = vals[mask].to_numpy()
        groups.append(Group(label=_display(lv, labels), n=n, value=float(np.mean(arr)),
                            directional_only=directional))
        arrays.append(arr)

    if len(groups) < 2:
        return None

    res = st.compare_ordinal(arrays) if ordinal else st.compare_means(arrays)
    f = Finding(
        id=store.stable_id(measure, "by", segment),
        kind="mean_by_segment",
        metric="mean",
        question_id=measure,
        question_text=_qtext(dic, measure),
        base_definition=f"Respondents answering '{_qtext(dic, measure)}', split by {seg_label}",
        groups=groups,
        overall_n=int(vals.notna().sum()),
        overall_value=float(vals.mean()),
        test=Test(name=res.name, statistic=res.statistic, p_raw=res.p_value,
                  effect_name=res.effect_name, effect_value=res.effect_value,
                  effect_reading=st.effect_reading(res.effect_name, res.effect_value),
                  note=res.note),
        gap_pp=None,
        flags=sorted(set(flags)),
        caveats=["Ordinal scale: the mean is a summary, not an interval quantity."] if ordinal else [],
        tags=["segment", seg_label, measure],
        provenance={"code": "cscg.analyze.mean_by_segment",
                    "segment_column": segment, "measure_column": measure, **run_meta},
    )
    return store.add(f)


def composition(store: FindingStore, df: pd.DataFrame, dic, column: str,
                run_meta: dict, labels: dict | None = None) -> Finding | None:
    """Who is in the sample. Always computed - this is the 'how to read' slide."""
    s = df[column].dropna().astype(str)
    if s.empty:
        return None
    vc = s.value_counts()
    n = int(s.size)
    groups = []
    for lv, k in vc.items():
        directional, suppressed, _ = _group_flags(int(k))
        groups.append(Group(label=_display(lv, labels), n=int(k), value=float(k / n),
                            count=int(k), directional_only=directional,
                            suppressed=suppressed))
    f = Finding(
        id=store.stable_id("comp", column),
        kind="composition",
        metric="percent",
        question_id=column,
        question_text=_qtext(dic, column),
        base_definition=f"All analysed respondents answering {_qtext(dic, column)}",
        groups=groups,
        overall_n=n,
        overall_value=None,
        tags=["composition", column],
        provenance={"code": "cscg.analyze.composition", "column": column, **run_meta},
    )
    return store.add(f)


def distribution(store: FindingStore, df: pd.DataFrame, dic, column: str,
                 run_meta: dict) -> Finding | None:
    """Full distribution of an ordinal item - the input to a stacked Likert chart."""
    entry = _entry(dic, column)
    s = df[column].dropna()
    if s.empty or entry.get("inferred_type") != "ordinal":
        return None
    vc = s.astype(str).value_counts()
    # keep natural scale order when the values are numeric
    try:
        order = sorted(vc.index, key=lambda x: float(x))
    except (TypeError, ValueError):
        order = list(vc.index)
    n = int(s.size)
    groups = [Group(label=str(lv), n=int(vc[lv]), value=float(vc[lv] / n), count=int(vc[lv]))
              for lv in order]
    pos = _positive_mask(df[column], entry)
    overall = float(pos[df[column].notna()].mean()) if pos is not None else None
    f = Finding(
        id=store.stable_id("dist", column),
        kind="distribution",
        metric="percent",
        question_id=column,
        question_text=_qtext(dic, column),
        base_definition=f"Respondents answering '{_qtext(dic, column)}'",
        groups=groups,
        overall_n=n,
        overall_value=overall,
        caveats=["`overall_value` is the top-box share, defined in analysis_rules."]
                if overall is not None else [],
        tags=["distribution", column],
        provenance={"code": "cscg.analyze.distribution", "column": column, **run_meta},
    )
    return store.add(f)


def ranked_items(store: FindingStore, df: pd.DataFrame, dic, columns: list[str],
                 label: str, base_definition: str, run_meta: dict) -> Finding | None:
    """A battery of binary 'select all that apply' items, ranked. The barriers chart."""
    groups = []
    bases = []
    for col in columns:
        entry = _entry(dic, col)
        pos = _positive_mask(df[col], entry)
        if pos is None:
            continue
        base = int(df[col].notna().sum())
        if base == 0:
            continue
        k = int(pos[df[col].notna()].sum())
        bases.append(base)
        groups.append(Group(label=_qtext(dic, col), n=base, value=k / base, count=k))
    if len(groups) < 2:
        return None
    groups.sort(key=lambda g: g.value, reverse=True)
    f = Finding(
        id=store.stable_id("items", label),
        kind="ranked_items",
        metric="percent",
        question_id=label,
        question_text=label,
        base_definition=base_definition,
        groups=groups,
        overall_n=int(max(bases)),
        tags=["ranked", label],
        provenance={"code": "cscg.analyze.ranked_items", "columns": columns, **run_meta},
    )
    return store.add(f)


def correlation(store: FindingStore, df: pd.DataFrame, dic, x: str, y: str,
                run_meta: dict, method: str = "pearson") -> Finding | None:
    xs, ys = _numeric(df[x]), _numeric(df[y])
    res = st.correlate(xs.to_numpy(), ys.to_numpy(), method)
    if res.p_value is None:
        return None
    n = int((xs.notna() & ys.notna()).sum())
    f = Finding(
        id=store.stable_id(x, "vs", y),
        kind="correlation",
        metric="correlation",
        question_id=f"{x}~{y}",
        question_text=f"{_qtext(dic, x)} vs {_qtext(dic, y)}",
        base_definition=f"Respondents with both values present",
        groups=[],
        overall_n=n,
        overall_value=float(res.statistic),
        test=Test(name=res.name, statistic=res.statistic, p_raw=res.p_value,
                  effect_name=res.effect_name, effect_value=res.effect_value,
                  effect_reading=st.effect_reading(res.effect_name, res.effect_value)),
        caveats=["Correlation only. Not evidence that one causes the other."],
        tags=["correlation", x, y],
        provenance={"code": "cscg.analyze.correlation", "x": x, "y": y, **run_meta},
    )
    return store.add(f)


def conditioned_proportion(store: FindingStore, df: pd.DataFrame, dic, measure: str,
                           segment: str, seg_label: str, order: list[str] | None,
                           condition: str, cond_label: str, cond_order: list[str] | None,
                           run_meta: dict, labels: dict | None = None,
                           cond_labels: dict | None = None) -> Finding | None:
    """Re-run a segment gap INSIDE each level of another declared segment.

    `suggest_deeper` marks this required before any segment gap is claimed, and the
    reason is the commonest false finding in this kind of sample: two segments overlap,
    so one gap is really the other gap wearing a different label.

    The finding is deliberately summarised by its WEAKEST stratum - the largest p and
    the smallest gap of any stratum. A conditioned gap is only worth asserting if it
    survives everywhere, so the gate should be set by the place it nearly fails.
    """
    entry = _entry(dic, measure)
    pos = _positive_mask(df[measure], entry)
    if pos is None:
        return None
    valid = df[measure].notna() & df[segment].notna() & df[condition].notna()
    sub = df[valid]
    if sub.empty:
        return None

    levels = order or sorted(sub[segment].dropna().astype(str).unique().tolist())
    strata = cond_order or sorted(sub[condition].dropna().astype(str).unique().tolist())

    groups: list[Group] = []
    strata_stats: list[dict[str, Any]] = []
    flags: list[str] = []
    for c in strata:
        cmask = sub[condition].astype(str) == str(c)
        cname = _display(c, cond_labels)
        counts, totals, cell_values, ok = [], [], [], True
        for lv in levels:
            m = cmask & (sub[segment].astype(str) == str(lv))
            n = int(m.sum())
            if n == 0:
                continue
            k = int(pos[sub.index][m].sum())
            directional, suppressed, gf = _group_flags(n)
            flags += [f"{f}:{cname}/{lv}" for f in gf]
            if suppressed:
                ok = False
                continue
            groups.append(Group(label=f"{cname}: {_display(lv, labels)}", n=n,
                                value=k / n, count=k, directional_only=directional))
            counts.append(k)
            totals.append(n)
            cell_values.append(k / n)
        if not ok or len(counts) < 2:
            continue
        res = st.compare_proportions(counts, totals)
        strata_stats.append({
            "stratum": cname,
            "n": int(sum(totals)),
            "gap_pp": round((max(cell_values) - min(cell_values)) * 100, 1),
            "direction_matches_pooled": bool(
                cell_values.index(max(cell_values)) == 0 or
                cell_values.index(max(cell_values)) == len(cell_values) - 1),
            "p_raw": res.p_value,
            "effect_name": res.effect_name,
            "effect_value": res.effect_value,
            "test": res.name,
        })

    if len(strata_stats) < 2:
        return None

    worst = max(strata_stats, key=lambda s: (s["p_raw"] if s["p_raw"] is not None else 1.0))
    smallest_gap = min(s["gap_pp"] for s in strata_stats)
    same_direction = all(s["direction_matches_pooled"] for s in strata_stats)

    caveats = [
        "Conditioned check: the gap is re-run inside each level of "
        f"{cond_label}. The test and the gap reported are the WEAKEST stratum's, so "
        "this finding is callable only if the gap survives everywhere."
    ]
    caveats += [f"Within {s['stratum']} (n={s['n']}): {s['gap_pp']}pp apart."
                for s in strata_stats]
    if not same_direction:
        caveats.append("The gap does not run the same way in every stratum. Do not "
                       "assert the pooled difference without saying so.")

    f = Finding(
        id=store.stable_id(measure, "by", segment, "in", condition),
        kind="proportion_by_segment",
        metric="percent",
        question_id=measure,
        question_text=_qtext(dic, measure),
        base_definition=(f"Respondents answering '{_qtext(dic, measure)}', split by "
                         f"{seg_label} within each level of {cond_label}"),
        groups=groups,
        overall_n=int(sum(g.n for g in groups)),
        overall_value=(float(sum(g.count or 0 for g in groups) /
                             max(sum(g.n for g in groups), 1))),
        test=Test(name=worst["test"], statistic=None, p_raw=worst["p_raw"],
                  effect_name=worst["effect_name"], effect_value=worst["effect_value"],
                  effect_reading=st.effect_reading(worst["effect_name"],
                                                   worst["effect_value"]),
                  note=f"Weakest stratum: {worst['stratum']}"),
        gap_pp=smallest_gap,
        flags=sorted(set(flags)),
        caveats=caveats,
        tags=["conditioned", seg_label, cond_label, measure],
        provenance={"code": "cscg.analyze.conditioned_proportion",
                    "measure_column": measure, "segment_column": segment,
                    "condition_column": condition, "strata": strata_stats,
                    "gap_survives_in_every_stratum": same_direction, **run_meta},
    )
    return store.add(f)


def rank_associations(store: FindingStore, outcome: str, dic, run_meta: dict,
                      label: str = "", include: list[str] | None = None,
                      display: dict[str, str] | None = None) -> Finding | None:
    """Rank declared correlations against one outcome, strongest first.

    This is the 'what actually moves the outcome' chart. It is derived purely from
    correlation findings already in the store, so it adds no new computation and stays
    traceable - each ranked item keeps the r that produced it.

    `include` restricts the ranking to a declared set of x columns. A ranking whose
    title says "each part of gameday" must not quietly contain the outcome's own
    behavioural correlates; the label and the contents have to agree.
    """
    corrs = [f for f in store if f.kind == "correlation"
             and f.provenance.get("y") == outcome
             and (include is None or f.provenance.get("x") in include)]
    if len(corrs) < 3:
        return None
    groups = []
    for c in sorted(corrs, key=lambda f: -abs(f.overall_value or 0)):
        col = c.provenance["x"]
        # A declared short name wins: full question wording makes an unreadable bar
        # label, and it still travels on the source line where it belongs.
        name = (display or {}).get(col) or _qtext(dic, col)
        # Strip the boilerplate so the bar label reads as the thing itself.
        name = name.replace("Satisfaction with ", "").replace(" (1-7)", "")
        groups.append(Group(label=name[:1].upper() + name[1:], n=c.overall_n,
                            value=abs(float(c.overall_value))))
    f = Finding(
        id=store.stable_id("rank", outcome, label),
        kind="ranked_items",
        metric="correlation",
        question_id=f"assoc_rank:{outcome}",
        question_text=label or f"Association with {_qtext(dic, outcome)}",
        base_definition=f"Respondents with both values present; Pearson r against {outcome}",
        groups=groups,
        overall_n=max(g.n for g in groups),
        caveats=["Correlations, ranked. Not evidence that any of these causes the outcome.",
                 "Ranking is by absolute r; direction is in the underlying findings."],
        tags=["derived", "ranked", "association", outcome],
        provenance={"code": "cscg.analyze.rank_associations", "outcome": outcome,
                    "derived_from": [c.id for c in corrs], **run_meta},
    )
    return store.add(f)


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def _apply_multiple_comparison_correction(store: FindingStore) -> None:
    """BH across the whole family of tests run in this cycle, then set the
    `callable_difference` gate."""
    rules = config.rules()["testing"]
    tested = [f for f in store if f.test and f.test.p_raw is not None]
    adj = st.benjamini_hochberg([f.test.p_raw for f in tested])
    for f, p in zip(tested, adj):
        f.test.p_adj = p
        f.test.adjustment = rules["multiple_comparison_adjustment"]

    call = rules["call_a_difference_when"]
    for f in store:
        if not f.test or f.test.p_adj is None:
            f.callable_difference = False
            continue
        sig = f.test.p_adj < call["adjusted_p_below"]
        order = ["negligible", "small", "moderate", "large"]
        reading = f.test.effect_reading

        if f.metric == "percent":
            big_enough = (f.gap_pp or 0) >= call["min_absolute_gap_pp"]
            too_small_msg = (
                f"Statistically clear but only {f.gap_pp}pp apart - below the "
                f"{call['min_absolute_gap_pp']}pp threshold for calling a difference.")
        else:
            # Means and correlations gate on effect size: a percentage-point threshold
            # does not apply, and with n in the thousands a negligible effect clears
            # p<0.05 easily.
            floor = call["min_effect_reading_for_correlations" if f.metric == "correlation"
                        else "min_effect_reading_for_means"]
            if reading is None or reading == "unclassified":
                big_enough = False
                too_small_msg = "No interpretable effect size, so the difference cannot be called."
            else:
                big_enough = order.index(reading) >= order.index(floor)
                too_small_msg = (
                    f"Statistically clear but the effect is {reading} "
                    f"({f.test.effect_name}={f.test.effect_value:.2f}), below the "
                    f"'{floor}' floor for calling a difference.")

        f.callable_difference = bool(sig and big_enough)
        if sig and not big_enough:
            f.caveats.append(too_small_msg)
        if not sig and f.test.p_raw is not None and f.test.p_raw < 0.05:
            f.caveats.append(
                "Significant before multiple-comparison adjustment, not after. "
                "Treat as a hypothesis, not a finding."
            )


def suggest_deeper(store: FindingStore, project) -> list[dict[str, str]]:
    """Propose further analysis WITH justification. Nothing here runs automatically."""
    out = []
    # Pairs already checked by a declared conditioning_check are not asked for again.
    checked = {(f.provenance.get("measure_column"), f.provenance.get("segment_column"))
               for f in store if "conditioned" in f.tags}
    strong = [f for f in store.callable_findings()
              if f.kind == "proportion_by_segment" and "conditioned" not in f.tags]
    seen = set()
    for f in strong:
        pair = (f.provenance.get("measure_column"), f.provenance.get("segment_column"))
        if pair in checked or pair in seen:
            continue
        seen.add(pair)
        out.append({
            "analysis": f"Check whether the {f.question_id} gap in {f.id} survives "
                        f"conditioning on the other declared segments",
            "justification": "Segment overlap is the most common false finding in this "
                            "kind of sample. If two segments correlate, one gap is the "
                            "other gap.",
            "required_before_claiming": True,
        })
    if len(store.callable_findings()) >= 4:
        out.append({
            "analysis": "Logistic regression of the primary outcome on the declared segments",
            "justification": "Only worth running if several segment gaps overlap AND the "
                            "client needs to know which one dominates. If crosstabs already "
                            "answer the question, skip it.",
            "required_before_claiming": False,
        })
    if (project.cfg.get("data") or {}).get("actuals_file"):
        out.append({
            "analysis": "Compare stated intent / recalled behaviour against the actuals file",
            "justification": "analysis_rules.self_report requires this whenever actuals exist. "
                            "Self-reports inflate in one direction.",
            "required_before_claiming": True,
        })
    return out


def run(project, force: bool = False) -> dict[str, Any]:
    dic = _dic(project)
    clean_path = project.path("data/processed/clean.csv")
    if not clean_path.exists():
        raise SystemExit("Run clean first: no data/processed/clean.csv")
    df = pd.read_csv(clean_path, dtype=object)

    rid = util.run_id(project.slug)
    run_meta = {"run_id": rid, "dataset": str(clean_path), "rows": len(df)}
    store = FindingStore()

    segments = project.cfg.get("segments") or []
    seg_cols = [s["column"] for s in segments if s.get("column") in df.columns]
    measures = [e["column"] for e in dic
                if e["analysis_role"] == "measure" and e["column"] in df.columns]
    batteries = project.cfg.get("item_batteries") or []

    # 1. Sample composition - always, for the 'how to read' slide.
    for s in segments:
        if s.get("column") in df.columns:
            composition(store, df, dic, s["column"], run_meta, s.get("labels"))

    # 2. Distributions of every declared measure.
    for m in measures:
        distribution(store, df, dic, m, run_meta)

    # 3. Declared item batteries, ranked.
    for b in batteries:
        cols = [c for c in b.get("columns", []) if c in df.columns]
        if cols:
            ranked_items(store, df, dic, cols, b.get("label", "Items"),
                         b.get("base_definition", "Respondents answering the battery"),
                         run_meta)

    # 4. Every declared measure by every declared segment. This is the bulk of the
    #    finding set, and it is exactly why BH correction is mandatory below.
    for s in segments:
        col = s.get("column")
        if col not in df.columns:
            continue
        label = s.get("label", col)
        order = s.get("order")
        labels = s.get("labels")
        for m in measures:
            e = _entry(dic, m)
            if _positive_mask(df[m], e) is not None:
                proportion_by_segment(store, df, dic, m, col, label, order, run_meta, labels)
            elif e.get("inferred_type") in ("numeric", "ordinal"):
                mean_by_segment(store, df, dic, m, col, label, order, run_meta, labels)
        for b in batteries:
            for c in b.get("columns", []):
                if c in df.columns:
                    proportion_by_segment(store, df, dic, c, col, label, order, run_meta, labels)

    # 5. Declared correlations only. No fishing.
    for pair in (project.cfg.get("correlations") or []):
        if pair.get("x") in df.columns and pair.get("y") in df.columns:
            correlation(store, df, dic, pair["x"], pair["y"], run_meta,
                        pair.get("method", "pearson"))

    # 6. Derived rankings over the declared correlations (no new computation).
    ranks = project.cfg.get("association_ranks") or []
    if ranks:
        for r in ranks:
            rank_associations(store, r.get("outcome"), dic, run_meta,
                              r.get("label", ""), r.get("include"), r.get("display"))
    else:
        for outcome in {p.get("y") for p in (project.cfg.get("correlations") or [])}:
            if outcome:
                rank_associations(store, outcome, dic, run_meta,
                                  project.cfg.get("association_rank_label", ""))

    # 7. Conditioned checks. `suggest_deeper` marks these required before any segment
    #    gap is claimed, so they are declared in project.yaml and run here, not argued.
    seg_by_col = {s.get("column"): s for s in segments}
    for chk in (project.cfg.get("conditioning_checks") or []):
        m, sc, cc = chk.get("measure"), chk.get("segment"), chk.get("condition_on")
        if not all(c in df.columns for c in (m, sc, cc)):
            continue
        sseg, cseg = seg_by_col.get(sc, {}), seg_by_col.get(cc, {})
        conditioned_proportion(
            store, df, dic, m, sc, sseg.get("label", sc), sseg.get("order"),
            cc, cseg.get("label", cc), cseg.get("order"), run_meta,
            sseg.get("labels"), cseg.get("labels"))

    _apply_multiple_comparison_correction(store)

    meta = {
        "run_id": rid,
        "project": project.slug,
        "rows_analysed": len(df),
        "segments_declared": [s.get("label", s.get("column")) for s in segments],
        "measures_analysed": len(measures),
        "tests_run": sum(1 for f in store if f.test and f.test.p_raw is not None),
        "multiple_comparison_adjustment":
            config.rules()["testing"]["multiple_comparison_adjustment"],
        "callable_differences": len(store.callable_findings()),
        "suggested_deeper_analysis": suggest_deeper(store, project),
    }
    store.save(project.path("analysis/findings.json"), meta)
    _write_markdown(project, store, meta)
    return meta


def _write_markdown(project, store: FindingStore, meta: dict) -> None:
    call = config.rules()["testing"]["call_a_difference_when"]
    lines = [
        f"# Exploratory analysis - {project.cfg.get('title', project.slug)}",
        "",
        f"{len(store)} findings computed from {meta['rows_analysed']} analysed rows. "
        f"{meta['tests_run']} statistical tests run, adjusted with "
        f"{meta['multiple_comparison_adjustment']}.",
        "",
        f"**{meta['callable_differences']} differences are callable** - meaning they "
        f"cleared both bars: adjusted p < {call['adjusted_p_below']} *and* at least "
        f"{call['min_absolute_gap_pp']} percentage points apart. Only these may be "
        f"asserted as a difference in a title or the executive summary.",
        "",
        "## Callable differences",
        "",
    ]
    callables = store.callable_findings()
    if callables:
        for f in sorted(callables, key=lambda x: -(x.gap_pp or 0)):
            lines.append(f"- {f.summary_line()}")
    else:
        lines.append("_None. That is itself a finding: report the absence of differences._")

    near = [f for f in store if not f.callable_difference and f.test
            and f.test.p_adj is not None and f.test.p_adj < 0.05]
    lines += ["", "## Statistically clear but too small to call", ""]
    lines += [f"- {f.summary_line()}" for f in near] or ["_None._"]

    lines += ["", "## Sample composition", ""]
    for f in store.by_tag("composition"):
        lines.append(f"- {f.summary_line()}")

    lines += ["", "## Suggested deeper analysis (NOT run automatically)", "",
              "Each needs your approval. Anything marked required must be done before "
              "the related claim goes in the deck.", ""]
    for s in meta["suggested_deeper_analysis"]:
        req = "**REQUIRED**" if s["required_before_claiming"] else "optional"
        lines += [f"- [{req}] {s['analysis']}", f"  - Why: {s['justification']}"]

    lines += ["", "## All findings", ""]
    lines += [f"- {f.summary_line()}" for f in store]
    lines.append("")
    project.path("analysis/findings.md").write_text("\n".join(lines))
