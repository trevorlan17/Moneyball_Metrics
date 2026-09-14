"""Deterministic QA: the claim linter.

This runs before any human or agent review, and it is the reason the system can
promise that slides do not contain invented numbers.

For every slide it:
  1. extracts every number that appears in the slide's text,
  2. resolves the findings the slide cites,
  3. fails if a number matches no citable value in those findings.

It also enforces the structural rules from config: every slide sourced, every evidence
slide carrying a 'so what', no causal verbs on correlational findings, no banned
phrases, daggers on small bases, and no difference asserted that the analysis marked
as not callable.

A finding of severity ERROR blocks the build. WARN is surfaced to the reviewer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml

from . import charts as chartlib, config, util
from .findings import Finding, FindingStore

# Numbers the linter should not chase: years, page numbers, ordinals in prose.
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
NUM_RE = re.compile(r"""
    (?P<pct>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*%      # 56%  12.5%  1,200%
  | \bn\s*=\s*(?P<n>\d{1,3}(?:,\d{3})*|\d{1,7})    # n=422  n=1,611
  | (?P<dec>\b\d+\.\d+\b)                          # 2.7, 0.25
  | (?P<int>\b\d{1,3}(?:,\d{3})+\b|\b\d{1,7}\b)      # 1,611  422  or  "5 of 6"
""", re.VERBOSE | re.IGNORECASE)

PCT_TOL = 0.55        # percentage points: slide text is rounded
DEC_TOL = 0.015
INT_TOL = 0.5

SEVERITY_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}


@dataclass
class Issue:
    severity: str
    slide: int
    layout: str
    rule: str
    message: str
    detail: str = ""


# ---------------------------------------------------------------------------
# text collection
# ---------------------------------------------------------------------------

TEXT_KEYS = (
    "title", "subtitle", "kicker", "caption", "chart_caption", "lead",
    "statement", "so_what", "question", "why", "text", "label", "value",
    "name", "prevalence", "head", "sub", "recommendation", "evidence",
    "implication", "client", "subject", "descriptor", "source",
    # `bullets` is a bare list of strings, so its items reach `walk` still carrying
    # the key "bullets". Leaving it out meant the how-to-read slide - the one that
    # states the sample size, the exclusions and the sensitivity of the whole study -
    # was the single slide in the deck whose numbers, banned phrases and causal verbs
    # were never checked at all.
    "bullets",
    # Agenda items are visible text too.
    "items",
)


def slide_text(sp: Any, include_source: bool = False) -> str:
    """Every human-visible string on a slide, flattened."""
    out: list[str] = []

    def walk(node, key=None):
        if isinstance(node, dict):
            # A quote block carries verbatim speech. Numbers inside it belong to the
            # speaker; they are verified against the transcript, not against findings.
            if "text" in node and "attribution" in node:
                # Keep the attribution's words so the language checks still see it,
                # but drop its digits: "Season ticket holders 1-5 years" describes the
                # speaker, it does not claim anything.
                out.append(re.sub(r"\d", " ", str(node.get("attribution", ""))))
                return
            for k, v in node.items():
                if k == "source" and not include_source:
                    continue
                if k in ("cites", "allow_numbers", "chart", "charts", "finding_id",
                         "finding_ids", "layout", "figsize", "type", "highlight",
                         "top_n", "points", "filename", "section", "arrangement"):
                    continue
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif node is not None:
            if key in TEXT_KEYS or key is None:
                out.append(str(node))

    walk(sp)
    return "  ".join(out)


def extract_numbers(text: str) -> list[tuple[str, float, str]]:
    """[(kind, value, raw)] where kind is pct | n | dec | int."""
    scrubbed = YEAR_RE.sub(" ", text)
    found = []
    for m in NUM_RE.finditer(scrubbed):
        def num(g):
            return float(g.replace(",", ""))
        if m.group("pct") is not None:
            found.append(("pct", num(m.group("pct")) / 100.0, m.group(0)))
        elif m.group("n") is not None:
            found.append(("n", num(m.group("n")), m.group(0)))
        elif m.group("dec") is not None:
            found.append(("dec", num(m.group("dec")), m.group(0)))
        elif m.group("int") is not None:
            found.append(("int", num(m.group("int")), m.group(0)))
    return found


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

def _allowed_values(project, store: FindingStore, sp: dict) -> tuple[set[tuple[str, float]], list[Finding]]:
    """Every (kind, value) pair this slide is permitted to state."""
    cites = sp.get("cites") or []
    findings = []
    missing: list[str] = []
    vals: set[tuple[str, float]] = set()
    for fid in cites:
        f = store.get(fid)
        if f is None:
            # A citation that resolves to nothing is worse than no citation: the slide
            # looks sourced and is not. Recorded and reported by check_numbers.
            missing.append(fid)
            continue
        findings.append(f)
        for kind, v in f.citable_values():
            if v is not None:
                vals.add((kind, round(float(v), 6)))
    # Numbers the analyst explicitly whitelisted on the slide (field dates, session
    # counts, instrument facts). These bypass kind checking by design.
    for v in (sp.get("allow_numbers") or []):
        vals.add(("any", round(float(v), 6)))
    # Project-level benchmarks are real, sourced numbers.
    for b in (project.cfg.get("benchmarks") or []):
        if b.get("value") is not None:
            vals.add(("any", round(float(b["value"]), 6)))
    return vals, findings, missing


# Which stored kinds a number written in a given form may legitimately come from.
# This is the rule that keeps a fabricated percentage from matching an effect size.
COMPATIBLE = {
    # "56%" - a proportion, a mean of a variable that is itself a percentage, or a
    # percentage-point gap. Never an effect size or a correlation.
    "pct": {"proportion", "mean", "gap_pp", "any"},
    # "n=422" - a base or a numerator.
    "n": {"count", "any"},
    # A bare integer: a base, a count, or a mean written without decimals.
    "int": {"count", "mean", "gap_pp", "any"},
    # "0.25" - a correlation, an effect size, a mean, or a proportion written as a
    # decimal.
    "dec": {"correlation", "effect", "mean", "proportion", "any"},
}


def _matches(kind: str, value: float, allowed: set[tuple[str, float]]) -> bool:
    ok_kinds = COMPATIBLE[kind]
    for a_kind, a in allowed:
        if a_kind not in ok_kinds:
            continue
        if kind == "pct":
            if a_kind in ("proportion", "any") and abs(a - value) <= PCT_TOL / 100.0:
                return True
            # A mean of a percentage variable (19.86) written as "20%", or a stored
            # percentage-point gap written the same way.
            if a_kind in ("mean", "gap_pp", "any") and abs(a - value * 100) <= PCT_TOL:
                return True
        elif kind in ("n", "int"):
            if abs(a - value) <= INT_TOL:
                return True
            if a_kind in ("proportion", "any") and abs(a * 100 - value) <= PCT_TOL:
                return True
        else:  # dec
            if abs(a - value) <= DEC_TOL:
                return True
            if a_kind in ("proportion", "any") and abs(a * 100 - value) <= PCT_TOL:
                return True
    return False


def check_numbers(project, store, sp, i, issues):
    layout = sp.get("layout", "?")
    if layout in ("title", "section", "agenda"):
        return
    text = slide_text(sp)
    nums = extract_numbers(text)
    if not nums:
        return
    allowed, findings, missing = _allowed_values(project, store, sp)
    if missing:
        issues.append(Issue(
            "ERROR", i, layout, "unknown_finding_id",
            f"Cites finding(s) that do not exist: {', '.join(missing)}.",
            "The analysis was re-run and the IDs moved, or the citation is a typo. "
            "A slide that cites nothing real is unsourced."))
    if not findings and not (sp.get("allow_numbers") or []):
        issues.append(Issue(
            "ERROR", i, layout, "uncited_numbers",
            f"Slide states {len(nums)} number(s) but cites no finding.",
            "Add `cites: [F0xx]`, or `allow_numbers:` for instrument facts."))
        return
    hint = _allowed_hint(findings)
    for kind, value, raw in nums:
        if not _matches(kind, value, allowed):
            issues.append(Issue(
                "ERROR", i, layout, "unverified_number",
                f"'{raw}' does not match any value in the cited findings.",
                f"Citable here: {hint}. Fix the number, cite the finding it comes from, "
                f"or add an instrument fact to allow_numbers."))


def _allowed_hint(findings, limit: int = 14) -> str:
    """The values a slide may state, written the way the linter reads them - so one error
    message is enough to fix the number without another lookup round trip."""
    out = []
    for f in findings:
        for g in f.groups:
            if g.suppressed:
                continue
            if f.metric == "percent":
                out.append(f"{g.value:.0%}")
            elif f.metric == "correlation":
                out.append(f"{g.value:.2f}")
            elif f.metric != "count":
                out.append(f"{g.value:,.2f}".rstrip("0").rstrip("."))
            out.append(f"n={g.n:,}")
            if g.count is not None and f.metric == "count":
                out.append(f"{g.count:,}")
        if f.gap_pp is not None:
            out.append(f"{round(f.gap_pp):.0f} points")
        if f.metric == "correlation" and f.overall_value is not None:
            out.append(f"{abs(f.overall_value):.2f}")
    seen = list(dict.fromkeys(out))
    return ", ".join(seen[:limit]) + (" ..." if len(seen) > limit else "") if seen else "nothing"


JARGON_RE = re.compile(r"(\bp\s*[=<]\s*0?\.|\bBH\b|benjamini|chi-?square|cram[eé]r|pearson|"
                       r"welch|t-test|top-box|top box|straightlin|speeder|cohen'?s)", re.I)
NULL_PHRASE_RE = re.compile(r"(about the same|similar|no clear|nothing separates|no separation|"
                            r"no difference|not statistically|did not clear|does not clear|null|"
                            r"without clearing|not clearing|no significant)", re.I)


def check_review(project, store, sp, i, issues):
    """Mechanical versions of what the four red-team reviewers caught by reading."""
    layout = sp.get("layout", "?")
    if layout in ("title", "agenda", "section"):
        return
    text = slide_text(sp)          # everything except the source line
    m = JARGON_RE.search(text)
    if m:
        issues.append(Issue("WARN", i, layout, "technical_text",
                            f"'{m.group(0)}' outside the source line. Test names and p-values "
                            "belong in `source:`; titles and notes are for the room."))

    specs = _chart_specs(sp)
    title = str(sp.get("title") or "")
    if specs and title:
        drawn: set = set()
        label_text = ""
        for spec in specs:
            for fid in (spec.get("finding_ids") or [spec.get("finding_id")]):
                f = store.get(fid) if fid else None
                if f:
                    drawn |= {(k, round(float(v), 6)) for k, v in f.citable_values()}
                    label_text += " " + " ".join(g.label for g in f.groups)
        # A number that is part of a band's NAME ("Under 4%", "10% or more") is on the chart.
        missing = [raw for k, v, raw in extract_numbers(title)
                   if k in ("pct", "dec") and not _matches(k, v, drawn)
                   and raw.strip() not in label_text]
        if drawn and missing:
            issues.append(Issue("WARN", i, layout, "title_not_on_chart",
                                f"Title states {', '.join(missing)}, which the chart does not "
                                "draw. Chart the finding the title is about, or retitle."))

    _, findings, _ = _allowed_values(project, store, sp)
    if not NULL_PHRASE_RE.search(text):
        for f in findings:
            if f.kind not in ("proportion_by_segment", "mean_by_segment") or f.callable_difference \
                    or not (f.test and f.test.p_adj is not None):
                continue
            vals = {(k, round(float(v), 6)) for k, v in f.citable_values() if k in ("proportion", "mean")}
            hits = sorted({raw for k, v, raw in extract_numbers(text)
                           if k == "pct" and _matches(k, v, vals)})
            if len(hits) >= 2:
                issues.append(Issue("WARN", i, layout, "reads_as_comparison",
                                    f"{f.id} is not a callable difference (adjusted p="
                                    f"{f.test.p_adj:.2f}), but {', '.join(hits[:3])} sit side by "
                                    "side and read as one. Say they are similar, or drop one."))


def check_structure(project, store, sp, i, issues):
    layout = sp.get("layout", "?")
    if layout in ("title", "section"):
        return
    if layout == "agenda":
        items = [str(x) for x in (sp.get("items") or [])]
        if not 3 <= len(items) <= 6:
            issues.append(Issue("ERROR", i, layout, "agenda_length",
                                f"Agenda has {len(items)} items; it takes 3-6."))
        for it in items:
            if len(it.split()) > 4:
                issues.append(Issue("WARN", i, layout, "agenda_item_long",
                                    f"Agenda item '{it}' is {len(it.split())} words. Keep "
                                    "it to 4 or fewer: it becomes a footer tab."))
            if re.search(r"\d", it):
                issues.append(Issue("WARN", i, layout, "agenda_item_number",
                                    f"Agenda item '{it}' carries a number. Agenda items are "
                                    "section names, not findings."))
        return
    if not sp.get("source"):
        issues.append(Issue("ERROR", i, layout, "missing_source",
                            "No source line. No slide ships without one."))
    if not sp.get("title"):
        issues.append(Issue("ERROR", i, layout, "missing_title", "No action title."))
    else:
        title = sp["title"]
        if title.isupper():
            issues.append(Issue("WARN", i, layout, "title_case",
                                "Action titles are sentence case; kickers are the caps."))
        if len(title) > 150:
            issues.append(Issue("WARN", i, layout, "title_length",
                                f"Title is {len(title)} chars; it will crowd the zone."))
        # A topic title is a title with no verb and no number.
        if not re.search(r"\d", title) and layout == "chart_with_notes":
            issues.append(Issue("WARN", i, layout, "topic_title",
                                "Evidence-slide titles should carry the number that "
                                "makes the point."))
    if layout == "chart_with_notes":
        notes = sp.get("notes") or []
        if not 2 <= len(notes) <= 3:
            issues.append(Issue("WARN", i, layout, "note_count",
                                f"{len(notes)} annotation boxes; the layout takes 2-3."))
        vocab = set(config.style()["annotation_vocabulary"])
        for note in notes:
            lbl = (note.get("label") or "").upper()
            if lbl and lbl not in vocab and not any(v.split()[0] in lbl for v in vocab):
                issues.append(Issue("INFO", i, layout, "annotation_vocabulary",
                                    f"Label '{lbl}' is outside the house vocabulary.",
                                    f"Known: {', '.join(sorted(vocab))}"))
    if layout == "executive_summary":
        for j, f in enumerate(sp.get("findings", [])):
            if not f.get("so_what"):
                issues.append(Issue("ERROR", i, layout, "missing_so_what",
                                    f"Exec-summary item {j + 1} has no 'So what'."))
            elif f.get("so_what", "").strip().lower().startswith(
                    f.get("statement", "")[:18].strip().lower()[:18]):
                issues.append(Issue("WARN", i, layout, "so_what_restates",
                                    f"Item {j + 1}'s 'So what' restates the finding."))
        n = len(sp.get("findings", []))
        if n > 5:
            issues.append(Issue("WARN", i, layout, "too_many_findings",
                                f"{n} findings. More than 5 means it is not prioritised."))
    if layout == "discussion_questions":
        for j, q in enumerate(sp.get("questions", [])):
            if not q.get("why"):
                issues.append(Issue("ERROR", i, layout, "missing_why",
                                    f"Question {j + 1} has no 'Why it matters'."))


NEGATED_RE = re.compile(
    r"(\b(not|no|never|rather than|nor|isn't|aren't|without)\s+(an?\s+|the\s+)?$"
    r"|\b(not|no|never|isn't|without)\s+(proof|evidence)\s+(of|that)\s+(\w+\s+){0,4}$)")


def _unnegated(low: str, word: str) -> bool:
    """True if `word` appears at least once NOT preceded by a negation. "These are
    associations, not causes" is exactly the hedge we want written; flagging it cost a
    rebuild on every run."""
    for m in re.finditer(rf"\b{re.escape(word)}\b", low):
        if not NEGATED_RE.search(low[max(0, m.start() - 40):m.start()]):
            return True
    return False


def check_language(project, store, sp, i, issues):
    layout = sp.get("layout", "?")
    text = slide_text(sp)
    low = text.lower()
    for phrase in config.style()["banned_phrases"]:
        if _unnegated(low, phrase):
            issues.append(Issue("WARN", i, layout, "banned_phrase",
                                f"Banned phrase: '{phrase}'.",
                                "See config/presentation_style.yaml: banned_phrases."))

    causal = config.rules()["causal_language"]["requires_experiment_or_behavioural_data"]
    _, findings, _missing = _allowed_values(project, store, sp)
    correlational = any(f.kind in ("correlation", "proportion_by_segment",
                                   "mean_by_segment", "distribution") for f in findings)
    if correlational:
        for verb in causal:
            if _unnegated(low, verb):
                issues.append(Issue(
                    "ERROR", i, layout, "causal_language",
                    f"Causal verb '{verb}' on a correlational finding.",
                    "Use 'is associated with' / 'is higher among', or name the "
                    "behavioural data that supports the stronger claim."))

    if re.search(r"\bstatistically significant\b", low):
        tested = [f for f in findings if f.test and f.test.p_adj is not None]
        if not tested:
            issues.append(Issue("ERROR", i, layout, "unsupported_significance",
                                "Claims significance but cites no tested finding."))


def check_evidence_strength(project, store, sp, i, issues):
    """The rule that stops a marginal gap being written as a difference."""
    layout = sp.get("layout", "?")
    if layout in ("title", "section"):
        return
    _, findings, _missing = _allowed_values(project, store, sp)
    text = slide_text(sp).lower()
    asserts_difference = bool(re.search(
        r"\b(vs|versus|compared with|more likely|less likely|higher than|lower than|"
        r"than [a-z]+s|gap|differ|difference)\b", text))

    for f in findings:
        if f.kind not in ("proportion_by_segment", "mean_by_segment"):
            continue
        if asserts_difference and not f.callable_difference:
            reason = "no test result" if not (f.test and f.test.p_adj is not None) else (
                f"adjusted p={f.test.p_adj:.3f}"
                + (f", gap {f.gap_pp}pp" if f.gap_pp is not None else ""))
            issues.append(Issue(
                "ERROR", i, layout, "difference_not_callable",
                f"Slide asserts a difference on {f.id}, which the analysis did not "
                f"mark callable ({reason}).",
                "Either reframe as 'similar' / 'no clear difference', or remove it. "
                "config/analysis_rules.yaml: testing.call_a_difference_when."))
        small = [g for g in f.groups if g.directional_only]
        if small:
            mark = config.rules()["bases"]["small_group_marker"]
            if mark not in slide_text(sp, include_source=True):
                issues.append(Issue(
                    "WARN", i, layout, "small_base_unmarked",
                    f"{f.id} includes group(s) under 30 "
                    f"({', '.join(g.label for g in small)}) with no '{mark}' marker."))
        for cav in f.caveats:
            issues.append(Issue("INFO", i, layout, "finding_caveat",
                                f"{f.id}: {cav}"))

    # Declared facts are citable but not computed. Surface them every time, so nobody
    # mistakes "the linter passed" for "this number was verified".
    declared = [f for f in findings if f.kind == "declared"]
    if declared:
        issues.append(Issue(
            "WARN", i, layout, "unverified_numbers",
            f"Rests on {len(declared)} analyst-declared number(s): "
            f"{', '.join(f.id for f in declared)}.",
            "Not computed by this pipeline. Check each against the source recorded on "
            "the finding before this goes to a client."))


def check_deck_level(project, store, storyline, issues):
    slides = storyline.get("slides", [])
    layouts = [s.get("layout") for s in slides]
    if "executive_summary" not in layouts:
        issues.append(Issue("ERROR", 0, "deck", "missing_executive_summary",
                            "No executive summary. CSCG decks answer first."))
    if "how_to_read" not in layouts:
        issues.append(Issue("ERROR", 0, "deck", "missing_how_to_read",
                            "No 'how to read these results' slide. Sample composition "
                            "and limitations must precede the findings."))
    if layouts and layouts[0] != "title":
        issues.append(Issue("WARN", 0, "deck", "no_title_slide", "Deck does not open with a title slide."))
    if len(layouts) < 2 or layouts[1] != "agenda":
        issues.append(Issue("ERROR", 0, "deck", "agenda_not_second",
                            "Slide 2 must be the agenda (3-6 short section names)."))
    if "executive_summary" in layouts and layouts.index("executive_summary") != 2:
        issues.append(Issue("WARN", 0, "deck", "exec_summary_position",
                            f"Executive summary is slide {layouts.index('executive_summary') + 1}; "
                            "it belongs straight after the agenda (slide 3)."))
    agenda = next((s for s in slides if s.get("layout") == "agenda"), None)
    if agenda:
        items = [str(x).strip().lower() for x in agenda.get("items") or []]
        used = {str(s.get("section") or "").strip().lower() for s in slides}
        used |= {str(s.get("title") or "").strip().lower() for s in slides if s.get("layout") == "section"}
        for it in items:
            if it not in used:
                issues.append(Issue("WARN", 0, "deck", "agenda_section_unused",
                                    f"Agenda item '{it}' names no slide's `section:`, so its "
                                    "footer tab never lights up."))
        for n, s in enumerate(slides, 1):
            sec = str(s.get("section") or "").strip().lower()
            if sec and sec not in items:
                issues.append(Issue("WARN", n, s.get("layout", "?"), "section_not_in_agenda",
                                    f"Section '{s.get('section')}' is not an agenda item."))

    # Variety: a deck that answers every question with the same chart usually chose the
    # chart before the claim. Warn, never block - sometimes every claim is a comparison.
    fam = config.charts().get("variety", {})
    types = [c.get("type", "grouped_bar") for s in slides for c in _chart_specs(s)]
    if len(types) >= fam.get("min_charts_for_variety_check", 3):
        family_of = {t: f for f, ts in fam.get("families", {}).items() for t in ts}
        families = {family_of.get(t, t) for t in types}
        if len(families) == 1:
            issues.append(Issue(
                "WARN", 0, "deck", "chart_monotony",
                f"All {len(types)} charts are {next(iter(families))} charts. Check whether a "
                "part-to-whole claim wants a donut, an ordered band a line, or a multi-attribute "
                "comparison a table (config/chart_rules.yaml: selection)."))

    # Does every exec-summary claim actually appear later in the deck?
    exec_slides = [s for s in slides if s.get("layout") == "executive_summary"]
    body_cites = {c for s in slides if s.get("layout") not in ("executive_summary", "title")
                  for c in (s.get("cites") or [])}
    for es in exec_slides:
        for j, f in enumerate(es.get("findings", [])):
            cites = set(f.get("cites") or es.get("cites") or [])
            if cites and not (cites & body_cites):
                issues.append(Issue(
                    "WARN", 0, "deck", "unsupported_summary_item",
                    f"Exec-summary item {j + 1} cites {sorted(cites)}, which no body "
                    f"slide develops."))

    # Non-random sample language.
    if project.cfg.get("nonrandom_sample", True):
        # The phrase names the population, which differs by engagement ("all students",
        # "all fans"). Projects override it; the stem is what must appear.
        phrase = project.cfg.get("respondent_language") \
            or config.rules()["bases"]["respondent_language"]
        stem = "respondents, not all"
        found = any(stem in slide_text(s, include_source=True).lower() for s in slides)
        if not found:
            issues.append(Issue(
                "WARN", 0, "deck", "missing_respondent_language",
                f"Sample is non-random but '{phrase}' appears nowhere."))

    # Repeated numbers with different bases across slides.
    seen: dict[float, list[int]] = {}
    for i, s in enumerate(slides, 1):
        for kind, v, raw in extract_numbers(slide_text(s)):
            if kind == "pct":
                seen.setdefault(round(v, 3), []).append(i)
    for v, pages in seen.items():
        if len(pages) > 3:
            issues.append(Issue("INFO", 0, "deck", "repeated_number",
                                f"{v:.0%} appears on slides {pages}. Check the bases match."))


def _chart_specs(sp) -> list[dict]:
    specs = []
    if isinstance(sp.get("chart"), dict):
        specs.append(sp["chart"])
    for c in sp.get("charts") or []:
        if isinstance(c, dict):
            specs.append(c)
    return specs


def check_charts(project, store, sp, i, issues):
    """Is each chart type honest for the finding it draws? A donut of separately-based
    groups, or of multi-select answers, misstates the data however clean it looks."""
    layout = sp.get("layout", "?")
    for spec in _chart_specs(sp):
        for sev, msg in chartlib.validate(spec, store):
            issues.append(Issue(sev, i, layout, "chart_type", msg))


def check_density(project, store, sp, i, issues):
    """Word counts that predict an unreadable slide before it is rendered."""
    layout = sp.get("layout", "?")
    if layout in ("title", "agenda", "section"):
        return
    words = len(slide_text(sp).split())
    limit = 150 if layout in ("how_to_read", "recommendation_table", "quotes_themes") else 120
    if words > limit:
        issues.append(Issue("WARN", i, layout, "dense_slide",
                            f"{words} words on the slide (limit ~{limit}). Cut before the "
                            "build shrinks it or reports an overflow."))
    src = str(sp.get("source") or "")
    if len(src.split()) > 55:
        issues.append(Issue("WARN", i, layout, "long_source",
                            f"Source line is {len(src.split())} words; it will not fit two "
                            "lines. Move detail to the appendix or the gate memo."))


CHECKS = [check_numbers, check_structure, check_language, check_evidence_strength,
          check_charts, check_density, check_review]


def run(project, force: bool = False) -> dict[str, Any]:
    store = FindingStore.load(project.path("analysis/findings.json"))
    path = project.path("storyline/storyline.yaml")
    if not path.exists():
        raise SystemExit(f"No storyline at {path}.")
    with path.open() as fh:
        storyline = yaml.safe_load(fh)

    issues: list[Issue] = []
    for i, sp in enumerate(storyline.get("slides", []), start=1):
        for check in CHECKS:
            check(project, store, sp, i, issues)
    check_deck_level(project, store, storyline, issues)
    issues.sort(key=lambda x: (SEVERITY_ORDER[x.severity], x.slide))

    counts = {s: sum(1 for x in issues if x.severity == s) for s in ("ERROR", "WARN", "INFO")}
    result = {
        "project": project.slug,
        "slides_checked": len(storyline.get("slides", [])),
        "findings_available": len(store),
        "counts": counts,
        "passed": counts["ERROR"] == 0,
        "issues": [asdict(x) for x in issues],
    }
    util.write_json(project.path("qa/lint_report.json"), result)
    _write_markdown(project, result)
    return result


def _write_markdown(project, r: dict[str, Any]) -> None:
    c = r["counts"]
    lines = [
        f"# Deterministic QA - {project.cfg.get('title', project.slug)}",
        "",
        f"{r['slides_checked']} slides checked against {r['findings_available']} findings.",
        "",
        f"**{c['ERROR']} errors, {c['WARN']} warnings, {c['INFO']} notes.** "
        + ("Build allowed." if r["passed"] else "**Build blocked until errors are fixed.**"),
        "",
        "Every number on every slide was matched back to the finding the slide cites. "
        "An unverified number means the deck says something the analysis does not.",
        "",
    ]
    for sev in ("ERROR", "WARN", "INFO"):
        rows = [x for x in r["issues"] if x["severity"] == sev]
        if not rows:
            continue
        lines += [f"## {sev} ({len(rows)})", ""]
        for x in rows:
            where = f"slide {x['slide']}" if x["slide"] else "deck"
            lines.append(f"- **[{x['rule']}]** {where} ({x['layout']}): {x['message']}")
            if x["detail"]:
                lines.append(f"  - {x['detail']}")
        lines.append("")
    project.path("qa/lint_report.md").write_text("\n".join(lines))
