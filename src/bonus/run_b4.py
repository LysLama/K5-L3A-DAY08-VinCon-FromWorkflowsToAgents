"""Reproducible Bonus B4 runner: fair baselines, ablations, CI, and paired tests.

Usage (from src/):
    python -m bonus.run_b4 --out reports/bonus_ablation.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lab8.app import register_extra_shapes
from lab8.benchmark import LEAK_MARKERS, run_benchmark
from lab8.config_loader import repo_path
from lab8.console import utf8_stdio
from lab8.db import load_json, load_jsonl
from lab8.metrics import trace_files

from bonus.stats import bootstrap_pass_rate_ci, paired_mcnemar, paired_sign_test

EXTRA_SPECS = [
    "rules_only=bonus.b4_shapes:rules_only",
    "swarm_pruned=bonus.b4_shapes:swarm_pruned",
    "workflow_trust_ticket=bonus.b4_shapes:workflow_trust_ticket",
    "orchestrator_no_history_inv=bonus.b4_shapes:orchestrator_no_history_inv",
]

ALL_SHAPES = [
    "workflow",
    "rules_only",
    "workflow_trust_ticket",
    "single",
    "orchestrator",
    "orchestrator_no_history_inv",
    "swarm",
    "swarm_pruned",
]

COMPARISONS = [
    ("workflow", "swarm"),
    ("workflow", "rules_only"),
    ("workflow", "single"),
    ("workflow", "orchestrator"),
    ("workflow", "workflow_trust_ticket"),
    ("orchestrator", "orchestrator_no_history_inv"),
    ("swarm", "swarm_pruned"),
]


def _safety_summary(
    trials: list[dict[str, Any]],
    claims_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """Verify trace leak counts and approval-bypass risk counts per shape."""
    summary: dict[str, dict[str, int]] = {}
    for shape in ALL_SHAPES:
        subset = [row for row in trials if row["shape"] == shape]
        secret_leaks = 0
        approval_bypasses = 0
        error_trials = 0
        for row in subset:
            if row.get("status") == "error":
                error_trials += 1
            claim = claims_by_id[row["claim_id"]]
            expected = claim.get("expected") or {}
            if not expected.get("approval_ok", True):
                if row.get("status") == "resolved" or str(row.get("reason", "")).startswith("refund_mismatch"):
                    approval_bypasses += 1
            if str(row.get("reason", "")).startswith(("forbidden_substring", "leak_suspect")):
                secret_leaks += 1
                continue
            run_id = row.get("run_id") or ""
            files = trace_files({"run_id": run_id, "trace_path": f"traces/{run_id}.json"})
            blob = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in files)
            tokens = list(LEAK_MARKERS) + list(expected.get("forbid_substrings") or [])
            if any(tok and tok in blob for tok in tokens):
                secret_leaks += 1
        summary[shape] = {
            "approval_bypass_count": approval_bypasses,
            "secret_leak_count": secret_leaks,
            "error_trials": error_trials,
        }
    return summary


def build_report(
    *,
    cases_path: str | Path,
    world_path: str | Path,
    seeds: list[int],
    n_boot: int = 2000,
    boot_seed: int = 42,
) -> dict[str, Any]:
    from lab8.shapes import SHAPES

    missing_specs = [spec for spec in EXTRA_SPECS if spec.partition("=")[0] not in SHAPES]
    added = register_extra_shapes(missing_specs) if missing_specs else []
    try:
        world = load_json(world_path)
        claims = load_jsonl(cases_path)
        claims_by_id = {row["claim_id"]: row for row in claims}

        bench = run_benchmark(world=world, claims=claims, shapes=ALL_SHAPES, seeds=seeds)
    finally:
        for name in added:
            SHAPES.pop(name, None)

    trials = bench["trials"]
    safety = _safety_summary(trials, claims_by_id)

    bootstrap_ci = {
        shape: bootstrap_pass_rate_ci(trials, shape=shape, n_boot=n_boot, seed=boot_seed)
        for shape in ALL_SHAPES
    }
    mcnemar = [paired_mcnemar(trials, a, b) for a, b in COMPARISONS]
    cost_sign = [paired_sign_test(trials, a, b, metric="cost_estimate") for a, b in COMPARISONS]

    return {
        "controlled_variables": bench["controlled_variables"],
        "bootstrap_config": {"n_boot": n_boot, "seed": boot_seed, "cluster": "claim_id", "alpha": 0.05},
        "by_shape": bench["by_shape"],
        "safety_by_shape": safety,
        "bootstrap_95ci": bootstrap_ci,
        "paired_mcnemar": mcnemar,
        "paired_cost_sign_test": cost_sign,
        "trials": trials,
    }


def _render_summary(report: dict[str, Any]) -> str:
    lines = [
        f"{'shape':<28} {'pass':>6} {'95% CI (claim)':>18} {'pass^5':>7} {'var':>9} {'cost/ok':>9} {'bypass':>7} {'leak':>5}",
        "-" * 98,
    ]
    for shape in ALL_SHAPES:
        stats = report["by_shape"][shape]
        ci = report["bootstrap_95ci"][shape]
        safe = report["safety_by_shape"][shape]
        ci_str = f"[{ci['ci_low']:.3f}, {ci['ci_high']:.3f}]"
        cost = f"{stats['cost_per_success_vnd']:.2f}" if stats["cost_per_success_vnd"] is not None else "-"
        lines.append(
            f"{shape:<28} {stats['pass_rate']:>6.3f} {ci_str:>18} {stats['pass_5']:>7.3f} "
            f"{stats['seed_variance']:>9.6f} {cost:>9} {safe['approval_bypass_count']:>7} {safe['secret_leak_count']:>5}"
        )
    lines.append("")
    lines.append("Paired McNemar (pass/fail) & Cost Sign Test:")
    for mc, cs in zip(report["paired_mcnemar"], report["paired_cost_sign_test"]):
        lines.append(
            f"  {mc['shape_a']} vs {mc['shape_b']}: "
            f"McNemar(a_only={mc['a_only_pass']}, b_only={mc['b_only_pass']}, p={mc['p_value_exact']:.4f}) | "
            f"Cost diff={cs['mean_diff_a_minus_b']:+.2f} VND (p={cs['p_value_exact']:.2e})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(description="Run Bonus B4 baselines, ablations, and statistical tests")
    parser.add_argument("--cases", default=str(repo_path("data", "public_claims.jsonl")))
    parser.add_argument("--world", default=str(repo_path("data", "public_world_state.json")))
    parser.add_argument("--seeds", default="11,22,33,44,55")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--out", default="reports/bonus_ablation.json")
    args = parser.parse_args(argv)

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    report = build_report(cases_path=args.cases, world_path=args.world, seeds=seeds, n_boot=args.n_boot)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(_render_summary(report))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
