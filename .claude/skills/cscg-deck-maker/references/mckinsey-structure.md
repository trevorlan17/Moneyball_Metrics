# McKinsey deck structure: the working reference

Depth behind SKILL.md. Read when you need the reasoning, not just the rule.

Primary source: <https://slidemodel.com/mckinsey-presentation-structure/>, supplemented by
Barbara Minto's *The Pyramid Principle* and Gene Zelazny's *Say It With Charts* (both
McKinsey-originated).

---

## 1. The Pyramid Principle

Developed by **Barbara Minto** at McKinsey in the 1960s. Ideas form a pyramid: one
governing thought at the apex, supporting arguments below, evidence at the base.

```
                    GOVERNING THOUGHT
                    (the answer, stated first)
                            │
        ┌───────────────────┼───────────────────┐
    ARGUMENT 1          ARGUMENT 2          ARGUMENT 3
        │                   │                   │
   evidence            evidence            evidence
```

Two rules govern the structure:

**Ideas at any level summarise the ideas grouped below them.** An argument is not a new
idea; it is the summary of its evidence. If you cannot summarise a group of slides in one
sentence, the group is not a group.

**Ideas in a group are the same kind of idea, in a logical order.** Not three causes and a
recommendation. Either all causes, or all steps, or all segments. Order them deliberately:
by time, by structure, or by importance.

### Why top-down

The audience is going to build a structure in their head whether you give them one or not.
If you present chronologically and conclude at the end, they build the wrong one and spend
the presentation re-filing everything you said. Give them the conclusion first and every
subsequent slide has somewhere to go.

This is also why the executive summary is slide 2. It is not a courtesy. It is the frame.

---

## 2. MECE

**Mutually Exclusive, Collectively Exhaustive.**

*Mutually exclusive*: no two categories overlap. Overlap signals that you have not
identified the real dimension. "Undergraduates, graduate students, and Greek life members"
is not MECE, because Greek life members are mostly undergraduates. The real dimensions are
student level and Greek affiliation, and they are separate cuts.

*Collectively exhaustive*: nothing material is missing. The categories together cover the
problem.

### Testing it

- Remove one argument. Does the governing thought still hold? If yes, that argument is
  decoration.
- Can you describe two arguments with the same sentence? Merge them.
- What would a hostile, well-informed client say is missing? Add it or explain its absence.

MECE is a thinking tool, not a presentation tool. If the deck is not MECE, the analysis is
not finished.

---

## 3. SCR / SCQA

**Situation → Complication → Resolution.** Minto's version adds a Question:
Situation → Complication → Question → Answer.

- **Situation**: context the audience already accepts. No argument here; you are
  establishing common ground.
- **Complication**: what changed, what broke, or what the situation fails to account for.
  This creates the tension that makes the audience want the answer.
- **Question**: the question the complication raises. Often implicit.
- **Resolution / Answer**: your governing thought.

Worked example:

> **S** — UNC Athletics wants more students at home games and runs a lottery to allocate
> student tickets.
> **C** — Students who most often say they cannot get tickets are not losing the lottery.
> They never entered it, because they did not know how.
> **Q** — Is this a demand problem or a distribution problem?
> **A** — Distribution. Fix outreach to grad and professional students before redesigning
> the draw.

The SCR belongs in the opening: the executive summary, or the slide before it. It should
take under a minute.

---

## 4. The ghost deck

A **ghost deck** is the numbered list of action titles, in order, with no slide content —
the deck's skeleton, written before anything is designed.

Build it as a table:

| # | Action title | Layout | Evidence (finding IDs) |
|---|---|---|---|
| 2 | Ticketing is a distribution problem, not a demand problem | executive_summary | F012, F034 |
| 3 | 422 respondents, reached via student orgs, skew Greek and undergraduate | how_to_read | F001, F002 |
| 4 | 56% of grad/professional respondents naming a barrier didn't know how to get tickets, vs 19% of undergrads | chart_with_notes | F012 |

Then **read only the title column, in order**. It must be a complete argument.

The ghost deck exists because changing your mind is free at this stage and expensive
later. It is also the artefact to put in front of a human for approval: reviewing 12 titles
takes two minutes, reviewing 12 built slides takes an hour and reviewers anchor on
formatting instead of logic.

---

