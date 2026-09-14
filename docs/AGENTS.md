# The agents

Seven specialised agents in `.claude/agents/`. Each has one job, a defined input and
output, and at least one thing it explicitly refuses to do.

| Agent | Takes | Produces | Refuses to |
|---|---|---|---|
| `cscg-data-analyst` | raw data | reviewed dictionary, cleaning rules, `findings.json` | compute a number in prose |
| `cscg-qualitative-analyst` | comments, FG notes | theme codes, codebook, quotes | state a theme count itself |
| `cscg-strategist` | findings briefing | `candidates.yaml` | use a number not in the briefing |
| `cscg-storyteller` | approved insights | `storyline.yaml` | assert a non-callable difference |
| `cscg-visualization` | a finding | a chart spec | chart without a finding ID |
| `cscg-deck-builder` | storyline | the `.pptx` | fix a fit problem by shrinking type |
| `cscg-qa-redteam` | everything | a hostile review | approve by default |

## Why these seven

The split follows where judgement actually differs, not where the pipeline has stages.

**Analyst and qualitative analyst are separate** because reading open text well and
choosing statistical tests well are different skills, and mixing them tends to produce
quantified qualitative data — the exact error the rules forbid.

**Strategist and storyteller are separate** because "what matters" and "in what order do
we say it" are genuinely different questions. Combining them produces decks that argue
for whatever is easiest to sequence.

**Visualization chooses, Python renders.** So charts are reproducible, restyleable, and
carry the exact numbers they drew in a sidecar file.

**QA is read-only and adversarial.** An agent that can fix what it finds will
under-report, because fixing is work and approving is not. It is told that a review
finding nothing is a review that was not done.

## Invoking them

Through the slash commands, which sequence them and stop at the gates:

```
/cscg-new  <slug> [data file]
/cscg-analyse  <slug>
/cscg-insights <slug>
/cscg-deck     <slug>
/cscg-qa       <slug>
/cscg-run      <slug>        # the whole thing, stopping at each gate
```

Or directly by name when you want one specific pass.

## Editing them

The agent files are prompts. When one of them keeps making the same mistake, that is a
missing instruction — add it to the agent file rather than correcting it by hand each
cycle. If the rule is about *what is true of CSCG work* rather than *how this agent
should behave*, put it in `config/` instead, so every agent and the linter both see it.
