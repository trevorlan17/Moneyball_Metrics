---
description: Run the whole CSCG pipeline with human checkpoints
argument-hint: <slug>
---

Run the full pipeline for `$ARGUMENTS`, stopping at each human gate.

Start with `.venv/bin/python -m cscg status $ARGUMENTS` to see where it is, then
continue from there:

| Stage | Agent | Gate |
|---|---|---|
| ingest, clean, analyse, qualitative | cscg-data-analyst, cscg-qualitative-analyst | **Gate 1: data** |
| candidate insights | cscg-strategist | **Gate 2: insights** |
| storyline and charts | cscg-storyteller, cscg-visualization | **Gate 3: storyline** |
| build | cscg-deck-builder | |
| red team | cscg-qa-redteam | **Gate 4: final** |

At every gate: summarise what was produced, say what you are least sure about, and
**stop and wait for me**. Do not approve a gate on my behalf, and do not pass `--force`
unless I tell you to.

If a gate is already approved, continue past it without asking again.
