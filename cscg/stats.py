"""Statistical primitives.

Every test the system runs lives here, so there is exactly one place where a p-value
can be produced. Tests are chosen by the shape of the data, not by what would be
impressive. Effect sizes are mandatory: a significant trivial difference is not a
finding.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sp

from . import config


@dataclass
class TestResult:
    name: str
    statistic: float | None
    p_value: float | None
    effect_name: str | None = None
    effect_value: float | None = None
    note: str | None = None


def _reading(effect_name: str, value: float) -> str:
    floors = config.rules()["testing"]["interpretation_floors"]
    key = {"cramers_v": "cramers_v", "cohens_d": "cohens_d", "r": "pearson_r",
           "pearson_r": "pearson_r", "spearman_rho": "pearson_r"}.get(effect_name)
    if key is None or key not in floors:
        return "unclassified"
    f = floors[key]
    v = abs(value)
    if v < f["negligible"]:
        return "negligible"
    if v < f["small"]:
        return "small"
    if v < f["moderate"]:
        return "moderate"
    return "large"


def cramers_v(table: np.ndarray) -> float:
    if (table.sum(axis=0) == 0).any() or (table.sum(axis=1) == 0).any():
        return float("nan")
    chi2 = sp.chi2_contingency(table, correction=False)[0]
    n = table.sum()
    if n == 0:
        return float("nan")
    k = min(table.shape) - 1
    return float(np.sqrt(chi2 / (n * k))) if k > 0 else float("nan")


def compare_proportions(counts: list[int], totals: list[int]) -> TestResult:
    """k-group comparison of a proportion.

    Chi-square by default; Fisher's exact for 2x2 when any expected cell is under 5,
    where chi-square is unreliable.
    """
    successes = np.asarray(counts, dtype=float)
    n = np.asarray(totals, dtype=float)
    failures = n - successes
    table = np.vstack([successes, failures])

    if (table < 0).any() or n.sum() == 0:
        return TestResult("none", None, None, note="degenerate table")
    if (table.sum(axis=0) == 0).any():
        return TestResult("none", None, None, note="empty group")
    if (table.sum(axis=1) == 0).any():
        # Every respondent gave the same answer, so there is nothing to compare.
        return TestResult("none", None, None,
                          note="no variation in the outcome: all or none in every group")

    expected = sp.contingency.expected_freq(table)
    use_fisher = table.shape[1] == 2 and (expected < 5).any()

    if use_fisher:
        odds, p = sp.fisher_exact(table.T)
        return TestResult("Fisher exact", float(odds), float(p),
                          "cramers_v", cramers_v(table),
                          note="expected cell < 5, chi-square not reliable")
    chi2, p, dof, _ = sp.chi2_contingency(table, correction=False)
    return TestResult("chi-square", float(chi2), float(p), "cramers_v", cramers_v(table))


def compare_means(groups: list[np.ndarray]) -> TestResult:
    """Two groups: Welch t-test (no equal-variance assumption). k>2: Welch ANOVA
    approximated by one-way ANOVA with a note, plus Kruskal-Wallis as a check."""
    groups = [np.asarray(g, dtype=float) for g in groups]
    groups = [g[np.isfinite(g)] for g in groups]
    if any(len(g) < 2 for g in groups):
        return TestResult("none", None, None, note="a group has fewer than 2 values")

    if len(groups) == 2:
        a, b = groups
        t, p = sp.ttest_ind(a, b, equal_var=False)
        # Cohen's d with pooled SD
        na, nb = len(a), len(b)
        sp_pool = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
        d = float((a.mean() - b.mean()) / sp_pool) if sp_pool > 0 else float("nan")
        return TestResult("Welch t-test", float(t), float(p), "cohens_d", d)

    f, p = sp.f_oneway(*groups)
    # eta-squared
    all_vals = np.concatenate(groups)
    grand = all_vals.mean()
    ss_between = sum(len(g) * (g.mean() - grand) ** 2 for g in groups)
    ss_total = ((all_vals - grand) ** 2).sum()
    eta2 = float(ss_between / ss_total) if ss_total > 0 else float("nan")
    return TestResult("one-way ANOVA", float(f), float(p), "eta_squared", eta2,
                      note="verify group variances before reading this strongly")


def compare_ordinal(groups: list[np.ndarray]) -> TestResult:
    """Rank-based comparison for ordinal scales, where means are not strictly meaningful."""
    groups = [np.asarray(g, dtype=float) for g in groups]
    groups = [g[np.isfinite(g)] for g in groups]
    if any(len(g) < 3 for g in groups):
        return TestResult("none", None, None, note="group too small for a rank test")
    if len(groups) == 2:
        u, p = sp.mannwhitneyu(groups[0], groups[1], alternative="two-sided")
        n1, n2 = len(groups[0]), len(groups[1])
        # rank-biserial correlation
        rb = float(1 - (2 * u) / (n1 * n2))
        return TestResult("Mann-Whitney U", float(u), float(p), "rank_biserial", abs(rb))
    h, p = sp.kruskal(*groups)
    return TestResult("Kruskal-Wallis", float(h), float(p))


def correlate(x: np.ndarray, y: np.ndarray, method: str = "pearson") -> TestResult:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 10:
        return TestResult("none", None, None, note="fewer than 10 complete pairs")
    if method == "spearman":
        r, p = sp.spearmanr(x, y)
        return TestResult("Spearman rho", float(r), float(p), "spearman_rho", float(r))
    r, p = sp.pearsonr(x, y)
    return TestResult("Pearson r", float(r), float(p), "pearson_r", float(r))


def benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    """BH-adjusted p-values, preserving None for tests that did not run.

    This is the single most important correction in survey work: run forty crosstabs
    and two will clear p<0.05 by chance alone.
    """
    idx = [i for i, p in enumerate(p_values) if p is not None and np.isfinite(p)]
    if not idx:
        return list(p_values)
    ps = np.array([p_values[i] for i in idx], dtype=float)
    m = len(ps)
    order = np.argsort(ps)
    ranked = ps[order]
    adj = ranked * m / (np.arange(1, m + 1))
    # enforce monotonicity from the largest p downwards
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    adj = np.clip(adj, 0, 1)
    out = list(p_values)
    for pos, orig_i in enumerate(order):
        out[idx[orig_i]] = float(adj[pos])
    return out


def effect_reading(name: str | None, value: float | None) -> str | None:
    if name is None or value is None or not np.isfinite(value):
        return None
    return _reading(name, value)
