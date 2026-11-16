"""Shape B — one ReAct agent. Student work.

Use `lab8.runtime.run_react` with max_steps=8. `decide` may pick a read tool.
It must not call `issue_refund`. After the loop, the host validates the quote
and is the only writer.

A decide() that trusts ticket text over the order row will fail hidden claims
where the customer overstates the delay or cites a superseded clause.

Per-order cap: an order may already have been refunded by an earlier claim.
The read tool `lookup_refund_history` shows how much. The host still enforces
the cap, so pass the full quote to `durability.issue_refund`, not a net amount.

Caps: stop at 8 steps. Count model calls in the Budget so cost stays comparable.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.mock_llm import complete
from lab8.runtime import run_react
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish
from lab8.tools import get_claim_view, tool_cost


class _Trace:
    """Local wrapper for trace so crash can flush before raising."""

    def __init__(self, run_id: str) -> None:
        from lab8.trace import Trace

        self._inner = Trace(run_id)

    def add(self, kind: str, payload: dict[str, Any]) -> None:
        self._inner.add(kind, payload)

    def write(self) -> str:
        return self._inner.write()

    @property
    def run_id(self) -> str:
        return self._inner.run_id


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(
    conn: sqlite3.Connection,
    claim_id: str,
    *,
    seed: int,
    crash_at: str | None,
) -> RunResult:
    budget = Budget()
    run_id = make_run_id("single", claim_id, seed)
    trace = _Trace(run_id)

    claim = get_claim_view(conn, claim_id)
    budget.add_tool(tool_cost())

    if not claim.get("found"):
        trace.add("error", {"reason": "unknown_claim"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="failed",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason="unknown_claim",
        )

    if not claim.get("order_id"):
        complete(budget, seed=seed, purpose="draft", prompt="needs_info")
        trace.add("decision", {"status": "needs_info"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="needs_info",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason="missing_order_id",
        )

    order_data: dict[str, Any] | None = None
    step_num = 0

    def decide(seen: dict[str, Any]) -> dict[str, Any]:
        nonlocal order_data, step_num
        step_num += 1

        if "last_tool" not in seen:
            complete(budget, seed=seed, purpose="react_step", prompt="lookup_order")
            trace.add("thought", {"step": step_num, "action": "lookup_order"})
            return {
                "tool": "lookup_order",
                "args": {
                    "order_id": claim.get("order_id"),
                    "principal_id": claim.get("principal_id"),
                },
            }

        last_tool = seen.get("last_tool")
        last_result = seen.get("last_result") or {}

        if last_tool == "lookup_order":
            if not last_result.get("visible"):
                complete(budget, seed=seed, purpose="react_step", prompt="order_not_visible")
                trace.add("thought", {"step": step_num, "action": "escalate", "reason": last_result.get("reason")})
                return {
                    "final": {
                        "status": "escalated",
                        "proposal_amount": 0,
                        "error_reason": last_result.get("reason"),
                    }
                }
            order_data = dict(last_result.get("order") or {})
            trace.add("order_view", {"visible": True, "order_id": order_data.get("order_id")})
            complete(budget, seed=seed, purpose="react_step", prompt="lookup_refund_history")
            trace.add("thought", {"step": step_num, "action": "lookup_refund_history"})
            return {
                "tool": "lookup_refund_history",
                "args": {
                    "order_id": order_data.get("order_id"),
                    "principal_id": claim.get("principal_id"),
                },
            }

        if last_tool == "lookup_refund_history":
            trace.add(
                "refund_history",
                {
                    "refund_count": last_result.get("refund_count"),
                    "refunded_vnd": last_result.get("refunded_vnd"),
                },
            )
            complete(budget, seed=seed, purpose="react_step", prompt="compute_compensation")
            trace.add("thought", {"step": step_num, "action": "compute_compensation"})
            return {
                "tool": "compute_compensation",
                "args": {"order": order_data},
            }

        if last_tool == "compute_compensation":
            quote_payload = last_result
            proposal = int(quote_payload.get("amount_vnd", 0))
            trace.add("quote", quote_payload)
            complete(budget, seed=seed, purpose="react_step", prompt=f"quote_result={proposal}")
            if proposal <= 0:
                return {
                    "final": {
                        "status": "denied",
                        "proposal_amount": 0,
                        "error_reason": quote_payload.get("reason"),
                    }
                }
            return {
                "final": {
                    "status": "resolved",
                    "proposal_amount": proposal,
                    "error_reason": None,
                }
            }

        return {"final": {"status": "failed", "error_reason": "unexpected_react_state"}}

    react_outcome = run_react(
        conn,
        budget,
        observation={"claim": claim},
        decide=decide,
        max_steps=8,
        worker=True,
    )

    if react_outcome.get("stopped") == "step_cap":
        trace.add("error", {"reason": "step_cap"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="failed",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason="step_cap",
        )

    final_decision = react_outcome.get("final") or {}
    decision_status = final_decision.get("status")
    proposal = int(final_decision.get("proposal_amount", 0))

    if decision_status in ("needs_info", "escalated"):
        complete(budget, seed=seed, purpose="draft", prompt=decision_status)
        trace.add("decision", {"status": decision_status})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status=decision_status,
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason=final_decision.get("error_reason"),
        )

    if proposal <= 0:
        complete(budget, seed=seed, purpose="draft", prompt="denied")
        trace.add("decision", {"status": "denied"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="denied",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason=final_decision.get("error_reason"),
        )

    complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")
    try:
        outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise

    if not outcome["ok"]:
        status = "failed" if outcome["conflict"] else "denied"
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status=status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=outcome["reason"],
        )

    return finish(
        conn,
        shape="single",
        claim_id=claim_id,
        seed=seed,
        status="resolved",
        proposal_amount=proposal,
        budget=budget,
        trace=trace,
        error_reason=None,
    )
