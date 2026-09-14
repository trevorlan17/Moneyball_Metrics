---
description: Turn approved findings into candidate insights for prioritisation
argument-hint: <slug>
---

Generate candidate insights for `$ARGUMENTS`.

1. Check gate 1 is approved (`cscg status <slug>`). If not, stop and tell me.
2. Run `.venv/bin/python -m cscg insights <slug>` to build the briefing.
3. Use the **cscg-strategist** agent to produce `insights/candidates.yaml`.
4. Show me the candidates ranked by decision relevance, and separately:
   - what is merely descriptive
   - which prior hypotheses the data did not support
   - where quantitative and qualitative disagree
   - what should go to the student advisory board rather than to the client
5. Create the gate-2 review file and stop. I prioritise; you do not.
