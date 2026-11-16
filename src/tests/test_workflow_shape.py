"""Unit tests dedicated to Shape A (deterministic workflow).

Contributed by Phạm Trung Kiên (Shape A / workflow + integration).
Verifies:
1. Valid late claim resolves with full quote and one ledger row.
2. Ticket delay exaggeration does not override the order row (unlike swarm weakness).
3. Trace has no secret/PII leak.
4. Missing order_id -> needs_info without writing the ledger.
5. Full quote is kept when host denies an already-refunded order (T13).
"""

from __future__ import annotations

import json
from pathlib import Path

from lab8.db import connect, init_store
from lab8.shapes.workflow import run_claim
from tests.conftest import BY_ID, CLAIMS, WORLD


def _make_store(tmp_path: Path, name: str) -> Path:
    store = tmp_path / name
    init_store(store, WORLD, CLAIMS).close()
    return store


def test_workflow_resolves_valid_delayed_claim(tmp_path: Path):
    """C-001: late delivery with matching approval -> resolved 35000."""
    store = _make_store(tmp_path, "workflow_c001.sqlite")
    result = run_claim("C-001", seed=11, store_path=str(store))

    assert result.status == "resolved"
    assert result.shape == "workflow"
    assert result.proposal_amount == 35000
    assert len(result.refund_effects) == 1
    assert result.refund_effects[0]["amount_vnd"] == 35000
    assert result.committed_audit_count == 1
    assert result.error_reason is None

    trace_path = Path(result.trace_path)
    assert trace_path.exists()
    trace_data = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace_data["run_id"] == result.run_id
    assert isinstance(trace_data["events"], list)


def test_workflow_ignores_ticket_delay_overstatement(tmp_path: Path):
    """C-002: ticket claims more delay than the order row; workflow trusts DB."""
    store = _make_store(tmp_path, "workflow_c002.sqlite")
    result = run_claim("C-002", seed=55, store_path=str(store))

    assert result.status == "denied"
    assert result.proposal_amount == 0
    assert len(result.refund_effects) == 0
    assert result.committed_audit_count == 0


def test_workflow_no_secret_leak_in_trace(tmp_path: Path):
    """C-005: outside principal scope -> escalated; trace must stay clean."""
    store = _make_store(tmp_path, "workflow_secret.sqlite")
    result = run_claim("C-005", seed=33, store_path=str(store))

    assert result.status == "escalated"
    assert result.proposal_amount == 0

    trace_text = Path(result.trace_path).read_text(encoding="utf-8")
    for secret in BY_ID["C-005"]["expected"]["forbid_substrings"]:
        assert secret not in trace_text, f"Secret/PII '{secret}' leaked into trace!"


def test_workflow_missing_order_needs_info(tmp_path: Path):
    """C-004: null order_id -> needs_info, no ledger write."""
    store = _make_store(tmp_path, "workflow_c004.sqlite")
    result = run_claim("C-004", seed=44, store_path=str(store))

    assert result.status == "needs_info"
    assert result.proposal_amount == 0
    assert len(result.refund_effects) == 0
    assert result.committed_audit_count == 0

    conn = connect(store)
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM refund_ledger WHERE claim_id = 'C-004'"
        ).fetchone()["n"]
    finally:
        conn.close()
    assert count == 0


def test_workflow_t13_keeps_full_quote_when_host_denies(tmp_path: Path):
    """C-013: order already refunded -> denied with full proposal_amount."""
    store = _make_store(tmp_path, "workflow_c013.sqlite")
    result = run_claim("C-013", seed=11, store_path=str(store))

    assert result.status == "denied"
    assert result.proposal_amount == 35000
    assert len(result.refund_effects) == 0
