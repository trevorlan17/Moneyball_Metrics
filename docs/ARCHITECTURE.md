# CSCG research-to-deck system: architecture

## The problem this solves

A CSCG cycle runs: pick a question → collect student data → analyse → find what matters
→ present to the student advisory board → refine → present to UNC Athletics. The gap
between receiving data and presenting can be days. Building each deck by hand wastes
most of that time on work that is mechanical, and the parts that are *not* mechanical —
deciding what matters, deciding what the evidence can bear — get squeezed.

The goal is a strong first draft in about an hour, with humans reviewing everything
before it reaches a client.

## The governing constraint

An LLM that writes slides directly will, sooner or later, write a number that is not in
the data. Not from malice — from fluency. It will round 19% to "roughly a fifth", carry
a base from one slide to another, or describe a correlation as a driver. In a student
consulting deck presented to a real athletic department, that is the failure that
matters.

So the system is built around one rule:

> **Numbers are computed only in Python. Agents may select and phrase them. They may
> never produce one.**

Every statistic lands in `analysis/findings.json` as a **Finding** with a stable ID, its
base, the test that was run, its effect size, and the code path that produced it. Slides
cite finding IDs. Before a deck is built, `cscg/verify.py` re-extracts every number from
every slide and matches it back against the findings that slide cites — by *kind*, so a
fabricated "14%" cannot match a Cramér's V of 0.14.

That is what makes "never fabricate data" an enforced property rather than a hope.

## Pipeline

```
data/raw/  (immutable, never written to)
    │
    ▼  [py] ingest ────────────► analysis/data_dictionary.{json,md}
    │                            types inferred, roles proposed
    │        ◄── ANALYST EDITS the dictionary: real question wording, honest roles
    ▼  [py] clean ─────────────► data/processed/clean.csv
    │                            analysis/cleaning_report.md
    │                            + exclusion-impact check: did cleaning move a number?
    ▼  [py] analyse ───────────► analysis/findings.json
    │                            descriptives, declared-segment tests, BH correction,
    │                            effect sizes, the `callable_difference` gate
    │
    │  [agent] qualitative-analyst codes comments
    ▼  [py] qual tally ────────► analysis/themes.md  (+ theme findings)
    │
    ├──────────────── HUMAN GATE 1: are the cleaning rules and findings right?
    │
    ▼  [py] insights ──────────► insights/briefing.md
    │  [agent] strategist ─────► insights/candidates.yaml   (cites finding IDs only)
    │
    ├──────────────── HUMAN GATE 2: which insights are real, and which matter?
    │
    ▼  [agent] storyteller ────► storyline/storyline.yaml
    │  [agent] visualization ──► chart specs inside the storyline
    │
    ├──────────────── HUMAN GATE 3: is this the right argument, in the right order?
    │
    ▼  [py] verify ────────────► qa/lint_report.md      ← blocks the build on ERROR
    ▼  [py] charts + deck ─────► decks/*.pptx, charts/*.{png,svg,csv,json}
    ▼  [py] preview ───────────► decks/preview/*.png    + text-overflow check
    │  [agent] qa-redteam ─────► the judgement pass
    │
    └──────────────── HUMAN GATE 4: is this client-ready?
```

## Division of labour

**Python does** anything deterministic: file handling, type inference, quality screens,
every statistic, multiple-comparison correction, theme counting, chart rendering, slide
geometry, text measurement, and claim verification.

**Agents do** anything that is judgement: what the question needs, what to exclude, what
a comment means, which findings matter, what the "so what" is, how to order an argument,
which chart makes a point, and what is wrong with all of it.

The split is not stylistic. Anything an LLM does is unverifiable by the next stage;
anything Python does is reproducible and can be re-checked. So the boundary is drawn to
put every *checkable* thing on the Python side.

## The seven agents

| Agent | Takes | Produces | Refuses to |
|---|---|---|---|
| `cscg-data-analyst` | raw data | reviewed dictionary, cleaning rules, findings | compute a number in prose |
| `cscg-qualitative-analyst` | comments, FG notes | theme codes, codebook, quotes | state a theme count itself |
| `cscg-strategist` | findings briefing | candidate insights | use a number not in the briefing |
| `cscg-storyteller` | approved insights | storyline.yaml | assert a non-callable difference |
| `cscg-visualization` | a finding | a chart spec | chart without a finding ID |
| `cscg-deck-builder` | storyline | the .pptx | fix a fit problem by shrinking type |
| `cscg-qa-redteam` | everything | a hostile review | approve by default |

## Human checkpoints

Four gates, each a markdown file the analyst edits. The CLI refuses to run a downstream
stage until the file says `Status: APPROVED`. `--force` exists and records that it was
used. The gates are placed where an unreviewed decision would otherwise become
client-facing:

1. **Data** — after analysis. Cleaning rules, exclusions, what the findings support.
2. **Insights** — after candidates. Which are real, which matter, which are dropped.
3. **Storyline** — after the argument, before any rendering.
4. **Final** — after QA.

## Key design decisions

**The findings store is the interface between stages.** Agents pass finding IDs, never
numbers. Any stage can be re-run and re-checked against it.

**`callable_difference` is computed, not argued.** A difference may be asserted only if
it cleared an adjusted significance test *and* a practical-size floor — percentage points
for proportions, effect-size class for means and correlations. With n in the thousands,
significance alone is nearly meaningless, which is exactly the trap a student team falls
into.

**Segments and correlations are declared before analysis.** Discovering a segment after
seeing results is how false findings are manufactured. It also keeps the
multiple-comparison family small enough that real findings survive correction.

**Raw data is never written to.** Cleaning produces a new file, records a hash of the
source, and reports whether excluding rows moved a headline number.

**Style lives in YAML, not code.** `config/presentation_style.yaml` holds the grid, type
scale, palette, layouts and writing rules inferred from the reference decks. Changing how
CSCG decks look does not mean touching Python.

**Text is measured, never assumed.** Layouts compute wrapped heights from real font
metrics and lay out from them. Fixed line counts are what make generated decks overlap
themselves.

## Repository layout

```
config/        presentation_style · analysis_rules · chart_rules   ← all CSCG knowledge
cscg/          the deterministic engine
  config       findings   ← the traceability spine
  ingest       clean      analyze     stats      qualitative
  charts       deck       textfit     preview    verify    project   cli
.claude/
  agents/      seven specialised agents
  commands/    /cscg-new /cscg-analyse /cscg-insights /cscg-deck /cscg-qa /cscg-run
templates/     storyline_schema.yaml
tests/         regression tests for the guarantees
projects/<slug>/
  project.yaml          the engagement: question, audience, segments, hypotheses
  data/raw/             immutable
  data/processed/       clean.csv, quality_flags.csv
  analysis/             dictionary, cleaning report, findings.json, themes
  insights/             briefing, candidates
  storyline/            storyline.yaml
  charts/               png + svg + csv + json sidecar per chart
  decks/                .pptx and preview/*.png
  qa/                   lint and layout reports
  reviews/              the four human gates
```
