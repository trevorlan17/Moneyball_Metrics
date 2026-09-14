"""Command line interface.

    cscg express <slug> --files ...   FAST PATH: set up, analyse, print the deck brief
    cscg ship <slug>           FAST PATH: lint + review checks + build + ghost deck
    cscg new <slug>            scaffold an engagement
    cscg intake <slug>         inspect every file that arrived and route it
    cscg ingest <slug>         profile raw data, build the data dictionary
    cscg clean <slug>          apply quality screens  -> gate 1
    cscg analyse <slug>        statistics -> findings.json
    cscg qual extract|tally    open-text handling
    cscg declare <slug>        register analyst-supplied facts as citable findings
    cscg insights <slug>       package findings for the strategist agent -> gate 2
    cscg cite <slug> [ids]     print slide-ready, linter-safe numbers for findings
    cscg storyline <slug>      validate a storyline -> gate 3
    cscg build <slug>          render the deck
    cscg qa <slug>             deterministic claim linting -> gate 4
    cscg preview <slug>        render slide PNGs and check for text overflow
    cscg run <slug>            everything that can run without an agent, in order
    cscg status <slug>         where the project is and what is blocking it
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import (analyze, clean, config, deck, declare, express, ingest, intake, preview,
               project as proj, qualitative, util, verify)
from .findings import FindingStore

BOLD, DIM, RED, GRN, YEL, END = "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[0m"


def _say(msg: str, kind: str = "") -> None:
    prefix = {"ok": f"{GRN}OK{END}  ", "warn": f"{YEL}!{END}   ",
              "err": f"{RED}X{END}   ", "": "    "}[kind]
    print(prefix + msg)


def _head(msg: str) -> None:
    print(f"\n{BOLD}{msg}{END}")


# ---------------------------------------------------------------------------

def cmd_express(a):
    r = express.run(a.slug, a.files, question=a.question, client=a.client,
                    audience=a.audience, title=a.title, outcome=a.outcome or None,
                    population=a.population or None, synthetic=a.synthetic)
    print(r["brief"])
    print(f"\n[express] {r['slug']}: {r['findings']} tests, {r['callable']} callable, "
          f"{r['themes']} themes, outcome={r['outcome']} in {r['seconds']}s. "
          f"Brief saved to projects/{r['slug']}/insights/brief.md - do not re-read it.")


def cmd_ship(a):
    """Lint, review checks, build and layout in one call, with compact output."""
    import os
    p = proj.load(a.slug)
    t0 = time.time()
    r = verify.run(p, a.force)
    errs = [x for x in r["issues"] if x["severity"] == "ERROR"]
    warns = [x for x in r["issues"] if x["severity"] == "WARN"]
    where = lambda x: f"s{x['slide']}" if x["slide"] else "deck"
    print(f"SHIP {p.slug}")
    if errs:
        print(f"ERRORS ({len(errs)}) - fix ALL of these in one rewrite, then ship once more:")
        for x in errs:
            extra = f" | {x['detail'][:220]}" if x["detail"] and x["rule"] in (
                "unverified_number", "uncited_numbers", "difference_not_callable", "chart_type") else ""
            print(f"  {where(x)} {x['rule']}: {x['message']}{extra}")
    if warns:
        print(f"WARN ({len(warns)}):")
        for x in warns[:10]:
            print(f"  {where(x)} {x['rule']}: {x['message'][:160]}")
    if errs and not a.force:
        print("NOT BUILT.")
        raise SystemExit(1)
    out = deck.run(p, a.force)
    lay = preview.run(p, Path(out["deck"])) if a.previews else preview.analyse(Path(out["deck"]))
    probs = out["overflows"] + lay["issues"]
    if probs:
        print(f"LAYOUT ({len(probs)}) - cut words:")
        for x in probs[:10]:
            print(f"  s{x['slide']} {x['detail'][:140]}")
    else:
        print("LAYOUT: clean")
    sl = deck.load_storyline(p)
    print("GHOST DECK (titles only - must read as the argument):")
    for i, sp in enumerate(sl.get("slides", []), 1):
        t = sp.get("title") or sp.get("subject") or " / ".join(str(x) for x in sp.get("items", []))
        print(f"  {i:>2} {sp.get('layout', '')[:12]:12s} {str(t).strip()[:150]}")
    for g in ("storyline", "final"):
        if not p.path(proj.GATES[g]["file"]).exists():
            p.write_gate(g, "Written by `cscg ship`. Review the built deck, then set Status: APPROVED.\n")
    print(f"GATES: storyline + final PENDING for human review of the draft")
    print(f"DECK: {os.path.relpath(out['deck'], config.ROOT)}  ({time.time() - t0:.1f}s)")


def cmd_new(a):
    p = proj.create(a.slug, title=a.title or a.slug, client=a.client,
                    question=a.question or "", audience=a.audience or "")
    _head(f"Created {p.root}")
    _say(f"1. Put raw data in {p.path('data/raw')}/", "ok")
    _say(f"2. Fill in {p.path('project.yaml')} - business_question, data.survey_file, segments", "ok")
    _say(f"3. Run: cscg run {p.slug}", "ok")


def cmd_intake(a):
    p = proj.load(a.slug)
    _head(f"Intake - {p.slug}")
    r = intake.run(p, a.force)
    for x in r["results"]:
        kind = {"raw_respondent_data": "ok", "unclear": "warn", "unknown": "warn",
                "unreadable": "err"}.get(x["kind"], "")
        _say(f"{x['file'][:44]:46s} {x['kind']:20s} {x['route'][:46]}", kind)
    unclear = [x for x in r["results"] if x["kind"] in ("unclear", "unknown", "unreadable")]
    if unclear:
        _say(f"{len(unclear)} file(s) need a human to classify before use", "warn")
    _say(f"-> {p.path('analysis/intake.md')}")
    _say("Check the routing. An aggregated table read as respondent data gives "
         "percentages of percentages.", "warn")


def cmd_ingest(a):
    p = proj.load(a.slug)
    _head(f"Ingesting {p.slug}")
    r = ingest.run(p, a.force)
    _say(f"{r['rows']} rows x {r['columns']} columns", "ok")
    for t, cols in sorted(r["columns_by_type"].items()):
        _say(f"{t:14s} {len(cols):3d}  {DIM}{', '.join(cols[:5])}{'...' if len(cols) > 5 else ''}{END}")
    w = r["warnings"]
    for x in w["high_missing_over_20pct"][:5]:
        _say(f"{x['column']}: {x['missing_pct']:.0%} missing", "warn")
    if w["constant_columns"]:
        _say(f"constant columns: {', '.join(w['constant_columns'][:6])}", "warn")
    _say(f"-> {p.path('analysis/data_dictionary.md')}")
    _say("Review question_text and analysis_role before cleaning.", "warn")


def cmd_clean(a):
    p = proj.load(a.slug)
    _head(f"Cleaning {p.slug}")
    r = clean.run(p, a.force)
    _say(f"{r['rows_in']} -> {r['rows_kept']} rows ({r['rows_excluded']} excluded, "
         f"{r['excluded_pct']:.1%})", "ok")
    for name, s in r["screens"].items():
        if s["rows_flagged"]:
            _say(f"{name:16s} {s['rows_flagged']:5d} ({s['pct']:.1%})")
    big = [x for x in r["exclusion_impact"] if abs(x["shift_from_cleaning"]) > 0.1]
    for x in big[:4]:
        _say(f"cleaning moved {x['column']} by {x['shift_from_cleaning']:+.2f} "
             f"- consider disclosing", "warn")
    _say(f"-> {p.path('analysis/cleaning_report.md')}")


def cmd_analyse(a):
    p = proj.load(a.slug)
    _head(f"Analysing {p.slug}")
    if not (p.cfg.get("segments") or []):
        _say("No segments declared in project.yaml. Segment comparisons will be skipped.", "warn")
    r = analyze.run(p, a.force)
    _say(f"{r['tests_run']} tests run, {r['multiple_comparison_adjustment']} adjusted", "ok")
    _say(f"{r['callable_differences']} callable differences "
         f"(passed both significance and the minimum gap)", "ok")
    for s in r["suggested_deeper_analysis"]:
        kind = "err" if s["required_before_claiming"] else ""
        _say(f"{'REQUIRED: ' if s['required_before_claiming'] else 'suggested: '}"
             f"{s['analysis']}", kind)
    body = Path(p.path("analysis/findings.md")).read_text()
    gate = p.write_gate("data", "## Analysis output\n\n" + body)
    _say(f"-> {p.path('analysis/findings.md')}")
    _head("HUMAN GATE 1")
    _say(f"Review {gate} and set 'Status: APPROVED' before building insights.", "warn")


def cmd_qual(a):
    p = proj.load(a.slug)
    if a.step == "extract":
        _head(f"Extracting open text - {p.slug}")
        r = qualitative.extract(p)
        _say(f"{r['comments_extracted']} comments, {r['focus_group_excerpts']} focus-group "
             f"excerpts across {r['focus_group_sessions']} sessions", "ok")
        _say(f"-> {r['file']}")
        _say("Hand this to the qualitative-analyst agent. It saves "
             "analysis/comments_coded.csv.", "warn")
    else:
        _head(f"Tallying themes - {p.slug}")
        store = FindingStore.load(p.path("analysis/findings.json"))
        r = qualitative.tally(p, store)
        store.save(p.path("analysis/findings.json"),
                   {"note": "reloaded and extended with qualitative themes"})
        _say(f"{r['coded_comments']} of {r['comment_base']} comments coded into "
             f"{len(r['themes'])} themes", "ok")
        for t in r["themes"][:6]:
            _say(f"{t['theme']:38s} {t['prevalence']}")
        _say(f"-> {p.path('analysis/themes.md')}")


def cmd_declare(a):
    p = proj.load(a.slug)
    _head(f"Declared facts - {p.slug}")
    r = declare.run(p, a.force)
    _say(f"{r['declared']} analyst-declared facts registered as citable findings", "ok")
    _say("These carry verified:false. The red team must check each against its source.", "warn")
    _say(f"-> {p.path('analysis/declared.md')}")


def cmd_insights(a):
    """Package everything the strategist agent needs, in one file."""
    p = proj.load(a.slug)
    if not a.force:
        p.require_gate("data")
    _head(f"Insight briefing - {p.slug}")
    store = FindingStore.load(p.path("analysis/findings.json"))
    cfg = p.cfg
    parts = [
        f"# Insight briefing: {cfg.get('title', p.slug)}",
        "",
        f"**Client:** {cfg.get('client')}   **Audience:** {cfg.get('audience')}",
        f"**Business question:** {str(cfg.get('business_question', '')).strip()}",
        f"**Decision context:** {str(cfg.get('decision_context', '')).strip()}",
        "",
        "## Prior hypotheses (test these, do not assume them)",
    ]
    parts += [f"- {h}" for h in (cfg.get("hypotheses") or [])] or ["- None recorded."]
    parts += ["", "## Context the data does not say",
              str(cfg.get("context_notes", "")).strip() or "- None recorded.", ""]

    cl = store.callable_findings()

    def strength(f):
        return abs(f.test.effect_value) if f.test and f.test.effect_value is not None else 0.0

    leads = sorted(cl, key=lambda f: -strength(f))[:10]
    parts += ["## Leads - callable findings, strongest effect first", "",
              "Start here. Effect size, not p-value, is the ranking: at this sample size "
              "almost everything is significant.", ""]
    parts += [f"- {f.summary_line()}" for f in leads] or ["_None._"]
    nulls = [f for f in store
             if f.test and f.test.p_adj is not None and not f.callable_difference
             and (f.overall_n or 0) >= 300 and f.test.effect_reading in ("negligible", None)]
    parts += ["", "## Well-powered nulls", "",
              "Large base, no detectable effect. A null on something the client believes "
              "matters is often the most decision-relevant finding in the file - check each "
              "against the hypotheses above.", ""]
    parts += [f"- {f.summary_line()}" for f in nulls[:12]] or ["_None._"]
    parts += ["", "## The bar every candidate insight must clear", "",
              "1. **Tension** - it contradicts a belief, a hypothesis above, or what people "
              "say. \"Everyone agrees X... but Y\" (McKinsey UCA). A restated finding is not "
              "an insight.",
              "2. **Decision** - it names the decision it changes and who makes it.",
              "3. **Mechanism** - a plausible why, labelled as a hypothesis, with the "
              "evidence that would test it.",
              "4. **Falsifier** - the observation that would kill it.",
              "5. **Pillar** - it belongs to one of 3 MECE pillars that organise the deck "
              "(JGR: Rewards / Relationships / Relevance). The pillars become the agenda.",
              ""]
    parts += ["## Callable differences (may be asserted as differences)", ""]
    parts += [f"- {f.summary_line()}" for f in cl] or ["_None._"]
    parts += ["", "## Everything else (descriptive, or not callable as a difference)", ""]
    parts += [f"- {f.summary_line()}" for f in store if f not in cl]

    themes_path = p.path("analysis/themes.md")
    if themes_path.exists():
        parts += ["", "## Qualitative", "", themes_path.read_text()]

    clean_md = p.path("analysis/cleaning_report.md")
    if clean_md.exists():
        parts += ["", "## Sample and cleaning", "", clean_md.read_text()]

    out = p.path("insights/briefing.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts))
    _say(f"{len(store)} findings packaged ({len(cl)} callable)", "ok")
    _say(f"-> {out}")
    _say("Hand to the strategist agent. It writes insights/candidates.yaml.", "warn")


def _slide_ready(f) -> list[str]:
    """How each citable value should be WRITTEN on a slide so the linter accepts it."""
    def fmt(v):
        if f.metric == "percent":
            return f"{v:.0%}"
        if f.metric == "correlation":
            return f"{v:.2f}"
        if f.metric == "count":
            return f"{v:,.0f}"
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    out = []
    for g in f.groups:
        bits = [f"{g.label}: {fmt(g.value)}" if f.metric != "count" else f"{g.label}:",
                f"n={g.n:,}"]
        if g.count is not None:
            bits.append(f"count {g.count:,}")
        if g.directional_only:
            bits.append("† directional")
        out.append("  " + "  ".join(bits))
    if f.overall_value is not None and f.metric != "count":
        out.append(f"  overall: {fmt(f.overall_value)}"
                   + (f"  (n={f.overall_n:,})" if f.overall_n else ""))
    if f.gap_pp is not None:
        out.append(f"  gap: {round(f.gap_pp):.0f} points   (write the integer, not {f.gap_pp})")
    if f.test and f.test.effect_value is not None:
        out.append(f"  {f.test.effect_name}: {f.test.effect_value:.2f} ({f.test.effect_reading})"
                   f"   p-values are never citable - put them in the source line")
    out.append("  CALLABLE - may be written as a difference" if f.callable_difference
               else "  NOT callable - no difference-words (vs, gap, higher than) on a slide citing it")
    return out


def cmd_cite(a):
    p = proj.load(a.slug)
    store = FindingStore.load(p.path("analysis/findings.json"))
    ids = list(a.ids or [])
    if a.grep:
        needle = a.grep.lower()
        ids += [f.id for f in store if needle in f.id.lower() or needle in f.question_text.lower()]
    if not ids:
        raise SystemExit("Give finding ids, or --grep <text>.")
    for fid in dict.fromkeys(ids):
        f = store.get(fid)
        if f is None:
            _say(f"{fid}: no such finding", "err")
            continue
        _head(f"{f.id}  -  {f.question_text}")
        _say(f"{f.kind} | {f.base_definition}")
        for line in _slide_ready(f):
            print(line)


def cmd_storyline(a):
    p = proj.load(a.slug)
    path = p.path("storyline/storyline.yaml")
    if not path.exists():
        raise SystemExit(f"No storyline at {path}. Run the storyteller agent first.")
    _head(f"Validating storyline - {p.slug}")
    r = verify.run(p, a.force)
    c = r["counts"]
    _say(f"{r['slides_checked']} slides, {c['ERROR']} errors, {c['WARN']} warnings",
         "ok" if r["passed"] else "err")
    for x in r["issues"][:15]:
        _say(f"[{x['severity']}] slide {x['slide']} {x['rule']}: {x['message']}",
             "err" if x["severity"] == "ERROR" else "warn")
    if r["passed"]:
        gate = p.write_gate("storyline", Path(p.path("qa/lint_report.md")).read_text())
        _head("HUMAN GATE 3")
        _say(f"Review {gate} and approve before building.", "warn")


def cmd_build(a):
    p = proj.load(a.slug)
    _head(f"Building deck - {p.slug}")
    t0 = time.time()
    r = verify.run(p, a.force)
    if not r["passed"] and not a.force:
        _say(f"{r['counts']['ERROR']} errors block the build. See "
             f"{p.path('qa/lint_report.md')}", "err")
        raise SystemExit(1)
    for x in r["issues"]:
        if x["severity"] == "WARN":
            _say(f"[WARN] {'slide %d' % x['slide'] if x['slide'] else 'deck'} {x['rule']}: "
                 f"{x['message'][:110]}", "warn")
    out = deck.run(p, a.force)
    _say(f"{out['slides']} slides -> {out['deck']}  ({out['theme']} theme, "
         f"client logo: {'yes' if out['client_logo'] else 'none - name shown'})", "ok")
    if a.no_preview:
        lay = preview.analyse(Path(out["deck"]))
    else:
        lay = preview.run(p, Path(out["deck"]))
    problems = out["overflows"] + lay["issues"]
    if problems:
        _say(f"{len(problems)} layout problems - cut words, do not shrink type:", "warn")
        for x in problems[:12]:
            _say(f"slide {x['slide']}: {x['kind']} - {x['detail'][:100]}", "warn")
    else:
        _say("layout clean: nothing overflows, overlaps or runs off the slide", "ok")
    if not a.no_preview:
        _say(f"previews -> {p.path('decks/preview')}/")
    _say(f"build took {time.time() - t0:.1f}s")


def cmd_qa(a):
    p = proj.load(a.slug)
    _head(f"QA - {p.slug}")
    r = verify.run(p, a.force)
    c = r["counts"]
    _say(f"{c['ERROR']} errors, {c['WARN']} warnings, {c['INFO']} notes",
         "ok" if r["passed"] else "err")
    for x in r["issues"]:
        sev = x["severity"]
        _say(f"[{sev}] {'slide %d' % x['slide'] if x['slide'] else 'deck'} "
             f"{x['rule']}: {x['message']}",
             "err" if sev == "ERROR" else ("warn" if sev == "WARN" else ""))
    _say(f"-> {p.path('qa/lint_report.md')}")
    _say("Deterministic checks only. Run the qa-redteam agent for the judgement pass.", "warn")
    if r["passed"]:
        p.write_gate("final", Path(p.path("qa/lint_report.md")).read_text())


def cmd_preview(a):
    p = proj.load(a.slug)
    _head(f"Preview - {p.slug}")
    r = preview.run(p)
    _say(f"{r['slides']} slides rendered -> {p.path('decks/preview')}/", "ok")
    for x in r["issues"]:
        _say(f"slide {x['slide']}: {x['kind']} - {x['detail'][:95]}", "warn")
    if not r["issues"]:
        _say("no layout problems", "ok")


def cmd_status(a):
    p = proj.load(a.slug)
    _head(f"{p.cfg.get('title', p.slug)}")
    checks = [
        ("raw data", any(x.is_file() and x.name != ".gitkeep"
                         for x in p.path("data/raw").glob("*"))),
        ("data dictionary", p.path("analysis/data_dictionary.json").exists()),
        ("cleaned data", p.path("data/processed/clean.csv").exists()),
        ("findings", p.path("analysis/findings.json").exists()),
        ("themes coded", p.path("analysis/comments_coded.csv").exists()),
        ("insight briefing", p.path("insights/briefing.md").exists()),
        ("candidate insights", p.path("insights/candidates.yaml").exists()),
        ("storyline", p.path("storyline/storyline.yaml").exists()),
        ("deck", any(p.path("decks").glob("*.pptx"))),
    ]
    for name, done in checks:
        _say(f"{'[x]' if done else '[ ]'} {name}", "ok" if done else "")
    _head("Gates")
    for name in proj.GATES:
        ok, msg = p.gate_status(name)
        _say(msg, "ok" if ok else "warn")


def cmd_run(a):
    """Every deterministic stage, in order, stopping at the first gate."""
    p = proj.load(a.slug)
    _head(f"Pipeline: {p.cfg.get('title', p.slug)}")
    for fn, name in [(cmd_ingest, "ingest"), (cmd_clean, "clean"), (cmd_analyse, "analyse")]:
        fn(a)
    try:
        qualitative.extract(p)
        _say("open text extracted -> analysis/comments_to_code.csv", "ok")
    except SystemExit as e:
        _say(str(e), "warn")
    _head("Stopped at HUMAN GATE 1")
    print(f"""
    Next:
      1. Read {p.path('analysis/cleaning_report.md')} and {p.path('analysis/findings.md')}
      2. Approve {p.path('reviews/gate1_data.md')}
      3. Code the open text with the qualitative-analyst agent, then: cscg qual tally {p.slug}
      4. cscg insights {p.slug}   -> hand insights/briefing.md to the strategist agent
    """)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cscg", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        s = sub.add_parser(name, **kw)
        s.add_argument("slug")
        s.add_argument("--force", action="store_true",
                       help="proceed past an unapproved gate or a failing lint")
        s.set_defaults(fn=fn)
        return s

    e = sub.add_parser("express", help="fast path: files -> analysis -> deck brief")
    e.add_argument("slug")
    e.add_argument("--files", nargs="+", default=[])
    e.add_argument("--question", default="")
    e.add_argument("--client", default="UNC Athletics")
    e.add_argument("--audience", default="")
    e.add_argument("--title", default="")
    e.add_argument("--outcome", default="", help="binary outcome column, if auto-detect is wrong")
    e.add_argument("--population", default="", help="e.g. 'students' -> 'Respondents, not all students.'")
    e.add_argument("--synthetic", action="store_true")
    e.add_argument("--force", action="store_true")
    e.set_defaults(fn=cmd_express)
    sh = sub.add_parser("ship", help="fast path: lint + review + build + ghost deck")
    sh.add_argument("slug")
    sh.add_argument("--previews", action="store_true", help="also render PNG previews (slower; only if asked)")
    sh.add_argument("--force", action="store_true")
    sh.set_defaults(fn=cmd_ship)

    n = sub.add_parser("new")
    n.add_argument("slug")
    n.add_argument("--title", default="")
    n.add_argument("--client", default="UNC Athletics")
    n.add_argument("--question", default="")
    n.add_argument("--audience", default="")
    n.add_argument("--force", action="store_true")
    n.set_defaults(fn=cmd_new)

    add("intake", cmd_intake)
    add("ingest", cmd_ingest)
    add("clean", cmd_clean)
    add("analyse", cmd_analyse)
    add("analyze", cmd_analyse)
    q = sub.add_parser("qual", help="extract open text, or tally coded themes")
    q.add_argument("step", choices=["extract", "tally"])
    q.add_argument("slug")
    q.add_argument("--force", action="store_true")
    q.set_defaults(fn=cmd_qual)
    add("declare", cmd_declare)
    add("insights", cmd_insights)
    c = sub.add_parser("cite", help="slide-ready numbers for findings")
    c.add_argument("slug")
    c.add_argument("ids", nargs="*")
    c.add_argument("--grep", default="")
    c.add_argument("--force", action="store_true")
    c.set_defaults(fn=cmd_cite)
    add("storyline", cmd_storyline)
    b = add("build", cmd_build)
    b.add_argument("--no-preview", action="store_true",
                   help="skip PNG previews (layout is still checked) - for fast iteration")
    add("qa", cmd_qa)
    add("preview", cmd_preview)
    add("status", cmd_status)
    add("run", cmd_run)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
