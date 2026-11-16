"""Standard-library statistics for fair multi-agent evaluation (Bonus B4).

Implements cluster bootstrap confidence intervals (resampled by claim_id so
seeds within the same claim stay grouped) and paired hypothesis tests
(exact two-sided McNemar test and exact paired sign test) using only the
Python standard library.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Linearly interpolated percentile on an already sorted non-empty list."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = pct * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    weight = pos - lo
    return sorted_vals[lo] * (1.0 - weight) + sorted_vals[hi] * weight


def _two_sided_binomial_p(k: int, n: int) -> float:
    """Exact two-sided p-value for Binom(n, 0.5) at tail count k <= n/2."""
    if n <= 0:
        return 1.0
    k = min(k, n - k)
    if n <= 1000:
        tail = math.ldexp(sum(math.comb(n, i) for i in range(k + 1)), -n)
    else:
        log_half_n = n * math.log(2.0)
        log_fact_n = math.lgamma(n + 1)
        tail = sum(
            math.exp(log_fact_n - math.lgamma(i + 1) - math.lgamma(n - i + 1) - log_half_n)
            for i in range(k + 1)
        )
    return min(1.0, 2.0 * tail)


def bootstrap_pass_rate_ci(
    trials: list[dict[str, Any]],
    *,
    shape: str,
    n_boot: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Compute a cluster bootstrap CI for pass_rate, resampling by claim_id."""
    by_claim: dict[str, list[bool]] = defaultdict(list)
    for row in trials:
        if row.get("shape") != shape or row.get("passed") is None:
            continue
        by_claim[str(row["claim_id"])].append(bool(row["passed"]))

    claim_ids = sorted(by_claim)
    if not claim_ids:
        return {
            "shape": shape,
            "n_claims": 0,
            "n_trials": 0,
            "pass_rate": None,
            "ci_low": None,
            "ci_high": None,
            "alpha": alpha,
            "n_boot": n_boot,
        }

    clusters = [by_claim[cid] for cid in claim_ids]
    total_trials = sum(len(c) for c in clusters)
    observed = sum(sum(1 for ok in c if ok) for c in clusters) / total_trials

    rng = random.Random(seed)
    boot_rates: list[float] = []
    n_clusters = len(clusters)
    for _ in range(n_boot):
        sampled = [clusters[rng.randrange(n_clusters)] for _ in range(n_clusters)]
        denom = sum(len(c) for c in sampled)
        numer = sum(sum(1 for ok in c if ok) for c in sampled)
        boot_rates.append(numer / denom)

    boot_rates.sort()
    return {
        "shape": shape,
        "n_claims": n_clusters,
        "n_trials": total_trials,
        "pass_rate": observed,
        "ci_low": _percentile(boot_rates, alpha / 2.0),
        "ci_high": _percentile(boot_rates, 1.0 - alpha / 2.0),
        "alpha": alpha,
        "n_boot": n_boot,
    }


def _pair_trials(
    trials: list[dict[str, Any]],
    shape_a: str,
    shape_b: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    map_a = {
        (str(r["claim_id"]), int(r["seed"])): r
        for r in trials
        if r.get("shape") == shape_a and r.get("passed") is not None
    }
    map_b = {
        (str(r["claim_id"]), int(r["seed"])): r
        for r in trials
        if r.get("shape") == shape_b and r.get("passed") is not None
    }
    keys = sorted(set(map_a) & set(map_b))
    return [(map_a[k], map_b[k]) for k in keys]


def paired_mcnemar(
    trials: list[dict[str, Any]],
    shape_a: str,
    shape_b: str,
) -> dict[str, Any]:
    """Run an exact two-sided McNemar test between two shapes on paired (claim_id, seed)."""
    pairs = _pair_trials(trials, shape_a, shape_b)
    n11 = n10 = n01 = n00 = 0
    for row_a, row_b in pairs:
        a_ok = bool(row_a["passed"])
        b_ok = bool(row_b["passed"])
        if a_ok and b_ok:
            n11 += 1
        elif a_ok and not b_ok:
            n10 += 1
        elif not a_ok and b_ok:
            n01 += 1
        else:
            n00 += 1

    discordant = n10 + n01
    p_exact = _two_sided_binomial_p(min(n10, n01), discordant)
    chi2_cc = ((abs(n10 - n01) - 1.0) ** 2 / discordant) if discordant > 0 and abs(n10 - n01) >= 1 else 0.0
    return {
        "shape_a": shape_a,
        "shape_b": shape_b,
        "n_pairs": len(pairs),
        "both_pass": n11,
        "a_only_pass": n10,
        "b_only_pass": n01,
        "both_fail": n00,
        "discordant": discordant,
        "p_value_exact": p_exact,
        "chi2_continuity_corrected": chi2_cc,
    }


def paired_sign_test(
    trials: list[dict[str, Any]],
    shape_a: str,
    shape_b: str,
    *,
    metric: str = "cost_estimate",
    tol: float = 1e-9,
) -> dict[str, Any]:
    """Exact paired sign test on a numeric metric (e.g., cost_estimate) across (claim_id, seed)."""
    pairs = _pair_trials(trials, shape_a, shape_b)
    n_a_gt_b = n_a_lt_b = n_ties = 0
    diffs: list[float] = []
    for row_a, row_b in pairs:
        va = float(row_a[metric])
        vb = float(row_b[metric])
        diff = va - vb
        diffs.append(diff)
        if abs(diff) <= tol:
            n_ties += 1
        elif diff > 0:
            n_a_gt_b += 1
        else:
            n_a_lt_b += 1

    non_ties = n_a_gt_b + n_a_lt_b
    p_exact = _two_sided_binomial_p(min(n_a_gt_b, n_a_lt_b), non_ties)
    return {
        "shape_a": shape_a,
        "shape_b": shape_b,
        "metric": metric,
        "n_pairs": len(pairs),
        "a_greater": n_a_gt_b,
        "a_less": n_a_lt_b,
        "ties": n_ties,
        "mean_diff_a_minus_b": (sum(diffs) / len(diffs)) if diffs else None,
        "p_value_exact": p_exact,
    }
