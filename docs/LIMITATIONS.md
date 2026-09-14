# Limitations, open questions, and what to build next

Written honestly. Everything here is a known gap, not a surprise waiting to happen.

## What the system does not do

**It does not judge whether a finding is true.** It verifies that every number on a
slide traces to a computed finding with a stated base and test. It cannot tell you the
finding means what the slide says it means. That is the red-team agent's job, and the
red-team agent is an LLM — it will miss things.

**The claim linter checks numbers, not words.** "Grad students are frustrated" cites no
number and passes. Qualitative overreach is caught by rules (causal verbs, banned
phrases, non-callable differences) and otherwise by humans.

**Chart choice is not verified.** The visualization agent picks; nothing checks that the
pick was right. A grouped bar where a Likert was needed will render happily.

**Verbatim quotes are not verified against the transcript.** They are excluded from
number checking by design, which means a misquoted number inside a quote passes. Quotes
must be checked by a human against the source.

**The preview renderer is an approximation.** It uses matplotlib font metrics against
Arial to estimate PowerPoint's layout. It catches overflow reliably; it is not
pixel-accurate, and it renders only the first run's formatting per paragraph, so
mixed-format lines look wrong in the preview and correct in the file. **Open the .pptx
before sending it.**

**No LibreOffice on this machine**, so the built deck was verified by reading its XML
geometry and by the preview renderer, not by opening it in PowerPoint. Do that once
before the first client use.

## Statistical limitations

**Unweighted only.** The reference decks report unweighted results and disclose the
skew, so the system does the same. If CSCG ever needs weighted estimates, that is a real
build: weights, design effects, and effective sample sizes throughout.

**No multivariate modelling.** Crosstabs, mean comparisons and correlations only. The
system *suggests* a logistic regression when several segment gaps overlap, but will not
run one. Deliberate: the reference analysis reached better conclusions with two-way
splits than a model would have, and a model nobody on the team can defend in the room is
worse than no model.

**The segment overlap check is flagged, not automated.** The system tells you to check
whether a gap survives conditioning on other segments; it does not do it. This is the
most likely source of a false finding and the most valuable next thing to automate.

**`callable_difference` thresholds are conventions, not laws.** 10 percentage points and
`adjusted p < 0.05` come from the demo deck's own stated rule. They are tunable in
config and should be revisited with the project lead.

**Top-box definitions are inferred.** Top-two-box on 5+ point scales, top box on 3-4
point scales. Reasonable, but it is a decision the instrument should make. Check it per
survey.

**BH corrects across the whole run.** This is conservative — a genuine finding can be
lost because forty uninteresting crosstabs were also computed. The mitigation is to
declare fewer measures, which is why the data-analyst agent is told to exclude
aggressively.

## Open questions for you and the project lead

1. **Where does this live?** It is currently in a session scratch workspace. It needs a
   real home and a git remote before the semester starts.
2. **Real UNC student data — where and under what terms?** `data/raw/` is gitignored,
   but that is a convention, not a control. Decide the handling rules before the first
   real dataset arrives: who can hold it, where it may be copied, what happens at the
   end of the engagement.
3. **Do we have the actual UNC benchmarks?** The demo deck cites "UNC By the Numbers
   2026" and "UNC Fraternity & Sorority Life, Spring 2025". The system will not invent
   a benchmark. Someone needs to supply the real figures with sources.
4. **Does CSCG have a logo file?** The UNC kickoff has one bottom-left on every slide.
   The builder currently leaves that space empty. Drop a PNG in `templates/` and it can
   be placed.
5. **Questions or recommendations?** The default is questions, per the demo deck. Confirm
   that is what UNC Athletics expects from a student advisory board cycle.
6. **Board vs. client deck.** The workflow presents preliminary findings to the student
   board, then a final deck to Athletics. Right now that is one storyline built twice.
   A `board` / `client` variant flag would be a small, useful addition.
7. **Who owns the codebook across cycles?** Themes should be comparable between cycle 1
   and cycle 3. That needs a persistent codebook, which does not exist yet.

## Next improvements, in the order I would do them

1. **Automate the segment overlap check.** Compute each callable gap conditioned on the
   other declared segments and attach the result to the finding. Highest value for
   analytical validity — it directly prevents the most likely false finding.
2. **Wire in the quadrant "loud vs decisive" chart properly.** It currently takes explicit
   points, which is a traceability hole. It should be derived from findings the way
   `rank_associations` is.
3. **A second dataset test.** The system has been validated against one dataset with a
   particular shape (numeric ratings, behavioural join). A survey that is mostly
   select-all-that-apply and open text will exercise different paths — the `item_batteries`
   and open-text routes are the least tested code in the system.
4. **Cross-cycle comparison.** Cycle 3 should be able to say "up from 31% in cycle 1".
   That needs findings to be matchable across runs by question ID.
5. **Deck variants from one storyline** (board / client / appendix).
6. **A verified-quote check** — match each quote back to the coded CSV so a misquote is
   caught mechanically.
7. **An `appendix` layout** for the full question-by-question tables clients often ask for.

## Things I deliberately did not build

- **A web UI.** This is an internal tool for a small team who are already in a terminal.
- **A database.** Files in a folder are inspectable, diffable, and survive the tool.
- **LLM-generated charts.** Charts are rendered from findings so they are reproducible
  and restyleable without re-running an agent.
- **Automatic gate approval.** The gates are the point. A system that approves its own
  work is a system that produces unreviewed client materials.
