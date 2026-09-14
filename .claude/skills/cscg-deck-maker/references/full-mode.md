# Full mode

Use ONLY when the user asks for full mode, a client-final deck, tailored analysis cuts, human approval mid-run, or a red team. It is thorough and slow (~25-30 min, several million tokens). Express mode in SKILL.md is the default.



# CSCG deck maker

**McKinsey structure, CSCG's 2026 look.** The argument is built like a McKinsey deck; the
slides look like the Peter Millar, JGR and Nike finals: dark navy, blue cards, CSCG and
client logos, agenda on slide 2, section tabs along the bottom.

Numbers are computed in Python or declared with a source. You select and phrase them;
you never produce one. `cscg build` refuses a deck whose numbers do not trace back.

---

## Budget: aim for under 20 minutes end to end

The slow runs were never Python (a full build is ~2 seconds). They were loops: analysing
repeatedly, guessing numbers and bouncing off the linter, polishing slides before the
argument was settled. So:

| Stage | Target | How |
|---|---|---|
| Intake + analysis | 3 min | `intake`, declare everything, `analyse` **once**, `qual tally` |
| Insights | 3 min | read only the **Leads** and **Well-powered nulls** in `insights/briefing.md` |
| Ghost deck | 2 min | titles only; get a yes |
| Storyline | 8 min | write short; get every number from `cscg cite` |
| Build + fix | 3 min | `build --no-preview` until clean, previews once at the end |
| Red team | parallel | one storyline pass, split across subagents, **before** the build |

Rules that keep it there:
- **Never type a number you did not copy from `cscg cite`.** It prints each value the way
  the linter accepts it (`38%`, `n=1,052`, `0.25`, `gap: 26 points`) and whether a
  difference may be claimed. This one habit removes the lint ping-pong.
- **Write to the word budgets below the first time.** Overflow costs a rebuild.
- **Iterate with `cscg build <slug> --no-preview`.** Render previews once, at the end.
- **Do not re-read** this file, `findings.md` or the references mid-run. Look things up in
  `templates/storyline_schema.yaml` (every layout, every chart type, one example each).
- **Red-team once, on the storyline, in parallel** (see below). Do not re-run a full red
  team after cosmetic fixes.

---

## Inputs

**1. Written insights and opinions.** Raw material. Find the claim inside it; test it.

**2. Data files** — PDFs, XLSX, form exports, CSV. Never read numbers off them by eye.

```bash
# everything into projects/<slug>/data/raw/  (never modified)
.venv/bin/python -m cscg intake <slug>          # then read analysis/intake.md
```

| Intake says | Route |
|---|---|
| `raw_respondent_data` (one row per person) | `ingest -> clean -> analyse` — **computed** |
| `summary_table` (already counted) | `analysis/declared.yaml` + `cscg declare` — **declared**, needs base + source |
| `document` (PDF, notes) | read for insight; any number goes in `declared.yaml` |
| `unclear` / scanned PDF | a human decides; never guess |

Workbooks usually hold both kinds. An aggregated table read as respondent data gives
percentages of percentages, and nothing downstream catches it.

**3. Slide directions** — audience, must-includes, length, close, must-nots. Constraints
on the argument, not a substitute for it. If a direction conflicts with the evidence, say
so once, then build it with the caveat on the slide.

---

## Better insights: the bar

Start from `cscg insights <slug>` — its **Leads** (callable findings, strongest effect
first) and **Well-powered nulls** (large base, no effect). A candidate is an insight only
if it clears all five:

1. **Tension** — it contradicts a belief, a hypothesis, or what people say. The McKinsey
   UCA pair is the model: *"Everyone agrees urgent care provides quick access…"* /
   *"…but there are varying views on what else it should provide."* A restated finding is
   not an insight.
2. **Decision** — it names what changes and who decides.
3. **Mechanism** — a plausible why, labelled as a hypothesis, with how to test it.
4. **Falsifier** — the observation that would kill it.
5. **Pillar** — it belongs to one of **three MECE pillars** that organise the deck.

