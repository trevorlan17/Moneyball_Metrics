"""Analyst-declared facts.

The pipeline's normal path computes every number from data. But a deck is often built
from material that already exists: a written insight carrying a number, a client-supplied
figure, a published benchmark, a chart someone made in Excel.

Those numbers still have to be citable, or the claim linter has nothing to check and the
deck's central guarantee quietly lapses. This module turns declared facts into Findings
so they travel through the same machinery - with one difference that is never hidden:
`verified: false`. A declared number is only as good as the source attached to it, and
the deck says so.

Input: `analysis/declared.yaml`

    facts:
      - id: D_grad_awareness          # optional; derived from the label if omitted
        label: "Grad students who didn't know how to get tickets"
        value: 0.56                   # proportion, count, mean or correlation
        metric: percent               # percent | count | mean | correlation
        base: 99                      # n behind the number - REQUIRED
        base_definition: "Grad/professional respondents naming a barrier"
        source: "CSCG ticketing survey, fielded Sep 29 - Oct 3 2026, Q12"
        note: "Self-reported."
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import util
from .findings import Finding, FindingStore, Group

REQUIRED = ("label", "value", "source", "base")


def load_declared(path: Path) -> list[dict[str, Any]]:
    with Path(path).open() as fh:
        doc = yaml.safe_load(fh) or {}
    facts = doc.get("facts") or []
    problems = []
    for i, f in enumerate(facts, 1):
        missing = [k for k in REQUIRED if f.get(k) in (None, "")]
        if missing:
            problems.append(f"fact {i} ({f.get('label', 'unlabelled')}): missing {', '.join(missing)}")
    if problems:
        raise SystemExit(
            "Declared facts are incomplete. Every declared number needs a base and a\n"
            "source - a number without them cannot go on a client slide:\n  "
            + "\n  ".join(problems))
    return facts


def to_findings(facts: list[dict[str, Any]], store: FindingStore,
                run_meta: dict[str, Any]) -> list[Finding]:
    """Add declared facts to a store. Re-running replaces them rather than duplicating."""
    store.drop_kind("declared")
    out = []
    for f in facts:
        fid = f.get("id") or "D_" + util.slugify(f["label"])[:28]
        metric = f.get("metric", "percent")
        value = float(f["value"])
        base = int(f["base"])
        count = int(round(value * base)) if metric == "percent" else None
        finding = Finding(
            id=fid,
            kind="declared",
            metric=metric,
            question_id=fid,
            question_text=f["label"],
            base_definition=f.get("base_definition") or f"n={base}",
            groups=[Group(label=f["label"], n=base, value=value, count=count,
                          directional_only=base < 30)],
            overall_n=base,
            overall_value=value,
            caveats=[
                "Analyst-declared, not computed by this pipeline. Verified only by the "
                "source recorded on the finding.",
            ] + ([f["note"]] if f.get("note") else []),
            tags=["declared", "unverified"],
            provenance={
                "code": "cscg.declare",
                "verified": False,
                "source": f["source"],
                **run_meta,
            },
        )
        out.append(store.add(finding))
    return out


def run(project, force: bool = False) -> dict[str, Any]:
    path = project.path("analysis/declared.yaml")
    if not path.exists():
        raise SystemExit(
            f"No {path}.\n"
            "Declare the facts your written insights rely on, with a base and a source "
            "for each. See docs/ or templates/declared_example.yaml.")
    facts = load_declared(path)

    fpath = project.path("analysis/findings.json")
    store = FindingStore.load(fpath) if fpath.exists() else FindingStore()
    added = to_findings(facts, store, {"run_id": util.run_id(project.slug)})
    store.save(fpath, {"note": "includes analyst-declared facts (verified: false)"})

    lines = [
        f"# Declared facts - {project.cfg.get('title', project.slug)}",
        "",
        f"{len(added)} facts declared by the analyst rather than computed from data.",
        "",
        "These are citable on slides so the claim linter can check them, but they carry "
        "`verified: false`. Each one is only as good as its source. The red-team review "
        "should check every one against that source.",
        "",
        "| ID | Fact | Value | Base | Source |",
        "|---|---|---|---|---|",
    ]
    for f, raw in zip(added, facts):
        v = util.pct(f.overall_value) if f.metric == "percent" else f"{f.overall_value:g}"
        lines.append(f"| `{f.id}` | {f.question_text} | {v} | n={f.overall_n} | {raw['source']} |")
    lines.append("")
    project.path("analysis/declared.md").write_text("\n".join(lines))
    return {"declared": len(added), "ids": [f.id for f in added]}