## 5. Horizontal and vertical logic

**Horizontal logic** runs *across* the deck, through the titles. Executives read titles
first, and some read only titles. The sequence of titles must stand alone as the argument.

Test: extract the titles to a plain text file and read it. If it reads as an agenda
("Methodology. Segmentation. Pricing. Next steps."), the deck has horizontal structure but
no horizontal logic.

**Vertical logic** runs *down* a single slide. The title makes a claim; everything on the
slide exists to support it. Every element answers "why should I believe the title?"

Test: cover the title. Can you reconstruct it from the body alone? Cover the body. Is the
title still a complete claim? Both should be yes.

---

## 6. Action titles

McKinsey's term for a title that states a finding rather than naming a topic. Sometimes
called a "so-what title" or "message title".

**Anatomy**: subject + what is true of it + the number that proves it.

> *56% of grad/professional respondents naming a barrier didn't know how to get tickets,
> vs 19% of undergrads.*

subject: grad/professional respondents · claim: didn't know how · number: 56% vs 19%

**Failure modes**

| Failure | Example | Fix |
|---|---|---|
| Topic label | "Ticket Access" | State what is true of ticket access |
| Claim with no number | "Grad students face more barriers" | Add the number and the base |
| Two claims | "Grads lack awareness and the lottery frustrates everyone" | Two slides |
| Hedged to meaninglessness | "There may be some awareness differences" | Either it cleared the test or it is not a finding |
| Restating the chart | "Chart showing barriers by student level" | Say what the chart *means* |

Sentence case, not title case. Title case reads as a heading; sentence case reads as a
sentence, which is what it is.

---

## 7. Chart selection (Zelazny)

Gene Zelazny ran visual communication at McKinsey for decades. His sequence:

**Message → comparison → chart form.** Never data → chart form.

Start from the sentence you want the reader to conclude. That sentence implies one of five
comparisons, and each comparison has a natural form:

| Comparison | Signalled by | Form |
|---|---|---|
| **Component** | share of, percentage of total | single 100% stacked bar (pie only for a 2-part split) |
| **Item** | larger than, ranked, best/worst | horizontal bar, sorted |
| **Time series** | changed, grew, declined, trend | column (few periods) or line (many) |
| **Frequency distribution** | range, concentration, distribution of | histogram or stacked Likert |
| **Correlation** | relates to, increases with, vs | scatter or paired bar |

Then: **the chart title is the message, not the variable names.** "Renewal tracks
atmosphere more than parking", not "Satisfaction vs renewal by category".

**Highlighting is the argument.** One focal colour on the series the title is about;
everything else grey. If every series is coloured, the chart has no point of view.

---

## 8. The so-what test

Applied at three levels:

- **Slide**: if the client accepted this completely, what would they do differently?
- **Argument**: does this change the governing thought if it fails?
- **Deck**: what decision does this affect?

A slide that survives only because the analysis was hard to do is a sunk cost. Move it to
the appendix.

---

## 9. Design conventions

From the source article, and consistent across McKinsey output:

- Action titles capturing key takeaways
- Minimal colour palette aligned with brand identity
- Ample white space to reduce visual fatigue
- Consistent fonts, sizes and layouts throughout
- Clear visual hierarchy for headings and subheadings
- High contrast between text and background

Note what is absent: gradients, drop shadows, stock photography, icon sets used
decoratively, animated transitions. Restraint is not an aesthetic preference here. It is
what makes the argument the most interesting thing on the slide.

---

## Sources

- [McKinsey Presentation Structure — SlideModel](https://slidemodel.com/mckinsey-presentation-structure/)
- [The Minto Pyramid Principle — Think Insights](https://thinkinsights.net/insights/minto-pyramid-principle)
- [The Pyramid Principle: How Consultants Structure Arguments That Win — Deckary](https://deckary.com/blog/pyramid-principle-consulting)
- [McKinsey Presentation Framework: The Complete Guide — A1 Slides](https://a1slides.com/mckinsey-presentation-framework/)
- [The Minto Pyramid Principle: How McKinsey Structures Slides — Winning Presentations](https://winningpresentations.com/pyramid-principle-presentations/)
- Barbara Minto, *The Pyramid Principle: Logic in Writing and Thinking*
- Gene Zelazny, *Say It With Charts*
