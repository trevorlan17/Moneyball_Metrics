"""The findings store.

This is the spine of the system. Every number that can ever appear on a slide is
computed here in Python and stored as a Finding with a stable ID, its base, the test
that was run, and where it came from. Agents may reference finding IDs and phrase them
in English; agents may never produce a number that is not in this store.

cscg/verify.py enforces that by re-extracting every number from the built deck and
matching it back against these records.
"""
from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import config, util


# Suffixes that carry no information in an id. `_band` and `_view` are deliberately NOT
# here: they are what distinguishes a derived band from the column it was derived from,
# and collapsing them makes `student_section_view` collide with
# `sat_student_section_energy` - two different analyses under one id.
_ID_DROP = ("_actual", "_score", "_pct")
_ID_PREFIX = ("sat_", "imp_")


def _id_part(text: Any, cap: int = 22) -> str:
    """One readable segment of a stable id: slugified, de-boilerplated, length-capped."""
    if text is None or not str(text).strip():
        return ""          # slugify() substitutes "x" for empty; an id should just omit it
    s = util.slugify(text)
    for p in _ID_PREFIX:
        if s.startswith(p):
            s = s[len(p):]
            break
    for suffix in _ID_DROP:
        if s.endswith(suffix) and len(s) > len(suffix) + 2:
            s = s[: -len(suffix)]
    if len(s) <= cap:
        return s
    # Trim on a word boundary; a half-word is worse than a shorter name.
    kept: list[str] = []
    for w in s.split("_"):
        if kept and sum(len(x) + 1 for x in kept) + len(w) > cap:
            break
        kept.append(w)
    return "_".join(kept)


@dataclass
class Group:
    """One reported group within a finding."""
    label: str
    n: int
    value: float                 # proportion (0-1) or a mean, per `metric`
    count: int | None = None     # numerator, when the value is a proportion
    directional_only: bool = False   # n below the small-group threshold
    suppressed: bool = False         # n below the suppression threshold


@dataclass
class Test:
    name: str
    statistic: float | None = None
    p_raw: float | None = None
    p_adj: float | None = None
    adjustment: str | None = None
    effect_name: str | None = None
    effect_value: float | None = None
    effect_reading: str | None = None    # negligible / small / moderate / large
    note: str | None = None


@dataclass
class Finding:
    """A single computed result.

    `callable_difference` is the gate that matters: it is True only when the
    difference passed a real test AND cleared the minimum practical gap. Only
    findings with callable_difference=True may be asserted as a difference in a
    slide title or the executive summary.
    """
    id: str
    kind: str                    # proportion_by_segment | ranked_items | distribution | correlation | mean_by_segment | overall_proportion | theme_prevalence
    metric: str                  # percent | mean | correlation | count
    question_id: str
    question_text: str
    base_definition: str
    groups: list[Group] = field(default_factory=list)
    overall_n: int | None = None
    overall_value: float | None = None
    test: Test | None = None
    gap_pp: float | None = None          # largest between-group gap, percentage points
    callable_difference: bool = False
    flags: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    # --- values a claim may legitimately cite -----------------------------
    def citable_values(self) -> list[tuple[str, float]]:
        """[(kind, value)] a slide may state on the strength of this finding.

        The kinds matter. An effect size, a correlation and a proportion are all
        dimensionless numbers between 0 and 1, so an untyped set lets a fabricated
        "14%" match a Cramer's V of 0.14 and slip through. Slide text is matched only
        against values of a compatible kind.

        kinds: proportion | mean | count | correlation | effect | gap_pp
        """
        out: list[tuple[str, float]] = []
        value_kind = {"percent": "proportion", "mean": "mean",
                      "correlation": "correlation", "count": "count"}.get(
                          self.metric, "mean")
        for g in self.groups:
            if self.metric != "count":
                out.append((value_kind, float(g.value)))
            # else: a theme's share of comments or sessions is deliberately NOT citable.
            # analysis_rules.qualitative forbids expressing it as a percentage, so the
            # store simply never offers it as one.
            out.append(("count", float(g.n)))
            if g.count is not None:
                out.append(("count", float(g.count)))
        if self.overall_value is not None:
            out.append(("count" if self.metric == "count" else value_kind,
                        float(self.overall_value)))
            if self.metric == "correlation":
                # Rankings and slide text commonly use |r|; the sign lives in the
                # finding record and the source line.
                out.append(("correlation", abs(float(self.overall_value))))
        if self.overall_n is not None:
            out.append(("count", float(self.overall_n)))
        if self.gap_pp is not None:
            out.append(("gap_pp", float(self.gap_pp)))
        if self.test and self.test.effect_value is not None:
            out.append(("effect", float(self.test.effect_value)))
        return out

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        d = dict(d)
        d["groups"] = [Group(**g) for g in d.get("groups", [])]
        t = d.get("test")
        d["test"] = Test(**t) if t else None
        return cls(**d)

    # --- human-readable one-liner used in memos and agent prompts ---------
    def summary_line(self) -> str:
        if self.kind in ("proportion_by_segment", "mean_by_segment") and self.groups:
            parts = []
            for g in self.groups:
                v = util.pct(g.value) if self.metric == "percent" else f"{g.value:.2f}"
                mark = config.rules()["bases"]["small_group_marker"] if g.directional_only else ""
                parts.append(f"{g.label} {v} (n={g.n}){mark}")
            body = " vs ".join(parts)
        elif self.kind == "ranked_items":
            body = "; ".join(
                f"{g.label} {util.pct(g.value)}" for g in self.groups[:5]
            )
        elif self.kind == "correlation":
            body = f"r = {self.overall_value:.2f} (n={self.overall_n})"
        elif self.groups:
            body = "; ".join(f"{g.label} {util.pct(g.value)}" for g in self.groups)
        else:
            v = self.overall_value
            body = (util.pct(v) if self.metric == "percent" else f"{v}") if v is not None else ""
            body += f" (n={self.overall_n})"

        bits = [f"[{self.id}] {self.question_text}: {body}"]
        if self.test and self.test.p_adj is not None:
            bits.append(
                f"{self.test.name}, adj p={self.test.p_adj:.3f}"
                + (f", {self.test.effect_name}={self.test.effect_value:.2f}"
                   f" ({self.test.effect_reading})" if self.test.effect_value is not None else "")
            )
        bits.append("CALLABLE" if self.callable_difference else "not callable as a difference")
        if self.flags:
            bits.append("flags: " + ", ".join(self.flags))
        return " | ".join(bits)


