---
name: cscg-deck-maker
description: Builds a CSCG client deck from data files (XLSX, CSV, PDF tables), written insights and slide directions, in the look of CSCG's 2026 finals with McKinsey structure. Default is express mode - a draft deck in about 5-8 minutes and under 1M tokens. Use whenever someone asks for a CSCG deck, slides or presentation.
---

# CSCG deck maker - express mode (default)

Target: **5-8 minutes, under 1M tokens, about 8 tool calls.** Every tool call re-reads the
whole conversation, so the cost is (calls) x (context). Keep both small. Full mode
(`references/full-mode.md`) only when the user asks for it by name, for a client-final
red team, or for tailored analysis cuts.

## Hard rules

- **Do not read** engine source (`cscg/*.py`), `findings.md`, `briefing.md`, `templates/`,
  other projects, raw workbooks, preview images, or this skill's references.
- **No subagents. No questions mid-run.** State assumptions in the final message instead.
- **Write each file once.** If a fix touches more than two places, rewrite the file with one
  Write rather than many Edits.
- **Batch.** Independent calls go in one message.
- **Never render or view previews** unless the user asks. `ship` checks layout without them.

## The path

1. **Setup + analysis + brief** (1 call):
   ```bash
   .venv/bin/python -m cscg express <slug> --files <every attached file> \
     --question "<the user's request>" --client "<client>" \
     [--population "students"] [--outcome <column>] [--synthetic]
   ```
   It prints the brief: leads with slide-ready numbers, chart specs and source lines, nulls,
   themes, and a storyline skeleton. That output is all you read.

2. **Decide the argument, in your head, before writing** (no tool call):
   governing thought → three MECE pillars (these are the agenda items) → 4-7 body slides,
   one lead each → close. An insight needs **tension** (it contradicts what people say or
   believe), a **decision** it changes, and a **mechanism** labelled as a hypothesis. Strong
   patterns: loud vs decisive, stated vs revealed, the well-powered null, everyone agrees...
   but.

3. **Write `projects/<slug>/storyline/storyline.yaml` once** (1 call), from the skeleton:
   title → agenda → executive_summary → how_to_read → body → close. Every body slide has
   `section:` (an agenda item), `cites:`, `chart:` copied from the brief, 2-3 notes, `source:`.

4. **Ship** (1 call): `.venv/bin/python -m cscg ship <slug>`
   It lints, runs review checks, builds, checks layout, and prints the ghost deck. If it
   lists errors, fix **all** of them in one rewrite and ship once more. Stop after the third
   ship and report what remains.

5. **Deliver** (1 call): SendUserFile the deck. In the reply: the ghost deck titles, what
   was auto-declared, assumptions made, and that the storyline and final gates are pending
   human review of the draft.

## Slide rules (the builder enforces the look; you supply the words)

| Element | Rule |
|---|---|
| Title | the finding with its number, sentence case, <= 2 lines |
| Agenda | slide 2; 3 pillars, <= 4 words each |
| Exec summary | 3-4 items: statement ~25 words, so_what ~12 |
| Notes | 2-3 boxes, <= 35 words, labels SO WHAT / WATCH-OUT / IMPLICATION / WHO CITES IT / ACROSS GROUPS / CONTEXT |
| Source | <= 40 words; test names and p-values only here |

**Charts:** use the spec the brief prints for each lead. `line` for ordered bands, `column` for
ordered scales, `grouped_bar`/`ranked_bar` for comparisons, `donut` for one whole in 2-5
parts (composition findings only), `table` for several attributes across groups
(`finding_ids`, `column_labels`, `value_formats`). `highlight` must be a group label exactly
as the brief writes it.

**Numbers:** copy them exactly from the brief; list their IDs in the slide's `cites:`.
Callable leads may be written as differences; nulls never ("similar", "nothing separates").
No causal verbs on correlations. Focus groups are sessions, never percentages. If a number
you need is not in the brief, run `cscg cite <slug> <id>` once - do not guess.
