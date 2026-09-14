# The CSCG presentation style, and where it came from

This is the reasoning behind `config/presentation_style.yaml`. The config is the
machine-readable version; this is why it says what it says.

## Sources

| Deck | What it established |
|---|---|
| `CSCG_UNC_Kickoff` (Fall 2026, 11 sl) | The current design system: grid, type scale, palette, footer, card geometry. Newest and most disciplined. |
| `DEMO_SYNTHETIC_CSCG_Ticketing_Deck` (12 pp) | The findings-deck storyline and the evidence discipline. Effectively a written spec. |
| `CSCG Coastal State Athletics` (4 sl) | Loud-vs-decisive framing; the RECOMMENDATION / EVIDENCE / IMPLICATION table. |
| `ESPN x CSCG Midpoint` (20 sl) | Segment slides, n= labels, quote slides, questions-for-client close. |
| `CSCG x ESPN Spring '26` / `USTA Fall '25` | Older internal kickoffs. Topic titles, not insight titles — the pre-system baseline, kept as a contrast. |
| `CSCG Final Analysis - Julia Chen.xlsx` | The analytical standard: method notes, cleaning checks, explicit caveats, "what I decided not to do". |

## The three-line head

Every slide in the modern decks stacks:

```
Fall 2026  •  Carolina Sports Consulting Group      ← eyebrow, 9.5pt, muted
TICKET ACCESS                                        ← kicker, 12pt bold, ALL CAPS
56% of grad/professional respondents naming a        ← action title, 21pt bold,
barrier didn't know how to get tickets, vs 19%.        sentence case, carries the number
```

The kicker names the slide's *job*. The title states what is *true*. Getting these
confused — "TICKET ACCESS" as the title — is the single most common way a deck slides
back into being a report.

**Titles are sentence case and contain a number.** A title without a number on an
evidence slide is a topic, and the linter warns about it.

## Grid

13.33 × 7.5in. Left margin 0.55in, content width 12.23in.

| | y |
|---|---|
| eyebrow | 0.24 |
| kicker | 0.62 |
| action title | 0.92 (height 1.05) |
| subtitle | 1.62 |
| evidence zone | 2.25 – 6.45 |
| source line | 6.62 |
| footer | 7.02 |

Standard gutter 0.32in. Cards are filled rectangles on the background; there are no
borders anywhere in the reference decks.

## Type

**Arial only.** Observed throughout the UNC kickoff. It is not an interesting choice,
and that is the point: CSCG decks get opened in PowerPoint, Keynote and Google Slides,
and Arial is the one face that renders identically in all three. A missing font is a
broken deck.

Scale: display 46 · title 21 (min 17) · stat hero 40 · card head 16.5 · body 11.5 ·
kicker 12 · eyebrow 9.5 · source 7.5 · footer 8.

The source line is deliberately small. It is for the record, not for the room.

## Colour

Carolina blue `#4B9CD3` is the focal accent — UNC's official primary, used as the
highlight throughout the kickoff deck. Two themes on one grid:

**Light** (client findings decks): white ground, `#F1F4FA` cards, `#121630` ink.
**Dark** (internal and kickoff decks): `#121630` ground, `#24365F` cards, white ink.

The working rule in charts: **one focal colour, everything else grey.** Colour marks the
comparison the title is making. It is an argument, not decoration.

For non-UNC clients, override `accent` per project. The ESPN decks adopted ESPN red and
kept the structure — client palette changes, conventions do not.

## Layouts

`chart_with_notes` is the workhorse: chart on the left (7.35in), three labelled
annotation boxes on the right (4.53in). **The boxes carry the argument; the chart only
carries the comparison.** Labels come from a fixed vocabulary — `WHO CITES IT`,
`WATCH-OUT`, `IMPLICATION`, `SO WHAT`, `ACROSS GROUPS`, `COMPOUNDING`, `CONTEXT` — so
readers learn what each box means across a deck.

Others: `title`, `executive_summary`, `how_to_read`, `comparison_pair`, `quotes_themes`,
`stat_row`, `three_cards`, `recommendation_table`, `discussion_questions`, `section`.

## Storyline

```
title
executive_summary     3-5 numbered findings, each with an explicit "So what:"
how_to_read           sample composition and limitations, BEFORE any finding
evidence slides       one message each
quotes_themes         the qualitative
discussion_questions  the close
```

Two conventions worth naming:

**Limitations come before findings, not in an appendix.** The demo deck's third slide
quantifies its own sample skew against real benchmarks before it shows a single result.
That is the move that makes the rest credible.

**The default close is questions, not recommendations.** Each with "Why it matters".
CSCG frames a decision; the client makes it. Recommendations are opt-in per project and
use the RECOMMENDATION / EVIDENCE / IMPLICATION table from the Coastal State deck.

**Null results get slides.** "Awareness gaps track student level, not Greek or Fever
status" stops a client acting on a pattern that is not there.

## Evidence discipline

From the demo deck, and it is strict:

- Every base is stated: `n=272`, and it travels in the chart's category label.
- Question wording is reproduced in the source line.
- `†` marks groups under 30 as directional only.
- A difference is called out **only** when statistically tested with
  multiple-comparison adjustment **and** at least 10 points apart.
- "Respondents, not all students" appears throughout.
- Focus groups are "voice, not prevalence" — reported in sessions, never percentages.
- Open-text themes are counted over a base: "54 of 224 comments".
- Every slide has a source line. No exceptions.

## Writing

- Answer first. The title concludes; the body proves.
- One message per slide. Two arguments means two slides.
- Say "respondents" whenever the sample is not representative.
- "39% attended no home games" beats "attendance was low".
- No adjective doing the work of evidence. "Significant" only when a test was run, and
  then name it.
- No causal verbs on correlational findings.
- Contractions are fine. Consulting-neutral, not stiff.

Banned outright, because they read as AI-generated or as unearned confidence: *delve,
leverage synergies, deep dive, holistic, game-changer, unlock, robust insights, clearly
shows, proves that, drives, causes.*