Patterns that reliably produce insights from survey data: **loud vs decisive** (most
complained about vs what tracks the outcome), **stated vs revealed** (what people say vs
recorded behaviour), **the well-powered null** (no effect on something the client believes
matters — often the most valuable slide), **the segment reversal**, and **everyone agrees…
but**.

---

## Structure

**Ghost deck first.** Titles only, in order. Read them top to bottom: they must form the
whole argument on their own (horizontal logic). If they read as topics, rewrite before
building anything. Get a human yes.

**Pyramid.** One governing thought (a claim someone could disagree with) → three pillars →
evidence. Answer first; never walk through the analysis chronologically.

**Three pillars, used everywhere** (the JGR final): they are the executive summary's
spine, the agenda's items, the section tabs, and the recommendation groups. The audience
always knows where they are.

**SCR** opens it: situation everyone accepts → complication → your resolution.

**Action titles.** Every title states the finding, with its number, in sentence case, in
two lines at most. *"56% of grad students naming a barrier didn't know how to get tickets,
vs 19% of undergrads"* — never *"Ticket Access"*.

**Vertical logic.** Everything on a slide answers "why should I believe the title?" One
message per slide.

### Deck sequence

```
1  title                 CSCG logo | client logo, subject line, date
2  agenda                ALWAYS. 3-6 section names, <= 4 words each - they become the tabs
3  executive_summary     governing thought + 3-5 findings, each with "So what:"
4  how_to_read           sample, method, limitations - before any finding
5+ body                  one message per slide, each with `section:` matching an agenda item
   quotes_themes         counted prevalence, attributed verbatims
N  close                 discussion_questions (default) or recommendation_table
   appendix              methodology, survey design, supplemental data (as the finals do)
```

The linter errors if slide 2 is not the agenda and warns if any agenda item names no
slide's `section:`.

---

## Charts: pick by the claim, and vary when the claim varies

| The title claims | Chart `type` |
|---|---|
| Group A differs from group B on one number | `grouped_bar` |
| These items rank in this order | `ranked_bar` (sorted, one highlighted) |
| One whole splits into 2-5 parts | `donut` (headline share in the centre) — `pie` for 2-3 |
| An outcome moves across ordered bands or time | `line` (several series may share the bands) |
| An ordered scale's distribution, left to right | `column` |
| Several attributes across several groups; exact values matter | `table` (native, editable, highlighted row) |
| Stated priority vs measured relationship | `quadrant_scatter` |
| One big number | not a chart: `stat_row` |

Every chart draws from findings (`finding_id`, or `finding_ids` for line/column/table).
The engine rejects a dishonest type: a donut whose slices do not sum to 100%, a donut of
separately-based groups or multi-select answers, a line with fewer than 3 points. It warns
when every chart in a deck is from one family — usually a sign the chart was chosen before
the claim. Examples of every type: `templates/storyline_schema.yaml`.

Formatting is automatic: one focal colour on the series the **title** is about, others
neutral; zero baselines; bases in labels; value labels instead of axes; format follows the
metric (`0.25` is never `25%`).

---

## The look (from the 2026 CSCG finals)

Applied by `cscg/deck.py` from `config/presentation_style.yaml`. You do not place any of it.

- **Logos, not names.** CSCG mark on the cover and bottom-left of every slide, client logo
  beside it. UNC Athletics gets the UNC logo automatically; for anyone else set
  `client_logo:` in `project.yaml`. The client's name is shown only when no logo exists.
- Dark navy ground, blue cards, light-blue pills and agenda boxes (`theme: dark`, default).
- Eyebrow "Fall 2026 Carolina Sports Consulting Group" top-left; kicker optional; title
  under it; body starts under the **measured** title.
- Section tabs along the bottom, current one lit; page number bottom-right.
- Source line: one or two short lines above the footer. Detail goes to the appendix.

### Word budgets (the build reports an overflow past these; it never shrinks type)

