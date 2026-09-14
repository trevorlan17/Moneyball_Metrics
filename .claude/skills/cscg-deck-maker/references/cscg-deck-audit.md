# What each CSCG reference deck establishes

Slide-level audit of the decks supplied as references. Update this when the project lead
sends more, so the reasoning behind the style rules survives the person who worked it out.

---

## `CSCG_UNC_Kickoff (1).pptx` — Fall 2026, 11 slides, 13.33 × 7.5in

**The deck to follow.** CSCG's most disciplined output and the source of the visual spec in
`config/presentation_style.yaml`.

Already applies action titles:

> *"We operate on three non-negotiables: communicate constantly, hold strong opinions
> loosely, and debate ideas, not people."*
> *"UNC Athletics needs a standing, representative student voice, and CSCG is building,
> running, and sustaining it."*
> *"A 19-week, 7-phase engagement: from a blank list, to a seated board, to a formal
> year-end review."*
> *"Six people, six lanes, one deadline: every launch-critical asset ships by Saturday."*

Each states a claim and carries its number. This is horizontal logic in CSCG's own voice.

**Established:** the three-line head (eyebrow 9.5pt `#9FB0C9` / ALL-CAPS kicker 12pt bold
`#81B6EB` / action title 21-23pt bold). Grid: margin 0.55in, content 12.23in, eyebrow
y=0.24, kicker y=0.62, title y=0.92, body 2.25–6.45, footer 7.02. Arial throughout. Cards
`#24365F` on `#121630`. Carolina blue `#4B9CD3` as focal accent. CONFIDENTIAL + page number
on every slide. Numbered badges, workstream colour-coding with a legend, a timeline with
explicit hard-deadline markers.

**Also worth stealing:** slide 6 encodes a second variable in geometry — column width is
workload, segment colour is workstream — and says so in a caption. That is a real
information-design move, not decoration.

---

## `ESPN x CSCG Midpoint Presentation.pptx` — Spring 2026, 20 slides, 13.33 × 7.5in

Client-facing findings deck. **Good evidence instincts, weak title discipline.**

**Keep:**
- Bases on segments (`n≈50`, `n≈69`, `n≈42`)
- "Key Takeaways" panels on a dark card beside the evidence — the ancestor of the
  `chart_with_notes` annotation boxes
- Full-slide verbatim quotes with attribution
- The method slide stating completion rate and expected vs received responses
- Closing with *Strategic Questions We're Exploring* and *Key Questions for ESPN* rather
  than hard recommendations
- Slide 9's framing: *"ESPN isn't competing against YouTube TV — it's competing against
  free."* That is an action title, and the best one in the deck.

**Do not copy:**
- Topic titles: *Meet the Team, Key Research, Methodology, Segmentation, Die-Hard Fans,
  Price Ceiling, Tier Confusion, Competitive Breakdown*. A reader skimming titles gets the
  agenda and none of the findings.
- 50pt Passion One display type for titles. It crowds the slide and forces the message into
  the body.
- Mixed typography — Passion One, Manrope, Alexandria, Open Sans, Play, Arial across one
  deck.
- Slide 3's stat row uses two different reds (`#FF160F`, `#FF0000`) for the same role.

**The lesson:** this deck knows what evidence to show and has not yet learned to put the
conclusion in the title.

---

## `CSCG x ESPN Spring '26 Kickoff.pptx` — 8 slides, 10 × 5.62in
## `CSCG x USTA Fall '25 Kickoff.pptx` — 7 slides, 10 × 5.62in

**Internal planning decks. Not a model for client work.**

Identical skeleton: *Project Objective → Questions to Consider → Project Overview
(WHO/WHAT) → The Gameplan (Timeline) → Workstreams → First Steps → Looking Ahead.*

Every title is a label. Content is dense prose in bullets. Smaller canvas, no source lines,
no bases.

**Useful for one thing:** the intake structure. *Objective / stakeholders / deliverables /
timeline / workstreams / first steps* is a sound checklist for scoping an engagement, and
maps onto what `project.yaml` asks for. Use it to *start* a project, not to present one.

---

## `CSCG Coastal State Athletics.pptx` — 4 slides, 13.33 × 7.5in

Short, and the strongest arguing in the set.

> *"CSA is losing fans over the things nobody is complaining about"*
> *"The loudest complaints are not the expensive ones"*
> *"What surveyed fans say doesn't predict what fans do"*
> *"Prioritize low-cost experience fixes before capital spending"*

Four action titles that form a complete argument on their own — a working example of
horizontal logic.

