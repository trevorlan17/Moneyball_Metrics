# CSCG research-to-deck system

Internal tool for Carolina Sports Consulting Group. Turns survey and focus-group data
into a client-ready CSCG deck, with human review at four gates.

Read `docs/ARCHITECTURE.md` before making structural changes.

## Speed budget - read this first

A deck request defaults to **express mode**: `cscg express` then one storyline Write then
`cscg ship`. Target 5-8 minutes, under 1M tokens, ~8 tool calls. A Sept 14 run without
these rules took 28 minutes and 7.4M tokens: every tool call re-reads the whole
conversation, and that run made 36 calls while its context grew to 289k tokens.

Never, in a deck request unless the user asks: read `cscg/*.py`, `findings.md`,
`briefing.md`, templates, other projects or raw workbooks; spawn subagents; ask questions
mid-run; view preview images; make many small Edits to one file. Full mode lives in
`.claude/skills/cscg-deck-maker/references/full-mode.md`.

## The rule that governs everything

**Numbers are computed only in Python. Agents select and phrase them; they never
produce one.**

If you are about to write a percentage into a slide, a memo, or a message to the user
that you did not read out of a generated file, stop. Run the pipeline and read the
result. This is the property the whole system exists to guarantee, and it is enforced:
`cscg/verify.py` re-derives every number on every slide from `analysis/findings.json`
and blocks the build if one does not match.

## Running it

```bash
.venv/bin/python -m cscg <command> <slug>      # never bare `python`
.venv/bin/python tests/test_system.py          # before and after any change to cscg/
```

Commands: `new intake ingest clean analyse qual declare insights cite storyline build preview qa status run`.

While writing slides, get every number from `cscg cite <slug> <ids|--grep text>` - it prints
values exactly as the linter accepts them. Iterate with `cscg build <slug> --no-preview`
(~2s); render previews once at the end.

Two ways a number becomes citable: **computed** (`analyse`, from respondent-level
data) or **declared** (`declare`, from a summary table, PDF or written insight).
Declared numbers carry `verified: false` and the linter warns on every slide that
uses one. Never put a number on a slide that is neither.

To write a deck, invoke the **cscg-deck-maker** skill. It holds the McKinsey
structure (Pyramid, MECE, SCR, ghost deck, action titles) and CSCG's visual identity.

## Where things belong

- **CSCG knowledge** → `config/*.yaml`. Thresholds, style, chart selection, writing
  rules. Never hard-code any of it in Python.
- **Agent behaviour** → `.claude/agents/*.md`. If an agent repeats a mistake, the fix is
  an instruction there, not a manual correction each cycle.
- **Deterministic logic** → `cscg/`.
- **Per-engagement anything** → `projects/<slug>/`.

If a rule is about what is *true of CSCG work*, it goes in `config/` so the agents and
the linter both see it. If it is about how an agent should *behave*, it goes in the
agent file.

## Conventions that are not negotiable

- `data/raw/` is immutable. Cleaning writes a new file and hashes the source.
- Segments and correlations are declared in `project.yaml` **before** analysis.
- Only `callable_difference` findings may be asserted as differences.
- No causal verbs on correlational findings.
- Comment and focus-group counts are never survey percentages.
- Every slide carries a source line and `cites:`.
- Layouts measure text with `cscg.textfit` and lay out from measured heights. **Never
  assume a line count** — that is what makes generated decks overlap themselves.
- Finding IDs must be stable across re-runs. **Every** finding derives its ID from its
  content, not a counter (`F_renewed_by_leave_early_band`, `Q_time_commitment`), so
  declaring one more correlation cannot renumber the rest and silently repoint a
  storyline's `cites:`. A trailing hex suffix means two declarations collided.

## Gotchas that have already bitten

- `matplotlib` rcParams are global and `charts.py` mutates them. `textfit` pins its own
  font for this reason — do not "simplify" it back to `family="sans-serif"`.
- Inferred scale ranges come from the data, so checking the data against them is
  circular. The impossible-value screen uses only `value_bounds` declared in
  `project.yaml`.
- Straightlining must be checked **within** a rating battery, not across every ordinal
  column, or it catches almost nobody.
- A percentage-point threshold is meaningless for means and correlations; those gate on
  effect size.

## Deck conventions (Sept 2026 ground truth)

The CSCG finals for Peter Millar, JGR and Nike are the reference look
(`.claude/skills/cscg-deck-maker/references/cscg-deck-audit.md`):
- Slide 2 is always the `agenda`; body slides carry `section:` and get footer tabs.
- Logos, not names: CSCG mark + client logo (UNC Athletics defaults to `assets/logos/unc.png`).
- Dark theme by default. Chart type follows the claim: donut / line / column / table
  as well as bars; `cscg/charts.py:validate` rejects dishonest types.
- Text is measured with one spacing model and never shrinks below `min_readable`;
  an overflow means cut words.
