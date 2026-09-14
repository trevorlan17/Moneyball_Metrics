"""Per-engagement project scaffolding, config, and the human approval gates."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import config, util

SUBDIRS = [
    "data/raw",
    "data/processed",
    "analysis",
    "insights",
    "charts",
    "storyline",
    "decks",
    "qa",
    "reviews",
]

# The four human checkpoints. The CLI refuses to run a stage whose upstream gate has
# not been signed off. This is the mechanism that stops an agent from taking an
# unreviewed strategic conclusion all the way to a client-facing slide.
GATES = {
    "data": {
        "file": "reviews/gate1_data.md",
        "after": "analyse",
        "question": "Are the cleaning rules, exclusions and sample caveats right?",
    },
    "insights": {
        "file": "reviews/gate2_insights.md",
        "after": "insights",
        "question": "Which candidate insights are real, and which matter to the client?",
    },
    "storyline": {
        "file": "reviews/gate3_storyline.md",
        "after": "storyline",
        "question": "Is this the right argument, in the right order?",
    },
    "final": {
        "file": "reviews/gate4_final.md",
        "after": "qa",
        "question": "Is the deck client-ready?",
    },
}

PROJECT_TEMPLATE = """\
# CSCG engagement configuration
# Everything the pipeline needs to know about this piece of work.

slug: "{slug}"
title: "{title}"
client: "{client}"
term: "{term}"
cycle: "{cycle}"

# --- The work ------------------------------------------------------------
business_question: >
  {question}

audience: "{audience}"          # who is in the room when this is presented
decision_context: >
  What decision could this affect? If nothing, reconsider doing the analysis.

# Does this engagement close with recommendations, or with questions for the client?
# CSCG's default is questions - the board and the client decide, we frame the choice.
close_with: questions          # questions | recommendations

# --- Data ----------------------------------------------------------------
data:
  survey_file: ""              # relative to data/raw/
  survey_sheet: ""             # for .xlsx; blank = first sheet
  id_column: ""
  open_text_columns: []
  # Behavioural / administrative data to check self-reports against, if any.
  actuals_file: ""
  actuals_join_key: ""

# Segments must be declared BEFORE analysis, not discovered after it.
segments: []
  # - column: respondent_type
  #   label: Student level
  #   order: [Undergraduate, Graduate/professional]

# --- Context -------------------------------------------------------------
# External benchmarks used on the "how to read these results" slide. Every entry
# needs a real, named, dated source. The system will not invent one.
benchmarks: []
  # - metric: "Share of students who are grad/professional"
  #   value: 0.36
  #   source: "UNC By the Numbers 2026"

# Team opinions and prior hypotheses. These are tested, not assumed.
hypotheses: []
  # - "Awareness, not interest, is the binding constraint on grad attendance."

context_notes: >
  Anything the analyst knows that the data does not say.

