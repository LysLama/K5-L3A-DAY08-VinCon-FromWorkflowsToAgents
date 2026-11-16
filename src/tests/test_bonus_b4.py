"""Tests for Bonus B4: fair baselines, ablations, and stdlib statistical helpers."""

from __future__ import annotations

import math
import time
from pathlib import Path

import pytest

from bonus.b4_shapes import (
    orchestrator_no_history_inv,
    rules_only,
    swarm_pruned,
    workflow_trust_ticket,
)
from bonus.run_b4 import build_report
from bonus.stats import bootstrap_pass_rate_ci, paired_mcnemar, paired_sign_test
from lab8.config_loader import repo_path
from lab8.db import connect, init_store
from lab8.durability import InjectedCrash
from lab8.metrics import trial_pass
from lab8.shapes.orchestrator import run_claim as run_orchestrator
from tests.conftest import BY_ID, CLAIMS, WORLD


def _store(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    init_store(path, WORLD, CLAIMS).close()
    return path


@pytest.mark.parametrize("claim_id", ["C-001", "C-002", "C-004", "C-005", "C-007", "C-013", "C-014"])
def test_rules_only_baseline_uses_zero_model_calls_and_passes(tmp_path: Path, claim_id: str):
    store = _store(tmp_path, f"rules-{claim_id}.sqlite")
    started = time.time()
    result = rules_only(claim_id, seed=55, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(result.as_dict(), BY_ID[claim_id]["expected"], conn, started_at=started)
    finally:
        conn.close()
    assert passed, reason
    assert result.model_calls == 0


def test_rules_only_crash_and_resume_stays_safe(tmp_path: Path):
    store = _store(tmp_path, "rules-crash.sqlite")
    with pytest.raises(InjectedCrash):
        rules_only("C-012", seed=11, store_path=str(store), crash_at="after_effect_before_checkpoint")
    resumed = rules_only("C-012", seed=11, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(resumed.as_dict(), BY_ID["C-012"]["expected"], conn)
        rows = conn.execute("SELECT COUNT(*) AS n FROM refund_ledger WHERE claim_id = 'C-012'").fetchone()["n"]
    finally:
        conn.close()
    assert passed, reason
    assert rows == 1


def test_swarm_pruned_is_seed_deterministic_and_preserves_host_safety(tmp_path: Path):
    store_a = _store(tmp_path, "sp-a.sqlite")
    store_b = _store(tmp_path, "sp-b.sqlite")
    res_a = swarm_pruned("C-007", seed=11, store_path=str(store_a))
    res_b = swarm_pruned("C-007", seed=11, store_path=str(store_b))
    assert res_a.status == "denied"
    assert res_a.proposal_amount == 35000
    assert res_a.model_calls == res_b.model_calls
    assert res_a.cost_estimate == res_b.cost_estimate
    assert res_a.model_calls <= 3  # peer/parse can only prune, never add calls

    esc_store = _store(tmp_path, "sp-esc.sqlite")
    esc = swarm_pruned("C-005", seed=55, store_path=str(esc_store))
    conn = connect(esc_store)
    try:
        passed, reason = trial_pass(esc.as_dict(), BY_ID["C-005"]["expected"], conn)
    finally:
        conn.close()
    assert passed, reason


def test_orchestrator_ablation_without_second_investigator_still_passes_cap_cases(tmp_path: Path):
    for claim_id in ("C-013", "C-014"):
        store_full = _store(tmp_path, f"full-{claim_id}.sqlite")
        store_abl = _store(tmp_path, f"abl-{claim_id}.sqlite")
        full = run_orchestrator(claim_id, seed=11, store_path=str(store_full))
        abl = orchestrator_no_history_inv(claim_id, seed=11, store_path=str(store_abl))
        conn = connect(store_abl)
        try:
            passed, reason = trial_pass(abl.as_dict(), BY_ID[claim_id]["expected"], conn)
        finally:
            conn.close()
        assert passed, reason
        assert abl.cost_estimate < full.cost_estimate
        assert abl.model_calls < full.model_calls


def test_workflow_trust_ticket_ablation_misses_t02_but_cannot_bypass_host(tmp_path: Path):
    store_t02 = _store(tmp_path, "wtt-t02.sqlite")
    t02 = workflow_trust_ticket("C-002", seed=11, store_path=str(store_t02))
    assert t02.status == "resolved"  # fails business rule by trusting ticket 5 days

    store_t07 = _store(tmp_path, "wtt-t07.sqlite")
    t07 = workflow_trust_ticket("C-007", seed=11, store_path=str(store_t07))
    conn = connect(store_t07)
    try:
        passed, reason = trial_pass(t07.as_dict(), BY_ID["C-007"]["expected"], conn)
    finally:
        conn.close()
    assert passed, reason  # expired approval still blocked by host


def test_stdlib_stats_cluster_bootstrap_mcnemar_and_sign_test():
    # Cluster bootstrap: 10 claims x 2 seeds, 9 claims pass both seeds, 1 fails both.
    trials = []
    for idx in range(10):
        cid = f"C-{idx:02d}"
        ok = idx != 0
        for seed in (11, 22):
            trials.append({"shape": "A", "claim_id": cid, "seed": seed, "passed": ok, "cost_estimate": 10.0})
            trials.append({"shape": "B", "claim_id": cid, "seed": seed, "passed": idx >= 3, "cost_estimate": 20.0})

    ci_a = bootstrap_pass_rate_ci(trials, shape="A", n_boot=1000, seed=7)
    assert ci_a["pass_rate"] == 0.9
    assert 0.6 <= ci_a["ci_low"] <= 0.9 <= ci_a["ci_high"] <= 1.0

    # Paired McNemar: A passes & B fails on claims 1 and 2 across 2 seeds -> a_only=4, b_only=0.
    mc = paired_mcnemar(trials, "A", "B")
    assert (mc["a_only_pass"], mc["b_only_pass"]) == (4, 0)
    assert math.isclose(mc["p_value_exact"], 2.0 * (0.5 ** 4), rel_tol=1e-9)

    # Paired sign test on cost: A (10.0) < B (20.0) on all 20 pairs.
    cs = paired_sign_test(trials, "A", "B", metric="cost_estimate")
    assert (cs["a_less"], cs["a_greater"], cs["ties"]) == (20, 0, 0)
    assert math.isclose(cs["p_value_exact"], 2.0 * (0.5 ** 20), rel_tol=1e-9)


def test_b4_report_builder_produces_valid_structure(tmp_path: Path):
    from lab8.shapes import SHAPES

    subset_claims = tmp_path / "claims.jsonl"
    raw_lines = repo_path("data", "public_claims.jsonl").read_text(encoding="utf-8").splitlines()
    subset_claims.write_text("\n".join(raw_lines[:2]) + "\n", encoding="utf-8")
    report = build_report(
        cases_path=subset_claims,
        world_path=repo_path("data", "public_world_state.json"),
        seeds=[11, 55],
        n_boot=200,
    )
    assert set(SHAPES) == {"workflow", "single", "orchestrator", "swarm"}
    assert set(report["by_shape"]) >= {"workflow", "rules_only", "swarm", "swarm_pruned"}
    assert all(safe["secret_leak_count"] == 0 for safe in report["safety_by_shape"].values())
    assert all(safe["approval_bypass_count"] == 0 for safe in report["safety_by_shape"].values())
