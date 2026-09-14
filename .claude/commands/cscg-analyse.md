---
description: Clean, analyse and profile a CSCG dataset up to the first human gate
argument-hint: <slug>
---

Run the analysis stage for `$ARGUMENTS` using the **cscg-data-analyst** agent.

The agent should:
1. Review and correct `analysis/data_dictionary.json` - real question wording, honest
   analysis roles, aggressive exclusion of measures that cannot change a decision.
2. Set `value_bounds` in `project.yaml` so the impossible-value screen actually works.
3. Run `cscg clean`, read the exclusion-impact table, and tell me if cleaning moved a
   headline number.
4. Confirm the declared segments and correlations are the ones the question needs.
5. Run `cscg analyse`.
6. Work through anything marked REQUIRED in the suggested deeper analysis - especially
   the segment overlap check.
7. Run `cscg qual extract`, then hand off to **cscg-qualitative-analyst** for coding,
   and run `cscg qual tally` afterwards.

Then summarise for me:
- what was excluded and why
- the callable differences, and what did not clear the bar
- what was deliberately not analysed
- what makes you uneasy

Finally, create the gate-1 review file and **stop**. Do not generate insights.
