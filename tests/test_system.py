"""Regression tests for the guarantees the system makes.

These exist because the guarantees are the product. If the claim linter stops catching
fabricated numbers, the system is worse than useless - it launders invention through a
process that looks rigorous.

Run: .venv/bin/python -m pytest tests/ -q       (or: .venv/bin/python tests/test_system.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from cscg import config, stats as st, textfit as tf, verify
from cscg.findings import Finding, FindingStore, Group, Test

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


# ---------------------------------------------------------------------------
def test_bh_correction():
    """BH must be monotone, bounded, and must not shrink p-values."""
    ps = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.5, 0.9]
    adj = st.benjamini_hochberg(ps)
    check("BH returns one value per input", len(adj) == len(ps))
    check("BH never decreases a p-value", all(a >= p - 1e-12 for a, p in zip(adj, ps)))
    check("BH stays in [0,1]", all(0 <= a <= 1 for a in adj))
    check("BH is monotone in the input order",
          all(adj[i] <= adj[i + 1] + 1e-12 for i in range(len(adj) - 1)))
    check("BH preserves None for tests that did not run",
          st.benjamini_hochberg([0.01, None, 0.5])[1] is None)
    # A family of pure noise should almost never survive correction.
    rng = np.random.default_rng(0)
    noise = list(rng.uniform(size=40))
    check("BH kills a family of null p-values",
          sum(1 for a in st.benjamini_hochberg(noise) if a < 0.05) == 0)


def test_degenerate_tables():
    """No-variation and empty-group tables must return no test, not crash."""
    check("no variation -> no test",
          st.compare_proportions([0, 0], [100, 100]).p_value is None)
    check("all-success -> no test",
          st.compare_proportions([50, 50], [50, 50]).p_value is None)
    check("empty group -> no test",
          st.compare_proportions([5, 0], [10, 0]).p_value is None)
    r = st.compare_proportions([30, 60], [100, 100])
    check("a real difference does return a test", r.p_value is not None and r.p_value < 0.01)


def test_effect_sizes_required():
    r = st.compare_proportions([30, 60], [100, 100])
    check("proportion test reports an effect size", r.effect_value is not None)
    check("effect size is classified",
          st.effect_reading(r.effect_name, r.effect_value) in
          ("negligible", "small", "moderate", "large"))
    big = st.compare_means([np.zeros(50), np.ones(50) * 3])
    check("mean test reports Cohen's d", big.effect_name == "cohens_d")


# ---------------------------------------------------------------------------
def _store() -> FindingStore:
    s = FindingStore()
    s.add(Finding(
        id="F001", kind="proportion_by_segment", metric="percent",
        question_id="q1", question_text="Didn't know how to get tickets",
        base_definition="Respondents naming a barrier",
        groups=[Group("Undergraduate", 272, 0.19, 52),
                Group("Graduate/professional", 99, 0.56, 55)],
        overall_n=371, overall_value=0.29, gap_pp=37.0,
        test=Test("chi-square", 42.0, 0.0001, 0.0004, "BH", "cramers_v", 0.14, "small"),
        callable_difference=True))
    s.add(Finding(
        id="F002", kind="correlation", metric="correlation",
        question_id="x~y", question_text="Atmosphere vs renewal",
        base_definition="Complete pairs", groups=[], overall_n=1611,
        overall_value=0.247,
        test=Test("Pearson r", 0.247, 0.0001, 0.0002, "BH", "pearson_r", 0.247, "small"),
        callable_difference=True))
    return s


def _slide(**kw):
    base = {"layout": "chart_with_notes", "kicker": "K",
            "title": "A title with 56% in it.", "cites": ["F001"],
            "source": "Source: test. Respondents, not all students.",
            "notes": [{"label": "SO WHAT", "text": "x"},
                      {"label": "WATCH-OUT", "text": "y"},
                      {"label": "IMPLICATION", "text": "z"}]}
    base.update(kw)
    return base


class _Proj:
    cfg = {"benchmarks": [], "nonrandom_sample": True}


def test_claim_linter_catches_fabrication():
    store, proj = _store(), _Proj()

    issues = []
    verify.check_numbers(proj, store, _slide(title="56% of grad respondents didn't know, vs 19%."), 1, issues)
    check("real numbers pass", not issues, str(issues))

    issues = []
    verify.check_numbers(proj, store, _slide(title="61% of grad respondents didn't know."), 1, issues)
    check("fabricated percentage is caught",
          any(i.rule == "unverified_number" for i in issues))

    issues = []
    verify.check_numbers(proj, store, _slide(title="Based on n=900 respondents."), 1, issues)
    check("fabricated base is caught",
          any(i.rule == "unverified_number" for i in issues))

    # The bug this test exists for: an effect size of 0.14 must not license "14%".
    issues = []
    verify.check_numbers(proj, store, _slide(title="14% of respondents said so."), 1, issues)
    check("a percentage cannot match an effect size of the same magnitude",
          any(i.rule == "unverified_number" for i in issues))

    # ...while the correlation itself may legitimately be written as a decimal.
    issues = []
    verify.check_numbers(proj, store,
                         _slide(title="Atmosphere is associated with renewal (r = 0.25).",
                                cites=["F002"]), 1, issues)
    check("a correlation may be cited as a decimal", not issues, str(issues))

    issues = []
    verify.check_numbers(proj, store, _slide(title="Some claim with 42% in it.", cites=[]), 1, issues)
    check("numbers with no citation are caught",
          any(i.rule == "uncited_numbers" for i in issues))

    issues = []
    verify.check_numbers(proj, store,
                         _slide(title="Fielded over 3 days with 2000 invitations.",
                                allow_numbers=[2000, 3]), 1, issues)
    check("allow_numbers whitelists instrument facts", not issues, str(issues))


def test_dangling_citation_is_caught():
    """A citation that resolves to nothing looks sourced and is not."""
    issues = []
    verify.check_numbers(_Proj(), _store(),
                         _slide(title="Some claim with 56% in it.", cites=["F999"]),
                         1, issues)
    check("a citation to a non-existent finding is an ERROR",
          any(i.rule == "unknown_finding_id" and i.severity == "ERROR" for i in issues))


def test_single_digit_claims_are_checked():
    """'raised in 5 of 6 focus groups' is a claim, not decoration."""
    store = _store()
    store.add(Finding(
        id="Q_x", kind="theme_prevalence", metric="count",
        question_id="theme:X", question_text="X", base_definition="6 sessions",
        groups=[Group("X", 6, 0.83, 5)], overall_n=6, overall_value=7.0))
    issues = []
    verify.check_numbers(_Proj(), store,
                         _slide(title="Raised in 5 of 6 focus groups.", cites=["Q_x"]),
                         1, issues)
    check("a true 'N of M' claim passes", not issues, str(issues))

    issues = []
    verify.check_numbers(_Proj(), store,
                         _slide(title="Raised in 4 of 6 focus groups.", cites=["Q_x"]),
                         1, issues)
    check("a false 'N of M' claim is caught",
          any(i.rule == "unverified_number" for i in issues))


def test_theme_prevalence_is_never_a_percentage():
    """analysis_rules forbids expressing a theme share as a survey percentage, so the
    store never offers it as one."""
    store = _store()
    store.add(Finding(
        id="Q_y", kind="theme_prevalence", metric="count",
        question_id="theme:Y", question_text="Y", base_definition="6 sessions",
        groups=[Group("Y", 6, 0.83, 5)], overall_n=6, overall_value=7.0))
    issues = []
    verify.check_numbers(_Proj(), store,
                         _slide(title="83% of focus groups raised it.", cites=["Q_y"]),
                         1, issues)
    check("a theme share cannot be written as a percentage",
          any(i.rule == "unverified_number" for i in issues))


def test_quote_attribution_digits_ignored():
    sp = {"layout": "quotes_themes", "title": "T", "cites": ["F001"], "source": "S",
          "themes": [{"name": "N", "prevalence": "p",
                      "quotes": [{"text": "q", "attribution": "Season ticket holders 1-5 years, focus group"}]}]}
    text = verify.slide_text(sp)
    check("digits in an attribution are not treated as claims",
          not any(k in ("int", "n") for k, _, _ in verify.extract_numbers(text)), text)
    check("attribution words survive for language checks", "focus group" in text)


def test_theme_ids_are_stable():
    """Theme IDs must not move when the tally is re-run, or storyline citations rot."""
    from cscg import util
    check("theme id derives from the theme name",
          "Q_" + util.slugify("Time Commitment")[:28] == "Q_time_commitment")


def test_thousands_separator():
    nums = dict((raw, v) for _, v, raw in verify.extract_numbers("n=1,611 and 1,850 rows"))
    check("1,611 reads as 1611", nums.get("n=1,611") == 1611.0, str(nums))
    check("1,850 reads as 1850", nums.get("1,850") == 1850.0, str(nums))


def test_quotes_are_not_number_checked():
    sp = {"layout": "quotes_themes", "title": "T", "cites": ["F001"], "source": "S",
          "themes": [{"name": "N", "prevalence": "5 of 10 comments",
                      "quotes": [{"text": "They announced a 7:30 kickoff six days out.",
                                  "attribution": "Student, focus group"}]}]}
    text = verify.slide_text(sp)
    check("verbatim quote text is excluded from number checking",
          "7:30" not in text, text)
    check("attribution is still collected", "focus group" in text)


def test_causal_language_blocked():
    issues = []
    verify.check_language(_Proj(), _store(),
                          _slide(title="Atmosphere drives renewal.", cites=["F002"]), 1, issues)
    check("causal verb on a correlation is an ERROR",
          any(i.rule == "causal_language" and i.severity == "ERROR" for i in issues))

    issues = []
    verify.check_language(_Proj(), _store(),
                          _slide(title="Atmosphere is associated with renewal.", cites=["F002"]),
                          1, issues)
    check("associational language passes",
          not any(i.rule == "causal_language" for i in issues))


def test_uncallable_difference_blocked():
    store = _store()
    store["F001"].callable_difference = False
    store["F001"].test.p_adj = 0.31
    issues = []
    verify.check_evidence_strength(_Proj(), store,
                                   _slide(title="Grads knew less than undergrads."), 1, issues)
    check("asserting a non-callable difference is an ERROR",
          any(i.rule == "difference_not_callable" and i.severity == "ERROR" for i in issues))


def test_structural_rules():
    issues = []
    verify.check_structure(_Proj(), _store(), _slide(source=None), 1, issues)
    check("a missing source line is an ERROR",
          any(i.rule == "missing_source" and i.severity == "ERROR" for i in issues))

    issues = []
    verify.check_structure(_Proj(), _store(),
                           {"layout": "executive_summary", "title": "T", "source": "S",
                            "findings": [{"statement": "x", "so_what": ""}]}, 1, issues)
    check("an exec-summary item with no 'So what' is an ERROR",
          any(i.rule == "missing_so_what" for i in issues))


# ---------------------------------------------------------------------------
def test_text_measurement_is_stable():
    """Measurement must not depend on whether a chart has been rendered yet."""
    from cscg import charts
    text = "Kickoff times announced late"
    before = tf.height(text, 15, 3.343, True)
    charts._setup("light")          # mutates matplotlib rcParams
    tf.measure.cache_clear()
    tf._font.cache_clear()
    after = tf.height(text, 15, 3.343, True)
    check("text metrics do not drift with matplotlib rcParams",
          abs(before - after) < 1e-9, f"{before} != {after}")
    check("wrapping is monotone in width",
          len(tf.wrap(text, 15, 1.5, True)) >= len(tf.wrap(text, 15, 6.0, True)))


def test_config_integrity():
    style, rules, charts_cfg = config.style(), config.rules(), config.charts()
    check("every layout has a documented purpose",
          all("purpose" in v for v in style["layouts"].values()))
    check("both themes define every colour token",
          set(style["themes"]["light"]) == set(style["themes"]["dark"]))
    check("the difference-calling rule is configured",
          "min_absolute_gap_pp" in rules["testing"]["call_a_difference_when"])
    check("charts must carry a finding id",
          charts_cfg["traceability"]["require_finding_id"] is True)
    check("small-group threshold is set", rules["bases"]["small_group_threshold"] > 0)


# ---------------------------------------------------------------------------
# September 2026: speed, agenda, chart variety, logos, spacing
# ---------------------------------------------------------------------------

def _mini_store():
    s = FindingStore()
    s.add(Finding(id="F_share", kind="composition", metric="percent", question_id="q_src",
                  question_text="How students get tickets", base_definition="All respondents",
                  groups=[Group("Lottery", 400, 0.60, 240), Group("Email", 400, 0.30, 120),
                          Group("Other", 400, 0.10, 40)], overall_n=400))
    s.add(Finding(id="F_by_level", kind="proportion_by_segment", metric="percent",
                  question_id="q_know", question_text="Knows how to get tickets",
                  base_definition="Respondents naming a barrier",
                  groups=[Group("Undergraduate", 272, 0.81, 220), Group("Graduate", 99, 0.44, 44)],
                  overall_n=371, overall_value=0.71, gap_pp=37.0, callable_difference=True))
    s.add(Finding(id="F_multi", kind="ranked_items", metric="percent", question_id="q_barr",
                  question_text="Barriers (select all)", base_definition="Respondents",
                  groups=[Group("Timing", 300, 0.51, 153), Group("Friends", 300, 0.41, 123),
                          Group("Cost", 300, 0.32, 96)], overall_n=300))
    return s


def test_text_measurement_is_fast():
    """The measurement change is the runtime fix; keep it from regressing."""
    import time
    tf.measure.cache_clear()
    text = " ".join(["Renewal falls from 78% to 50% across how often an account leaves"] * 400)
    t = time.time()
    tf.wrap(text, 11, 4.5)
    elapsed = time.time() - t
    check("wrapping ~5,000 words takes under 0.2s cold", elapsed < 0.2, f"{elapsed:.3f}s")
    w = tf.measure("Crowd atmosphere", 14, False)
    check("measured width is plausible for Arial 14pt", 1.4 < w < 1.9, f"{w:.3f}in")


def test_agenda_rules():
    store = _mini_store()

    class P:
        cfg = {"nonrandom_sample": False}
    slides_bad = {"slides": [{"layout": "title"}, {"layout": "executive_summary", "title": "x",
                                                   "source": "s", "findings": []}]}
    issues = []
    verify.check_deck_level(P(), store, slides_bad, issues)
    check("slide 2 that is not an agenda is an ERROR",
          any(i.rule == "agenda_not_second" and i.severity == "ERROR" for i in issues))

    issues = []
    verify.check_structure(P(), store, {"layout": "agenda",
                                        "items": ["a", "b", "c", "d", "e", "f", "g"]}, 2, issues)
    check("an agenda of 7 items is an ERROR", any(i.rule == "agenda_length" for i in issues))
    issues = []
    verify.check_structure(P(), store, {"layout": "agenda",
                                        "items": ["Who we heard from and why", "Access", "Next"]}, 2, issues)
    check("a long agenda item is flagged", any(i.rule == "agenda_item_long" for i in issues))

    good = {"slides": [{"layout": "title"}, {"layout": "agenda", "items": ["Access", "Lottery", "Next"]},
                       {"layout": "executive_summary", "section": "Access"},
                       {"layout": "chart_with_notes", "section": "Lottery"}]}
    issues = []
    verify.check_deck_level(P(), store, good, issues)
    check("unused agenda item is warned", any(i.rule == "agenda_section_unused" for i in issues))
    check("a correct agenda raises no agenda error",
          not any(i.rule == "agenda_not_second" for i in issues))


def test_share_charts_must_be_parts_of_a_whole():
    from cscg import charts
    store = _mini_store()
    ok = charts.validate({"finding_id": "F_share", "type": "donut"}, store)
    check("a composition summing to 100% may be a donut", not [m for s_, m in ok if s_ == "ERROR"], str(ok))
    bad = charts.validate({"finding_id": "F_by_level", "type": "donut"}, store)
    check("separately-based groups may not be a donut", any(s_ == "ERROR" for s_, _ in bad))
    multi = charts.validate({"finding_id": "F_multi", "type": "pie"}, store)
    check("multi-select answers may not be a pie", any(s_ == "ERROR" for s_, _ in multi))
    line = charts.validate({"finding_id": "F_by_level", "type": "line"}, store)
    check("a two-point line is an ERROR", any(s_ == "ERROR" for s_, _ in line))
    unknown = charts.validate({"finding_id": "F_share", "type": "radar"}, store)
    check("unknown chart types are rejected", any(s_ == "ERROR" for s_, _ in unknown))


def test_chart_monotony_warns():
    store = _mini_store()

    class P:
        cfg = {"nonrandom_sample": False}
    bars = {"slides": [{"layout": "title"}, {"layout": "agenda", "items": ["A", "B", "C"]}] + [
        {"layout": "chart_with_notes", "chart": {"finding_id": "F_by_level", "type": "grouped_bar"}}] * 3}
    issues = []
    verify.check_deck_level(P(), store, bars, issues)
    check("three bar charts and nothing else is warned",
          any(i.rule == "chart_monotony" for i in issues))
    mixed = {"slides": bars["slides"][:3] + [
        {"layout": "chart_with_notes", "chart": {"finding_id": "F_share", "type": "donut"}},
        {"layout": "chart_with_notes", "chart": {"finding_id": "F_share", "type": "table"}}]}
    issues = []
    verify.check_deck_level(P(), store, mixed, issues)
    check("a mixed deck is not warned", not any(i.rule == "chart_monotony" for i in issues))


def test_table_cells_come_from_findings():
    from cscg import charts
    store = _mini_store()
    data = charts.table_data({"finding_ids": ["F_by_level"], "finding_id": "F_by_level",
                              "type": "table", "column_labels": ["Knows how"],
                              "value_formats": ["percent"], "highlight": "Graduate"}, store)
    check("table values are the finding's values", data["rows"] == [["Undergraduate", "81%"],
                                                                    ["Graduate", "44%"]], str(data["rows"]))
    check("table highlight row resolves", data["highlight_row"] == 1)


def test_cite_output_passes_the_linter():
    from cscg import cli
    store = _mini_store()
    lines = "\n".join(cli._slide_ready(store["F_by_level"]))
    check("cite prints the percentage as written", "81%" in lines and "44%" in lines, lines)
    check("cite prints the gap as an integer", "gap: 37 points" in lines, lines)

    class P:
        cfg = {"benchmarks": []}
    issues = []
    verify.check_numbers(P(), store, {"layout": "chart_with_notes", "cites": ["F_by_level"],
                                      "title": "81% of undergraduates know how, vs 44% of graduates, a 37-point gap (n=272)."},
                         1, issues)
    check("numbers copied from cite verify clean", not issues, str(issues))


def test_unc_logo_deck_builds_clean():
    """End to end: UNC client gets the UNC logo, not its name; new chart types render;
    nothing overflows or overlaps at the readable type floors."""
    import tempfile
    from pptx import Presentation
    from cscg import deck, preview
    from cscg.project import Project
    store = _mini_store()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        proj = Project(root=root, cfg={"client": "UNC Athletics", "term": "Fall 2026"})
        sl = {"meta": {"client": "UNC Athletics", "term": "Fall 2026", "theme": "dark"},
              "slides": [
                  {"layout": "title", "subject": "Student ticketing", "date": "October 2026"},
                  {"layout": "agenda", "items": ["Access", "Lottery", "Next steps"]},
                  {"layout": "executive_summary", "title": "Access, not demand, limits attendance.",
                   "cites": ["F_by_level"], "source": "Source: test data.",
                   "findings": [{"statement": "81% of undergraduates know how to get tickets, vs 44% of graduates.",
                                 "so_what": "Target outreach at graduate students."}]},
                  {"layout": "chart_with_notes", "section": "Access", "title": "60% get tickets through the lottery.",
                   "cites": ["F_share"], "source": "Source: test data.",
                   "chart": {"finding_id": "F_share", "type": "donut", "highlight": "Lottery"},
                   "notes": [{"label": "SO WHAT", "text": "The lottery is the main channel."},
                             {"label": "WATCH-OUT", "text": "Respondents, not all students."}]},
                  {"layout": "comparison_pair", "section": "Lottery", "title": "Knowing how differs by level.",
                   "cites": ["F_by_level"], "source": "Source: test data.",
                   "charts": [{"finding_id": "F_by_level", "type": "table", "columns": ["value", "n"],
                               "value_label": "Knows how", "row_label": "Level"}],
                   "caption": "Undergraduates know how far more often."},
              ]}
        builder = deck.DeckBuilder(proj, store, sl)
        out = builder.build(root / "decks" / "t.pptx")
        prs = Presentation(str(out))
        cover = prs.slides[0]
        pics = [sh for sh in cover.shapes if sh.shape_type == 13]
        texts = " ".join(sh.text_frame.text for sh in cover.shapes if sh.has_text_frame)
        check("cover carries the CSCG and UNC logos", len(pics) >= 2, f"{len(pics)} pictures")
        check("cover does not print 'UNC Athletics' when the logo exists",
              "UNC Athletics" not in texts, texts)
        footer_pics = [sh for sh in prs.slides[3].shapes if sh.shape_type == 13]
        check("body slide footer carries logos (plus the chart)", len(footer_pics) >= 3,
              f"{len(footer_pics)} pictures")
        check("a native table was built",
              any(getattr(sh, "has_table", False) and sh.has_table for sh in prs.slides[4].shapes))
        problems = builder.overflows + preview.analyse(out)["issues"]
        check("mini deck has no overflow or overlap", not problems, str(problems[:3]))


def test_spacing_model_is_shared():
    """The builder and the checker must measure a paragraph at the same line spacing."""
    from cscg import preview
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
    p = box.text_frame.paragraphs[0]
    p.line_spacing = 1.3
    r = p.add_run()
    r.text = "A paragraph set at 1.3 line spacing"
    r.font.size = Pt(12)
    paras = preview._shape_text(box)
    check("the checker reads the paragraph's line-spacing multiple",
          abs(paras[0]["mult"] - 1.3) < 1e-6, str(paras))


# ---------------------------------------------------------------------------
# Express mode (Sept 14, 2026): speed without losing the checks
# ---------------------------------------------------------------------------

def test_express_declares_from_structure_and_briefs_compactly():
    import random, tempfile, shutil as _sh
    from cscg import config as _cfg, express
    rnd = random.Random(7)
    with tempfile.TemporaryDirectory() as tmp:
        csvp = Path(tmp) / "survey.csv"
        rows = ["respondent_id,account_type,renewed_actual,sat_atmosphere,sat_parking,games_scanned,too_fast,survey_duration_sec"]
        for i in range(400):
            t = "Season" if i % 3 else "Student"
            atm = rnd.randint(1, 7)
            ren = 1 if rnd.random() < (0.35 + 0.08 * atm) else 0
            rows.append(f"{1000+i},{t},{ren},{atm},{rnd.randint(1,7)},{rnd.randint(0,7)},0,{rnd.randint(200,900)}")
        csvp.write_text("\n".join(rows))
        slug = "zz_express_selftest"
        root = _cfg.PROJECTS_DIR / slug
        if root.exists():
            _sh.rmtree(root)
        try:
            r = express.run(slug, [str(csvp)], question="What moves renewal?",
                            client="UNC Athletics", population="students")
            import yaml as _y
            cfg = _y.safe_load((root / "project.yaml").read_text())
            check("express detects the binary outcome by name", r["outcome"] == "renewed_actual", str(r["outcome"]))
            seg_cols = [x["column"] for x in cfg["segments"]]
            check("express declares a structural segment", "account_type" in seg_cols, str(seg_cols))
            check("flag and paradata columns are never analysed",
                  not any(c in (cfg["auto_declared"]["measures"]) for c in ("too_fast", "survey_duration_sec")))
            check("the declaration is recorded as made before results",
                  "before any result" in cfg["auto_declared"]["rule"])
            check("brief is compact (< 24k chars)", len(r["brief"]) < 24000, str(len(r["brief"])))
            check("brief carries a storyline skeleton", "Storyline skeleton" in r["brief"])
            check("express runs in under 30 seconds", r["seconds"] < 30, str(r["seconds"]))
        finally:
            if root.exists():
                _sh.rmtree(root)


def test_review_checks_catch_what_reviewers_caught():
    from cscg import charts
    store = _mini_store()
    bad_hl = charts.validate({"finding_id": "F_by_level", "type": "grouped_bar",
                              "highlight": "Grad students"}, store)
    check("a highlight that names no group is an ERROR", any(s_ == "ERROR" for s_, _ in bad_hl))
    ok_hl = charts.validate({"finding_id": "F_by_level", "type": "grouped_bar",
                             "highlight": "Graduate"}, store)
    check("a real highlight passes", not any(s_ == "ERROR" for s_, _ in ok_hl), str(ok_hl))

    class P:
        cfg = {"benchmarks": []}
    issues = []
    verify.check_review(P(), store, {"layout": "chart_with_notes", "cites": ["F_by_level", "F_share"],
                                     "title": "60% get tickets through the lottery.",
                                     "chart": {"finding_id": "F_by_level", "type": "grouped_bar"},
                                     "source": "s"}, 1, issues)
    check("a title number the chart does not draw is flagged",
          any(i.rule == "title_not_on_chart" for i in issues), str(issues))
    issues = []
    verify.check_review(P(), store, {"layout": "chart_with_notes", "cites": ["F_by_level"],
                                     "title": "81% know how, BH-adjusted p=0.01.", "source": "s"}, 1, issues)
    check("test jargon outside the source is flagged", any(i.rule == "technical_text" for i in issues))

    store["F_by_level"].callable_difference = False
    store["F_by_level"].test = Test("chi-square", 1.0, 0.2, 0.31, "BH", "cramers_v", 0.05, "negligible")
    issues = []
    verify.check_review(P(), store, {"layout": "chart_with_notes", "cites": ["F_by_level"],
                                     "title": "Undergraduates 81%, graduates 44%.", "source": "s"}, 1, issues)
    check("two numbers from a non-callable finding side by side are flagged",
          any(i.rule == "reads_as_comparison" for i in issues))
    issues = []
    verify.check_review(P(), store, {"layout": "chart_with_notes", "cites": ["F_by_level"],
                                     "title": "Undergraduates 81% and graduates 44%: no clear difference.",
                                     "source": "s"}, 1, issues)
    check("an explicitly stated null is not flagged",
          not any(i.rule == "reads_as_comparison" for i in issues))


def test_unverified_number_message_says_what_is_citable():
    store = _mini_store()

    class P:
        cfg = {"benchmarks": []}
    issues = []
    verify.check_numbers(P(), store, {"layout": "chart_with_notes", "cites": ["F_by_level"],
                                      "title": "61% know how."}, 1, issues)
    detail = next((i.detail for i in issues if i.rule == "unverified_number"), "")
    check("the error lists the citable values", "81%" in detail and "44%" in detail, detail)


def test_negated_causal_language_is_allowed():
    """The hedge the skill asks for must not cost a rebuild."""
    store = _mini_store()

    class P:
        cfg = {"benchmarks": []}
    for text, should_flag in [("These are associations, not causes.", False),
                              ("It is not proof that parking drives churn.", False),
                              ("Atmosphere causes renewal.", True),
                              ("Early exits drive lapses.", False)]:
        issues = []
        verify.check_language(P(), store, {"layout": "chart_with_notes", "cites": ["F_by_level"],
                                           "title": text}, 1, issues)
        flagged = any(i.rule == "causal_language" for i in issues)
        check(f"causal check {'flags' if should_flag else 'allows'}: {text}", flagged == should_flag, str(issues))


def test_single_line_with_point_highlight_stays_focal():
    """The brief suggests a band label as the highlight; the only line must still be focal."""
    from cscg import charts, config as _c
    f = Finding(id="F_band", kind="proportion_by_segment", metric="percent", question_id="renewed",
                question_text="Renewed", base_definition="All",
                groups=[Group("Lowest quarter", 400, 0.78, 312), Group("Second quarter", 400, 0.68, 272),
                        Group("Highest quarter", 400, 0.50, 200)], overall_n=1200)
    fig = charts.line([f], "dark", highlight="Highest quarter")
    colour = fig.axes[0].lines[0].get_color().lstrip("#").upper()
    check("single-series line is drawn in the focal colour",
          colour == _c.theme("dark")["accent"].upper(), colour)


def main():
    for fn in sorted((f for n, f in globals().items() if n.startswith("test_")),
                     key=lambda f: f.__code__.co_firstlineno):
        print(f"\n{fn.__name__}")
        fn()
    print("\n" + "=" * 60)
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