| Element | Budget |
|---|---|
| Action title | 2 lines, ~28 words |
| Exec-summary statement / so-what | ~30 / ~15 words, 3-5 items |
| Annotation box (`chart_with_notes`, 2-3 boxes) | ~35 words |
| `how_to_read` | 3 stats, <= 5 bullets of ~20 words |
| Recommendation cell | ~30 words |
| Source line | ~40 words |
| Agenda item | 4 words |

If the build says *"cut words"*, cut words. Do not move text into smaller boxes.

---

## Number rules the linter enforces

| Rule | In practice |
|---|---|
| Slide-level `cites:` authorises numbers | List every finding a slide mentions at slide level |
| Declared numbers are citable but flagged | Every `unverified_numbers` warning needs a human check against its source |
| Only `callable_difference` findings may be written as differences | No `vs` / `gap` / `higher than` on a slide citing a null; write "nothing separates them" |
| `gap_pp` is written as an integer | "26 points", not "25.9 points" |
| p-values are never citable | Put them in the source line |
| Ordinals and "Move 1" count as numbers | Add them to `allow_numbers:` |
| The small-base dagger must literally appear | `†` in the source line |
| No causal verbs on correlations | "is associated with", not "drives" |
| Focus groups are never percentages | "raised in 4 of 6 sessions" |

`cscg cite` output already respects all of these.

---

## Workflow

```bash
.venv/bin/python -m cscg intake   <slug>              # route files; read intake.md
.venv/bin/python -m cscg declare  <slug>              # declared facts (tables, PDFs, opinions)
.venv/bin/python -m cscg analyse  <slug>              # ONCE, after declaring every segment/check
.venv/bin/python -m cscg qual tally <slug>            # after every analyse
.venv/bin/python -m cscg insights <slug>              # Leads + Well-powered nulls
#   ghost deck -> human yes
.venv/bin/python -m cscg cite     <slug> --grep renew # numbers, slide-ready
#   write storyline/storyline.yaml (short, to budget)
.venv/bin/python -m cscg storyline <slug>             # lint the argument
#   red-team the storyline (parallel, below)
.venv/bin/python -m cscg build    <slug> --no-preview # ~2s; repeat until clean
.venv/bin/python -m cscg build    <slug>              # final, with previews
```

### Red team: once, on the storyline, in parallel

`cscg qa` at zero errors proves numbers trace to findings. It cannot see that a finding
answers a different question. Send one message with four subagent calls over the frozen
files (absolute paths, the specific question, what you already know):

1. **Citations** — does each cited finding support the exact sentence above it?
2. **Statistics** — callable vs not, nulls stated as nulls, confounds conceded but testable.
3. **Charts** — does each chart type fit its claim; does the title's number appear on it?
4. **Client** — the three questions leadership will ask that the deck cannot answer.

Never run two agents that write into the same project. The ghost deck and storyline have
one author.

---

## Analyse once

Every `analyse` recomputes the whole finding set and the multiple-comparison family, and
resets the data gate. Before the first run, declare every segment, correlation, derived
band and conditioning check you could need — including the ones expected to come out null
and the ones that could undercut the recommendation. Then `qual tally` (analyse rewrites
`findings.json`, and theme IDs vanish without it).

Finding IDs describe the finding (`F_renewed_by_leave_early_band`,
`Q_time_commitment`). Read each ID you cite and ask whether it describes the sentence
it sits under.

---

## Before you call it done

- [ ] Slide 2 is the agenda; every body slide has a `section:` from it
- [ ] Titles alone tell the story; governing thought is a claim; three MECE pillars
- [ ] Every insight has tension, decision, mechanism, falsifier
- [ ] Chart types fit their claims; the deck is not all bars unless every claim is a comparison
- [ ] `cscg build` reports no lint errors and no layout problems
- [ ] Cover and footers show logos; the client's name appears only if no logo exists
- [ ] Every `unverified_numbers` warning checked against its source by a human
- [ ] Previews viewed once, start to finish

Deeper reference, only if needed: `references/mckinsey-structure.md`,
`references/cscg-deck-audit.md` (includes the September 2026 ground-truth decks).
