---
description: Start a new CSCG research cycle from a raw data file
argument-hint: <slug> [path/to/data.csv]
---

Set up a new CSCG engagement cycle: `$ARGUMENTS`

1. Run `.venv/bin/python -m cscg new <slug>`.
2. If a data file path was given, copy it into `projects/<slug>/data/raw/`.
   **Copy - never move or modify the original.**
3. Interview me for what `project.yaml` needs, one short round of questions:
   - the business question this cycle answers (one sentence)
   - the decision it could affect - if none, say so and ask whether this is worth doing
   - who is in the room when it is presented
   - segments we care about, declared now rather than discovered later
   - any prior hypotheses or team opinions to test
   - whether we close with questions or recommendations
   - whether the data is real or synthetic
4. Fill in `project.yaml` from my answers.
5. Run `.venv/bin/python -m cscg ingest <slug>` and show me the data dictionary summary.
6. Stop there and tell me what to review before cleaning.