**Established:** the LOUD vs QUIET-BUT-DECISIVE framing (complaint volume beside measured
association with the outcome); the RECOMMENDATION / EVIDENCE / IMPLICATION table; stating
quality exclusions on the title slide (*"232 responses (12.5%) removed for quality
failures"*).

---

## `DEMO_SYNTHETIC_CSCG_Ticketing_Deck_light.pdf` — 12 pages

Effectively a written spec for a CSCG findings deck, and the closest thing in the set to
McKinsey output.

**Established the whole evidence discipline:**
- Executive summary of 4 numbered findings, each with an explicit `So what:`
- A *"How to read these results"* slide at position 3 — field dates, n analysed, n excluded
  and why, distribution method, sample skew quantified against named benchmarks, weighting
  status, and the rule used for calling a difference
- `†` marking groups under n=30 as directional only
- Differences called out only when statistically tested with multiple-comparison adjustment
  **and** at least 10 points apart
- *"Respondents, not all students"* on every slide
- Qualitative prevalence as a count over a base: *"54 of 224 comments; 2 of 3 focus groups"*
- Source lines reproducing question wording, bases and test method
- Closing on discussion questions, each with *"Why it matters:"*
- A synthetic-data banner on every slide

Its rules are encoded in `config/analysis_rules.yaml` and enforced by `cscg/verify.py`.

---

## `CSCG Final Analysis - Julia Chen.xlsx`

Not a deck, but it sets the analytical standard the decks rest on. Tabs: *Notes+Method*
(how I built the file / the three things I found / **what I decided not to do** / **things
I am not sure about**), *Cleaning Checks*, and one tab per analysis with plain-English
caveats.

**Established:** correlation is never called causation; complaint volume is separated from
decision relevance (parking: 318 complaints, r = 0.04); stated intent is checked against
recorded behaviour; and what you chose *not* to analyse is documented alongside what you
did.

---

# GROUND TRUTH, September 2026

Supplied as the reference set to follow. Where anything above disagrees, this section wins.

## `CSCG x PM Final Presentation` (Peter Millar, Spring 2026, 58 slides)

- **Slide 2 is the agenda**: five rounded light-blue boxes in a row, joined by a thin
  line, each a 1-3 word section name. Nothing else on the slide.
- **Section tabs** along the bottom of every body slide (Aspiration / Socials / Gifting
  Bundles / Legacy Lounge), current section filled. The agenda items *are* the tabs.
- **Logos, not names**: CSCG mark + PETER MILLAR wordmark bottom-left of every slide.
- Dark navy ground; light-blue cards with a header pill; eyebrow "Spring 2026 Carolina
  Sports Consulting Group" tiny top-left; page number bottom-right.
- Recommendation slides are titled **"Recommendation N: <the recommendation>"** and every
  one is followed by the evidence slides that earn it.
- Chart mix: vertical columns in scale order ("relevant now" vs "in 5-10 years"), a donut
  beside bars, a **native table with a highlighted benchmark cell** (competitive
  licensing capabilities), word clouds, timelines. Not all bars.
- Methodology, survey design and focus-group detail live in the **appendix**, not the body.

## `CSCG x JGR Final Presentation` (Joe Gibbs Racing, 33 slides)

- **Three-pillar executive summary**: governing thought in a box on top, three pillar
  cards (Rewards / Relationships / Relevance), a "so what" box underneath. The same three
  pillars return as **section dividers with the current pillar lit** and the others greyed.
  This is the best structural move in the set: the pillars are MECE, they organise the
  whole deck, and the audience always knows where they are.
- Client logo top-right, CSCG mark bottom-right, numbered section tabs at the bottom.
- Evidence slide pattern: donut of drivers on the left, an arrow, three "Strategic
  Observations" boxes on the right. Big-number callouts (~79%, ~45%) beside a case study.
- Action titles: "Direct Utility and Exclusive Access Are the Primary Catalysts for Gen Z
  Purchase Intent".

## `Nike x CSCG Final Presentation` (27 slides)

- **Title lockup**: CSCG mark | thin vertical rule | Nike swoosh. No title text needed.
- CSCG + client logo bottom-left of every slide.
- Agenda as a stacked chevron list; "Key Patterns" panels beside charts; phased rollout
  plan; tables for product portfolios; treemap and donut in the survey overview.

## McKinsey references (UCA SAG, MGI adaptation, blockchain)

- "Topics for discussion" / "Agenda" as slide 2; the agenda **repeats as a divider** with
  the current item highlighted.
- **Split layout**: the action title set large in a narrow left panel, the chart on the
  right. Titles often run as a pair across two slides: *"Everyone agrees X..."* /
  *"...but there are varying views on Y"*. That tension is the insight.
- Donuts with the **headline share printed in the centre** ("~70% have a comprehensive
  strategy"). Stat callouts ("73.3/100"). Chart headers state the question: *"Q: What are
  the top challenges...? % of respondents"*.
- Source line one short line, bottom-left; "McKinsey & Company" + page number bottom-right.
- Close: *"What can we collectively do to advance these priorities?"* over the agenda list.

## What changed in the engine because of these

| Ground truth | Now in the engine |
|---|---|
| Agenda on slide 2, tabs on every slide | `agenda` layout; `section:` key; footer tabs; linter ERROR if slide 2 is not the agenda |
| Logos, not names | CSCG mark + client logo on cover and footer; UNC logo defaults for UNC Athletics |
| Dark navy + blue cards | `default_theme: dark`, card tokens with readable contrast |
| Donut, column, line, table | chart types `donut`, `pie`, `column`, `line`, `table`; validity checks; variety warning |
| One-line sources, readable body | type floors (`min_readable`); overflow reported instead of shrink-to-fit |
