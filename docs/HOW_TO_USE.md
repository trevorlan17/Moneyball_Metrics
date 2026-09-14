# Using the system when a new survey arrives

The short version: `/cscg-new`, answer some questions, then `/cscg-run` and work the
four gates. Everything below is what happens at each step and what you should actually
look at.

## Setup, once

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python tests/test_system.py     # should print "all checks passed"
```

## The fast path

In Claude Code, from the repo root:

```
/cscg-new unc_ticketing_c1 ~/Downloads/ticketing_survey.csv
/cscg-run  unc_ticketing_c1
```

`/cscg-run` walks the whole pipeline and stops at each human gate. Everything below
happens under it.

## Step by step

### 1. New cycle

```bash
.venv/bin/python -m cscg new unc_ticketing_c1
cp ~/Downloads/survey.csv projects/unc_ticketing_c1/data/raw/
```

Fill in `project.yaml`. The fields that change your results:

- **`business_question`** — one sentence. If you cannot write it, do not start.
- **`decision_context`** — what decision this could affect. If nothing, say so; that is
  a legitimate finding about the research design.
- **`segments`** — declare them *now*. Finding a segment after you have seen results is
  how false findings are made. Add `labels` so groups read as English.
- **`correlations`** — only the pairs the question needs. Every extra test enlarges the
  family that multiple-comparison correction has to work across, which makes your real
  findings harder to detect.
- **`hypotheses`** — what the team expects. These get tested, not assumed.
- **`synthetic_data: true`** if this is test data. Stamps a banner on every slide.

### 2. Ingest and review the dictionary

```bash
.venv/bin/python -m cscg ingest unc_ticketing_c1
```

**This is the step that determines everything downstream. Do not skip it.**

Read `analysis/data_dictionary.md`, then edit `analysis/data_dictionary.json`:

- `question_text` must match the real instrument. It is quoted verbatim in slide source
  lines. `q14_barrier` is not a question.
- `analysis_role`: `identifier` / `segment_candidate` / `measure` / `qualitative` /
  `exclude`.
- **Exclude aggressively.** A measure that cannot change a decision is noise.
- Watch for columns that are someone else's analysis output — pre-existing quality
  flags, derived scores. Using them is circular.

Also set `value_bounds` in `project.yaml` with the real instrument ranges. Without them
the impossible-value screen does nothing, because inferred ranges come from the data and
can never fail.

### 3. Clean

```bash
.venv/bin/python -m cscg clean unc_ticketing_c1
```

Read `analysis/cleaning_report.md`, and read the **"Did cleaning change the answer?"**
table specifically. If a number moves between "all rows" and "kept", the rows you removed
differ systematically, and that belongs in the deck's limitations.

### 4. Analyse

```bash
.venv/bin/python -m cscg analyse unc_ticketing_c1
```

`analysis/findings.md` separates:

- **Callable differences** — passed an adjusted test *and* a practical-size floor. Only
  these may be asserted as differences in a title or the exec summary.
- **Statistically clear but too small to call** — hypotheses, not findings.
- **Suggested deeper analysis** — nothing here runs automatically. Anything marked
  REQUIRED must be resolved before the related claim goes in a deck. The most common is
  the segment overlap check: a "Greek life" gap that is really an "undergraduate" gap.

### 5. Qualitative

```bash
.venv/bin/python -m cscg qual extract unc_ticketing_c1
# the cscg-qualitative-analyst agent codes the CSV -> analysis/comments_coded.csv
.venv/bin/python -m cscg qual tally unc_ticketing_c1
```

Counts are computed, never written by the agent. Comment counts are never survey
percentages; focus groups are reported in sessions, never percentages of participants.

### → GATE 1

`reviews/gate1_data.md`. Set `Status: APPROVED` when you are satisfied with the cleaning
rules, the exclusions, and what the findings support.

### 6. Insights

```bash
.venv/bin/python -m cscg insights unc_ticketing_c1     # builds the briefing
```

Then the strategist agent writes `insights/candidates.yaml`. Read the
`counter_argument` field on each candidate — if it is weak, the insight is not
understood well enough to present.

### → GATE 2

You prioritise. The agent does not decide what goes in the deck.

### 7. Storyline

The storyteller writes the argument in prose first, then `storyline/storyline.yaml`.

```bash
.venv/bin/python -m cscg storyline unc_ticketing_c1    # validates
```

### → GATE 3

Approve the argument before anything is rendered. This is the cheapest place to change
your mind.

### 8. Build

```bash
.venv/bin/python -m cscg build unc_ticketing_c1
```

Lints, renders the .pptx, checks the layout, and writes PNG previews to `decks/preview/`.
The build **refuses to run** if any claim fails verification.

### 9. QA

```bash
.venv/bin/python -m cscg qa unc_ticketing_c1
```

Then the red-team agent. It is instructed not to approve by default; if it comes back
with nothing, ask it what it tried.

### → GATE 4

## Commands

| | |
|---|---|
| `cscg new <slug>` | scaffold an engagement |
| `cscg ingest <slug>` | profile data, build the dictionary |
| `cscg clean <slug>` | quality screens |
| `cscg analyse <slug>` | statistics → findings.json |
| `cscg qual extract\|tally <slug>` | open text |
| `cscg insights <slug>` | package findings for the strategist |
| `cscg storyline <slug>` | validate a storyline |
| `cscg build <slug>` | render the deck |
| `cscg preview <slug>` | slide PNGs + overflow check |
| `cscg qa <slug>` | claim linting |
| `cscg status <slug>` | where the project is, what is blocking |
| `cscg run <slug>` | every deterministic stage, stopping at gate 1 |

Add `--force` to proceed past an unapproved gate or a failing lint. It is recorded.

## When something is blocked

**"Slide states N numbers but cites no finding."** Add `cites: [F0xx]`, or
`allow_numbers:` for instrument facts like field dates.

**"'61%' does not match any value in the cited findings."** Either the number is wrong,
the citation is wrong, or the analysis behind it was never run. Check in that order.

**"Slide asserts a difference on F033, which the analysis did not mark callable."**
Reframe as "similar" / "no clear difference", or remove it.

**"Causal verb 'drives' on a correlational finding."** Use "is associated with". If
independently recorded behaviour supports the stronger claim, name that source on the
slide.

**Text overflow.** Cut words. Do not shrink type — a title that needs 11pt is trying to
be two slides.

## Changing how CSCG decks look

Everything is in `config/`:

- `presentation_style.yaml` — grid, type scale, palette, layouts, writing rules, banned
  phrases
- `analysis_rules.yaml` — thresholds, test selection, causal-language policy
- `chart_rules.yaml` — chart selection and formatting

For a non-UNC client, set `accent_override` in `project.yaml` rather than editing the
palette.