# --- Flags ---------------------------------------------------------------
synthetic_data: false          # stamps a warning banner on every slide when true
theme: dark                    # dark (2026 CSCG finals, default) | light
accent_override: ""            # hex, for non-UNC clients
# Client logo shown on the cover and in every footer. Known clients (UNC Athletics)
# default automatically; set a path here for anyone else.
client_logo: ""
"""


@dataclass
class Project:
    root: Path
    cfg: dict[str, Any]

    @property
    def slug(self) -> str:
        return self.cfg.get("slug", self.root.name)

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    # --- gates ------------------------------------------------------------
    def gate_status(self, name: str) -> tuple[bool, str]:
        """(approved, message). A gate is open only when a human wrote APPROVED in it."""
        gate = GATES[name]
        f = self.path(gate["file"])
        if not f.exists():
            return False, f"Gate '{name}' not yet created ({gate['file']})."
        text = f.read_text()
        for line in text.splitlines():
            s = line.strip().lower()
            if s.startswith("status:"):
                val = s.split(":", 1)[1].strip()
                if val.startswith("approved"):
                    return True, f"Gate '{name}' approved."
                return False, f"Gate '{name}' is '{val}' - not approved."
        return False, f"Gate '{name}' has no 'Status:' line."

    def require_gate(self, name: str) -> None:
        ok, msg = self.gate_status(name)
        if not ok:
            raise SystemExit(
                f"\nBLOCKED: {msg}\n"
                f"  Question to answer: {GATES[name]['question']}\n"
                f"  Review {self.path(GATES[name]['file'])}, then set 'Status: APPROVED'.\n"
                f"  To bypass deliberately (and record that you did): add --force.\n"
            )

    NOTES_HEADING = "## Analyst notes"
    NOTES_PLACEHOLDER = "_(what you changed, what you disagree with, what to watch)_"
    BODY_SEPARATOR = "\n---\n\n"

    def _existing_gate_notes(self, f: Path) -> tuple[str, str]:
        """(notes, previous status) from a gate file that is being regenerated.

        Regenerating a gate used to overwrite it wholesale, which threw away everything
        the analyst had written the moment anything upstream was re-run. The notes are
        the most expensive text in the project and the least reproducible.
        """
        if not f.exists():
            return "", ""
        text = f.read_text()
        status = ""
        for line in text.splitlines():
            if line.startswith("Status:"):
                status = line.split(":", 1)[1].strip()
                break
        if self.NOTES_HEADING not in text:
            return "", status
        after = text.split(self.NOTES_HEADING, 1)[1]
        notes = after.split(self.BODY_SEPARATOR, 1)[0]
        if self.NOTES_PLACEHOLDER in notes or not notes.strip():
            return "", status
        return notes.strip("\n"), status

    def write_gate(self, name: str, body: str) -> Path:
        """Create - or regenerate - the review file an analyst signs off in.

        Analyst notes are always carried forward. The approval is NOT: the gate exists
        so a human signs off on a specific analysis, and regenerating means that
        analysis changed, so a prior APPROVED is stale by definition. The previous
        status is recorded rather than dropped, so nothing is lost silently.
        """
        gate = GATES[name]
        f = self.path(gate["file"])
        f.parent.mkdir(parents=True, exist_ok=True)
        prior_notes, prior_status = self._existing_gate_notes(f)

        stale = ""
        if prior_status and prior_status.upper() != "PENDING":
            stale = (
                f"Previous status: {prior_status} (reset {_dt.datetime.now():%Y-%m-%d %H:%M}: "
                f"the analysis below was regenerated, so that sign-off no longer "
                f"covers it)\n"
            )
        notes_block = prior_notes if prior_notes else f"_{self.NOTES_PLACEHOLDER[1:-1]}_"
        if prior_notes:
            notes_block = (
                "> Carried over from the previous run. Check it against the regenerated\n"
                "> analysis below - finding ids and numbers may have moved.\n\n"
                + prior_notes
            )
        header = (
            f"# Human review gate: {name}\n\n"
            f"**Question:** {gate['question']}\n\n"
            f"**Created:** {_dt.datetime.now():%Y-%m-%d %H:%M}\n\n"
            f"Status: PENDING\n"
            f"{stale}"
            f"Reviewer: \n\n"
            f"> Change `Status:` to `APPROVED` once you have read the section below and\n"
            f"> made any edits you need. Write your notes under 'Analyst notes'.\n\n"
            f"{self.NOTES_HEADING}\n\n{notes_block}\n"
            f"{self.BODY_SEPARATOR}"
        )
        f.write_text(header + body)
        return f


def load(slug_or_path: str) -> Project:
    p = Path(slug_or_path)
    if not p.exists():
        p = config.PROJECTS_DIR / slug_or_path
    if not p.exists():
        raise SystemExit(f"No such project: {slug_or_path}")
    cfg_file = p / "project.yaml"
    if not cfg_file.exists():
        raise SystemExit(f"Missing {cfg_file}")
    with cfg_file.open() as fh:
        cfg = yaml.safe_load(fh) or {}
    return Project(root=p, cfg=cfg)


def create(slug: str, title: str = "", client: str = "UNC Athletics",
           question: str = "", audience: str = "", term: str = "",
           cycle: str = "1") -> Project:
    root = config.PROJECTS_DIR / util.slugify(slug)
    if root.exists():
        raise SystemExit(f"Project already exists: {root}")
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
        (root / sub / ".gitkeep").touch()

    now = _dt.datetime.now()
    term = term or f"{'Fall' if now.month >= 7 else 'Spring'} {now.year}"
    def q(v):  # keep values safe inside double-quoted YAML scalars
        return str(v).replace('\\', '\\\\').replace('"', '\\"')

    (root / "project.yaml").write_text(
        PROJECT_TEMPLATE.format(
            slug=util.slugify(slug),
            title=q(title or slug),
            client=q(client),
            term=q(term),
            cycle=q(cycle),
            question=question or "TODO: the one question this cycle answers.",
            audience=q(audience or "UNC Athletics leadership"),
        )
    )
    (root / "README.md").write_text(
        f"# {title or slug}\n\n"
        f"Client: {client} | {term} | Cycle {cycle}\n\n"
        "1. Drop raw data in `data/raw/` (it is never modified).\n"
        "2. Fill in `project.yaml` - especially `business_question` and `segments`.\n"
        "3. Run `cscg run <slug>` and work through the four review gates.\n"
    )
    return load(str(root))
