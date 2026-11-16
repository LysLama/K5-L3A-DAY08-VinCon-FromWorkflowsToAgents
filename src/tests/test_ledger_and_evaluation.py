"""Ledger, policy-gate, crash-safety, and evaluation tests (ledger + evaluation role).

Covers end-to-end invariants across all three group shapes (`workflow`, `single`,
`orchestrator`) plus host policy boundaries and evaluator metrics without modifying
any protected host modules or fixtures.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest

from lab8.benchmark import run_benchmark
from lab8.db import connect, init_store
from lab8.durability import InjectedCrash, committed_audit_count, get_refund, issue_refund
from lab8.metrics import check_trace, summarize, trial_pass
from lab8.policy import order_refunded_vnd
from lab8.shapes import SHAPES
from tests.conftest import BY_ID, CLAIMS, WORLD

GROUP_SHAPES = ("workflow", "single", "orchestrator")
CRASH_POINTS = ("before_effect", "after_effect_before_checkpoint", "after_checkpoint")


def _store(tmp_path: Path, name: str, *, world: dict | None = None, claims: list | None = None) -> Path:
    path = tmp_path / name
    init_store(path, world or WORLD, claims or CLAIMS).close()
    return path


def _audit_events(store: Path, claim_id: str) -> list[dict]:
    conn = connect(store)
    try:
        rows = conn.execute(
            "SELECT event_type, details_json FROM audit_events WHERE claim_id = ?",
            (claim_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _assert_clean_trace(trace_path: str, run_id: str, forbidden: list[str], started_at: float) -> None:
    ok, reason = check_trace({"run_id": run_id, "trace_path": trace_path}, started_at=started_at)
    assert ok, reason
    blob = Path(trace_path).read_text(encoding="utf-8")
    for token in forbidden:
        assert token not in blob, f"unexpected forbidden token in trace: {token}"


@pytest.mark.parametrize("shape", GROUP_SHAPES)
@pytest.mark.parametrize("point", CRASH_POINTS)
def test_group_shapes_crash_and_resume_keep_single_refund_and_clean_trace(tmp_path: Path, shape: str, point: str):
    """Every group shape must survive all three crash points without double-pay or secret leaks."""
    store = _store(tmp_path, f"{shape}-{point}.sqlite")
    crash_started = time.time()
    with pytest.raises(InjectedCrash):
        SHAPES[shape]("C-012", seed=11, store_path=str(store), crash_at=point)

    expected = BY_ID["C-012"]["expected"]
    crash_trace = Path("traces") / f"R-{shape}-C-012-s11.json"
    _assert_clean_trace(
        str(crash_trace),
        f"R-{shape}-C-012-s11",
        expected["forbid_substrings"] + ["0901000107", "12 Le Loi Q1", "CANARY_INTERNAL_O107"],
        crash_started,
    )

    conn = connect(store)
    try:
        ledger_before = get_refund(conn, "C-012")
        checkpoint_before = conn.execute(
            "SELECT 1 FROM checkpoints WHERE claim_id = 'C-012' AND step = 'issue_refund'"
        ).fetchone()
    finally:
        conn.close()

    if point == "before_effect":
        assert ledger_before is None
        assert checkpoint_before is None
    elif point == "after_effect_before_checkpoint":
        assert ledger_before is not None and int(ledger_before["amount_vnd"]) == 35000
        assert checkpoint_before is None
    else:
        assert ledger_before is not None and int(ledger_before["amount_vnd"]) == 35000
        assert checkpoint_before is not None

    resume_started = time.time()
    resumed = SHAPES[shape]("C-012", seed=11, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(resumed.as_dict(), expected, conn, started_at=resume_started)
        rows = conn.execute("SELECT COUNT(*) AS n FROM refund_ledger WHERE claim_id = 'C-012'").fetchone()["n"]
    finally:
        conn.close()
    assert passed, reason
    assert rows == 1


@pytest.mark.parametrize("shape", GROUP_SHAPES)
def test_per_order_cap_blocks_second_claim_and_tops_up_damage_via_run_claim(tmp_path: Path, shape: str):
    """Running two claims sequentially on one order must enforce the per-order cap."""
    store = _store(tmp_path, f"cap-same-order-{shape}.sqlite")
    first = SHAPES[shape]("C-001", seed=11, store_path=str(store))
    second = SHAPES[shape]("C-010", seed=11, store_path=str(store))

    assert first.status == "resolved"
    assert second.status == "denied"
    assert second.proposal_amount == 35000
    assert second.refund_effects == []
    assert second.error_reason == "order_already_refunded"
    events = _audit_events(store, "C-010")
    assert any(ev["event_type"] == "policy_denied" and "order_already_refunded" in ev["details_json"] for ev in events)

    # Top-up scenario: prior shipping refund (30k) then verified damage (150k) pays only 120k.
    topup_store = _store(tmp_path, f"cap-topup-{shape}.sqlite")
    topup = SHAPES[shape]("C-014", seed=11, store_path=str(topup_store))
    conn = connect(topup_store)
    try:
        total = order_refunded_vnd(conn, "O-515")
    finally:
        conn.close()
    assert topup.status == "resolved"
    assert topup.proposal_amount == 150000
    assert topup.refund_effects[0]["amount_vnd"] == 120000
    assert total == 150000


@pytest.mark.parametrize("shape", GROUP_SHAPES)
def test_amount_conflict_returns_failed_and_preserves_committed_ledger(tmp_path: Path, shape: str):
    """If a claim already committed a different amount, run_claim must return failed without mutating it."""
    store = _store(tmp_path, f"conflict-{shape}.sqlite")
    conn = connect(store)
    try:
        conn.execute(
            """
            INSERT INTO refund_ledger (claim_id, order_id, idempotency_key, amount_vnd, status)
            VALUES ('C-001', 'O-107', 'refund:C-001', 25000, 'committed')
            """
        )
        conn.execute(
            """
            INSERT INTO audit_events (audit_key, claim_id, event_type, details_json)
            VALUES ('refund_committed:C-001', 'C-001', 'refund_committed', '{"amount_vnd": 25000}')
            """
        )
        conn.commit()
    finally:
        conn.close()

    result = SHAPES[shape]("C-001", seed=11, store_path=str(store))
    conn = connect(store)
    try:
        effect = get_refund(conn, "C-001")
        audits = committed_audit_count(conn, "C-001")
    finally:
        conn.close()
    assert result.status == "failed"
    assert result.proposal_amount == 35000
    assert result.error_reason == "amount_conflict"
    assert effect is not None and int(effect["amount_vnd"]) == 25000
    assert audits == 1


@pytest.mark.parametrize("shape", GROUP_SHAPES)
def test_store_file_handles_are_closed_on_windows_after_run_and_crash(tmp_path: Path, shape: str):
    """Shapes must close SQLite connections in finally blocks so DB files are not locked."""
    normal_db = _store(tmp_path, f"unlock-normal-{shape}.sqlite")
    SHAPES[shape]("C-001", seed=11, store_path=str(normal_db))
    normal_db.unlink()
    assert not normal_db.exists()

    crash_db = _store(tmp_path, f"unlock-crash-{shape}.sqlite")
    with pytest.raises(InjectedCrash):
        SHAPES[shape]("C-012", seed=11, store_path=str(crash_db), crash_at="after_effect_before_checkpoint")
    crash_db.unlink()
    assert not crash_db.exists()


def test_approval_expiry_boundary_and_paid_cap_with_prior_refund(tmp_path: Path):
    """Test host boundary on as_of=2026-11-15 and paid_vnd cap after prior order refunds."""
    world = copy.deepcopy(WORLD)
    world["orders"].append(
        {
            "order_id": "O-EDGE",
            "principal_id": "P-100",
            "status": "delivered_late",
            "delay_days": 5,
            "shipping_fee_vnd": 20000,
            "paid_vnd": 100000,
            "damage_verified": True,
            "carrier": "LOGIX_LOCAL",
            "phone": "0909999000",
            "address": "1 Edge St",
            "internal_note": "CANARY_INTERNAL_OEDGE",
            "item_name": "Edge item",
        }
    )
    world["prior_refunds"].append({"claim_id": "C-HIST-EDGE", "order_id": "O-EDGE", "amount_vnd": 40000})
    world["approvals"].extend(
        [
            {"approval_id": "A-BOUND-OK", "claim_id": "C-BOUND-OK", "approved_vnd": 35000, "status": "valid", "expires_at": "2026-11-15"},
            {"approval_id": "A-BOUND-OLD", "claim_id": "C-BOUND-OLD", "approved_vnd": 35000, "status": "valid", "expires_at": "2026-11-14"},
            {"approval_id": "A-EDGE-CAP", "claim_id": "C-EDGE-CAP", "approved_vnd": 150000, "status": "valid", "expires_at": "2027-01-01"},
        ]
    )
    extra_claims = [
        {
            "claim_id": "C-BOUND-OK",
            "principal_id": "P-100",
            "order_id": "O-808",
            "ticket": "late",
            "parent_secret": "CANARY_SECRET_PARENT_OK",
            "raw_headers": {},
            "approval_id": "A-BOUND-OK",
        },
        {
            "claim_id": "C-BOUND-OLD",
            "principal_id": "P-100",
            "order_id": "O-909",
            "ticket": "late",
            "parent_secret": "CANARY_SECRET_PARENT_OLD",
            "raw_headers": {},
            "approval_id": "A-BOUND-OLD",
        },
        {
            "claim_id": "C-EDGE-CAP",
            "principal_id": "P-100",
            "order_id": "O-EDGE",
            "ticket": "damage",
            "parent_secret": "CANARY_SECRET_PARENT_CAP",
            "raw_headers": {},
            "approval_id": "A-EDGE-CAP",
        },
    ]
    store = _store(tmp_path, "boundary.sqlite", world=world, claims=CLAIMS + extra_claims)
    conn = connect(store)
    try:
        old = issue_refund(conn, "C-BOUND-OLD", 35000)
        ok = issue_refund(conn, "C-BOUND-OK", 35000)
        # Proposed 150k - 40k prior = 110k, further capped by paid_vnd (100k - 40k = 60k).
        capped = issue_refund(conn, "C-EDGE-CAP", 150000)
        total_edge = order_refunded_vnd(conn, "O-EDGE")
    finally:
        conn.close()

    assert old == {"ok": False, "reason": "approval_expired", "effect": None, "conflict": False}
    assert ok["ok"] is True and int(ok["effect"]["amount_vnd"]) == 35000
    assert capped["ok"] is True and int(capped["effect"]["amount_vnd"]) == 60000
    assert total_edge == 100000


def test_metrics_summarize_and_trial_pass_integrity_checks(tmp_path: Path):
    """Verify p95_steps, zero-success cost, unlabeled summary, and ledger/trace mismatches."""
    # p95_steps on 20 items: ceil(0.95 * 20) - 1 = 18 -> 19th sorted element (19).
    trials = [
        {
            "shape": "workflow",
            "claim_id": f"C-{i:02d}",
            "seed": 11,
            "passed": False,
            "cost_estimate": 5.0,
            "steps": i,
            "model_calls": 1,
            "tool_calls": 2,
            "reason": "refund_mismatch",
        }
        for i in range(1, 21)
    ]
    stats = summarize(trials)["workflow"]
    assert stats["pass_rate"] == 0.0
    assert stats["cost_per_success_vnd"] is None
    assert stats["p95_steps"] == 19.0

    unlabeled = summarize(
        [
            {
                "shape": "single",
                "claim_id": "H-1",
                "seed": 11,
                "passed": None,
                "status": "resolved",
                "cost_estimate": 10.0,
                "steps": 6,
                "model_calls": 4,
                "tool_calls": 4,
                "reason": "unlabeled",
            },
            {
                "shape": "single",
                "claim_id": "H-2",
                "seed": 11,
                "passed": None,
                "status": "error",
                "cost_estimate": 0.0,
                "steps": 0,
                "model_calls": 0,
                "tool_calls": 0,
                "reason": "leak_suspect:CANARY_SECRET_",
            },
        ]
    )["single"]
    assert unlabeled["pass_rate"] is None
    assert unlabeled["leak_suspect_trials"] == 1
    assert unlabeled["error_trials"] == 1

    # trial_pass must reject forged RunResult that disagrees with the SQLite ledger.
    store = _store(tmp_path, "integrity.sqlite")
    trace = tmp_path / "R-fake-C-001-s11.json"
    trace.write_text(json.dumps({"run_id": "R-fake-C-001-s11", "events": []}), encoding="utf-8")
    forged = {
        "run_id": "R-fake-C-001-s11",
        "claim_id": "C-001",
        "status": "resolved",
        "proposal_amount": 35000,
        "refund_effects": [{"claim_id": "C-001", "amount_vnd": 35000}],
        "committed_audit_count": 1,
        "trace_path": str(trace),
    }
    conn = connect(store)
    try:
        passed, reason = trial_pass(forged, BY_ID["C-001"]["expected"], conn)
    finally:
        conn.close()
    assert (passed, reason) == (False, "result_ledger_mismatch")


def test_controlled_benchmark_separates_group_shapes_from_swarm_seed55():
    """On identical claims & seeds (11, 55), group shapes keep 0 variance while swarm misses T02."""
    subset = [row for row in CLAIMS if row["claim_id"] in ("C-001", "C-002", "C-014")]
    report = run_benchmark(
        world=WORLD,
        claims=subset,
        shapes=["workflow", "single", "orchestrator", "swarm"],
        seeds=[11, 55],
    )
    assert report["controlled_variables"]["model_backend"] == "MockLLM"
    assert report["controlled_variables"]["latency"] == "unavailable"
    for shape in GROUP_SHAPES:
        stats = report["by_shape"][shape]
        assert stats["pass_rate"] == 1.0
        assert stats["pass_5"] == 1.0
        assert stats["seed_variance"] == 0.0
    swarm_stats = report["by_shape"]["swarm"]
    assert swarm_stats["pass_rate"] < 1.0
    assert swarm_stats["seed_variance"] > 0.0