class FindingStore:
    """Ordered collection of findings, persisted as analysis/findings.json."""

    def __init__(self, findings: Iterable[Finding] = ()) -> None:
        self._items: dict[str, Finding] = {f.id: f for f in findings}
        self._counter = len(self._items)

    # --- construction -----------------------------------------------------
    def next_id(self, prefix: str = "F") -> str:
        """Positional id. Deprecated: use `stable_id`.

        Kept only so an old findings.json still loads. A counter renumbers every
        downstream finding the moment one more correlation is declared, which silently
        repoints every `cites:` in a storyline that was written against the last run.
        """
        self._counter += 1
        return f"{prefix}{self._counter:03d}"

    def stable_id(self, *parts: str, prefix: str = "F") -> str:
        """An id derived from what the finding IS, not from when it was computed.

        Two properties matter, and they are the same two the theme findings already
        have (`Q_time_commitment`):

        1. **Stable across re-runs.** Declaring one more correlation must not move any
           other finding's id, or a storyline written yesterday cites the wrong thing
           today - and nothing downstream can detect it, because the citation still
           resolves.
        2. **Readable.** `F_renewed_actual_by_stated_intent_in_respondent` and
           `F_return_intent_by_leave_early_in_respondent` are hard to confuse in a
           `cites:` list. `F114` and `F117` are not, and citing the wrong one puts a
           finding under a claim it does not support.

        Collisions get a numeric suffix rather than raising, so a project that declares
        two genuinely identical analyses still runs.
        """
        body = "_".join(x for x in (_id_part(p) for p in parts) if x)
        base = f"{prefix}_{body}"[:72].rstrip("_")
        if base not in self._items:
            return base
        # Disambiguate from the full key, not from a counter. A counter would depend on
        # which of the colliding findings happened to be computed first, so reordering
        # project.yaml would swap two ids - exactly the instability this replaces.
        digest = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:4]
        return f"{base[:67]}_{digest}"

    def add(self, finding: Finding) -> Finding:
        if finding.id in self._items:
            raise ValueError(f"Duplicate finding id {finding.id}")
        self._items[finding.id] = finding
        return finding

    # --- access -----------------------------------------------------------
    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items.values())

    def __getitem__(self, fid: str) -> Finding:
        if fid not in self._items:
            raise KeyError(
                f"Unknown finding id '{fid}'. A slide cannot cite a finding that was "
                f"never computed. Known ids: {', '.join(sorted(self._items)[:10])}..."
            )
        return self._items[fid]

    def drop_kind(self, kind: str) -> int:
        """Remove every finding of a kind. Lets a stage be re-run idempotently."""
        doomed = [k for k, v in self._items.items() if v.kind == kind]
        for k in doomed:
            del self._items[k]
        return len(doomed)

    def get(self, fid: str) -> Finding | None:
        return self._items.get(fid)

    def callable_findings(self) -> list[Finding]:
        return [f for f in self if f.callable_difference]

    def by_tag(self, tag: str) -> list[Finding]:
        return [f for f in self if tag in f.tags]

    # --- persistence ------------------------------------------------------
    def save(self, path: Path, meta: dict[str, Any] | None = None) -> None:
        util.write_json(
            path,
            {
                "meta": meta or {},
                "count": len(self._items),
                "findings": [f.to_dict() for f in self._items.values()],
            },
        )

    @classmethod
    def load(cls, path: Path) -> "FindingStore":
        data = util.read_json(path)
        store = cls(Finding.from_dict(f) for f in data["findings"])
        store._counter = len(store._items)
        return store

    def as_briefing(self, only_callable: bool = False) -> str:
        """Plain-text rendering handed to the strategist and QA agents."""
        items = self.callable_findings() if only_callable else list(self)
        lines = [f"{len(items)} findings available.", ""]
        lines.extend(f.summary_line() for f in items)
        return "\n".join(lines)
