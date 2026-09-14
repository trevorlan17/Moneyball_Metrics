# CSCG research-to-deck system

Raw survey data → analysis → insights → storyline → charts → a CSCG-formatted deck,
with humans reviewing at four checkpoints.

Built for Carolina Sports Consulting Group's UNC Athletics student advisory board
engagement, and reusable across topics and clients.

## The one rule everything else follows

**Numbers are computed only in Python. Agents select and phrase them; they never
produce one.**

Every statistic lands in `analysis/findings.json` with a stable ID, its base, the test
that was run, and its provenance. Slides cite finding IDs. Before a deck is built, the
claim linter re-extracts every number from every slide and matches it back — by kind, so
a fabricated `14%` cannot match a Cramér's V of 0.14. **The build refuses to run if a
claim fails.**

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python tests/test_system.py          # "all checks passed"
```

In Claude Code:

```
/cscg-new  unc_ticketing_c1  ~/Downloads/survey.csv
/cscg-run  unc_ticketing_c1
```

Or drive it directly:

```bash
.venv/bin/python -m cscg new     unc_ticketing_c1
.venv/bin/python -m cscg run     unc_ticketing_c1     # → human gate 1
.venv/bin/python -m cscg status  unc_ticketing_c1
.venv/bin/python -m cscg cite    unc_ticketing_c1 --grep ticket   # slide-ready numbers
.venv/bin/python -m cscg build   unc_ticketing_c1 --no-preview    # ~2s iteration
```

## Pipeline

```
files in  → intake ─┬→ raw respondent data → ingest → clean → analyse ─┐
data/raw/           └→ summary tables, PDFs, opinions → declare ────────┤
                                                                        │
                                    ─────────────────────────────────┬→ GATE 1 → insights → GATE 2
                                     │
                    qualitative ─────┘
                                          → storyline → GATE 3
                                          → build + QA → GATE 4 → deck
```

Each gate is a markdown file you edit. The CLI will not run past one that does not say
`Status: APPROVED`.

## Docs

| | |
|---|---|
| [docs/HOW_TO_USE.md](docs/HOW_TO_USE.md) | **start here** when a survey arrives |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | how it fits together and why |
| [docs/CSCG_STYLE_SPEC.md](docs/CSCG_STYLE_SPEC.md) | the deck conventions, and where they came from |
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | what it does not do, and what to build next |
| [templates/storyline_schema.yaml](templates/storyline_schema.yaml) | every layout and slot |
| [.claude/skills/cscg-deck-maker/SKILL.md](.claude/skills/cscg-deck-maker/SKILL.md) | **the deck-writing method**: McKinsey structure in CSCG's skin |

## Where CSCG knowledge lives

All of it in `config/`, none of it in code:

- `presentation_style.yaml` — grid, type, palette, layouts, writing rules, banned phrases
- `analysis_rules.yaml` — thresholds, test selection, causal-language policy
- `chart_rules.yaml` — which chart answers which question, and how to draw it

## Worked example

`projects/coastal_state_fan_research/` is a complete run on the Coastal State Athletics
case data (1,850 survey responses joined to gate-scan and account records, plus 6 focus
groups). It reproduces the reference analysis's correlations independently — crowd
atmosphere 0.25, entry wait 0.16, parking 0.05 — and builds a nine-slide deck that
passes the claim linter with zero errors.
