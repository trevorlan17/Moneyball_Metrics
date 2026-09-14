---
description: Build the storyline and render the deck from approved insights
argument-hint: <slug>
---

Build the deck for `$ARGUMENTS`.

1. Check gate 2 is approved. If not, stop.
2. **cscg-storyteller**: write the argument in prose first - governing thought, the
   three to five supporting arguments, the evidence under each - and show it to me
   before writing any YAML. Then write `storyline/storyline.yaml`.
3. **cscg-visualization**: choose the chart for each evidence slide, specified against
   a finding ID.
4. Run `cscg storyline <slug>` and fix everything it reports.
5. Create the gate-3 review file, show me the storyline, and **wait for my approval**.
6. Once approved, **cscg-deck-builder**: run `cscg build <slug>`, read the previews,
   fix any fitting problems, rebuild.
7. Show me the rendered previews.
