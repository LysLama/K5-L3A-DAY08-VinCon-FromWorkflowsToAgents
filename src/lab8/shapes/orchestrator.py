"""Shape C — orchestrator plus read-only investigators.

Signature (do not change):

    run_claim(claim_id, *, seed, store_path, crash_at=None) -> RunResult

The orchestrator plans, hands work to investigators, and is the only writer:

1. Read the claim view. One model call plans the next move from the ticket.
2. Handoff `verify_order_facts` -> an investigator with `lookup_order` only.
3. The orchestrator quotes from that investigator's order view (`compute_compensation`).
4. Only when there is something to pay: handoff `check_prior_refunds` -> an investigator
   with `lookup_refund_history`, carrying the order facts through the allowlist.
5. The orchestrator calls `durability.issue_refund` with the FULL quote. What the second
   investigator reports is for the reply and the trace; the host does the subtraction.

Every handoff is built by `lab8.handoff.make_handoff`: allowlisted fields and fact keys,
read-only tools, and a refusal if a canary survives. Investigators have no write registry.
An LLM summary of the parent context is not a sanitizer, so none is used.

Trace contract v1: every return path goes through `finish`. The trace records the
sanitized handoff and the investigators' allowlisted results, never the parent context
(ticket, principal, secret, headers).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.handoff import make_handoff
from lab8.mock_llm import complete
from lab8.runtime import dispatch, run_readonly_investigators
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import get_claim_view, tool_cost
from lab8.trace import Trace

SHAPE = "orchestrator"


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    budget = Budget()
    trace = Trace(make_run_id(SHAPE, claim_id, seed))
    conn: sqlite3.Connection | None = None
    try:
        conn = connect(store_path)
        return _run(conn, claim_id, seed=seed, crash_at=crash_at, budget=budget, trace=trace)
    except InjectedCrash:
        # Flush what happened so far, then let the crash reach the caller (T12 needs it).
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise
    except Exception as exc:  # noqa: BLE001 — run_claim must not raise (includes HandoffError)
        # Only the exception type is traced: the message could carry row data.
        trace.add("error", {"type": type(exc).__name__})
        return _fail_closed(conn, claim_id, seed, budget, trace, f"internal:{type(exc).__name__}")
    finally:
        if conn is not None:
            conn.close()


def _investigate(
    conn: sqlite3.Connection,
    budget: Budget,
    trace: Trace,
    seed: int,
    claim: dict[str, Any],
    *,
    task: str,
    facts: dict[str, Any],
    tools: list[str],
) -> dict[str, Any]:
    """Send one sanitized handoff to a read-only investigator and return its tool results."""
    handoff = make_handoff(
        request_id=f"REQ-{claim['claim_id']}-{task}",
        claim_id=claim["claim_id"],
        task=task,
        facts=facts,
        allowed_tools=tools,
    )
    trace.add("handoff", safe_dump(handoff))
    # The investigator is a model call whose whole context is the handoff.
    complete(budget, seed=seed, purpose="investigate", prompt=json.dumps(handoff, ensure_ascii=False))
    # principal_id scopes the read tools. It is passed by code and is not part of the handoff.
    report = run_readonly_investigators(conn, budget, handoff, principal_id=claim["principal_id"])
    results = {name: report["tools"].get(name) for name in tools}
    trace.add("investigator", {"task": task, "claim_view": report["claim_view"], "tools": results})
    return results


def _order_facts(order: dict[str, Any]) -> dict[str, Any]:
    """Order facts worth forwarding. `make_handoff` drops any key outside its allowlist."""
    return {
        "delay_days": order["delay_days"],
        "damage_verified": order["damage_verified"],
        "carrier": order["carrier"],
        "order_status": order["status"],
        "shipping_fee_vnd": order["shipping_fee_vnd"],
        "paid_vnd": order["paid_vnd"],
    }


def _run(
    conn: sqlite3.Connection,
    claim_id: str,
    *,
    seed: int,
    crash_at: str | None,
    budget: Budget,
    trace: Trace,
) -> RunResult:
    def done(status: str, proposal: int, reason: str | None = None) -> RunResult:
        if status != "failed":
            # Same draft prompts as workflow, single and swarm, so the draft call costs the same in every shape.
            prompt = status if status in ("needs_info", "escalated") else f"proposal={proposal}"
            complete(budget, seed=seed, purpose="draft", prompt=prompt)
        trace.add("decision", {"status": status, "proposal_vnd": proposal, "reason": reason})
        return finish(
            conn,
            shape=SHAPE,
            claim_id=claim_id,
            seed=seed,
            status=status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=reason,
        )

    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    trace.add("claim", {"found": claim["found"], "has_order_id": bool(claim.get("order_id"))})
    if not claim["found"]:
        return done("failed", 0, "unknown_claim")

    # The orchestrator reads the ticket to plan. The plan picks a task, never an amount.
    complete(budget, seed=seed, purpose="plan", prompt=claim["ticket"])
    if not claim["order_id"]:
        trace.add("plan", {"next": "ask_customer"})
        return done("needs_info", 0, "missing_order_id")
    trace.add("plan", {"next": "verify_order_facts"})

    order_view = _investigate(
        conn, budget, trace, seed, claim, task="verify_order_facts", facts={}, tools=["lookup_order"]
    ).get("lookup_order") or {}
    if not order_view.get("visible"):
        return done("escalated", 0, order_view.get("reason"))
    order = order_view["order"]

    quote = dispatch(conn, budget, "compute_compensation", {"order": order}, worker=False)
    trace.add("quote", quote)
    proposal = int(quote["amount_vnd"])
    if proposal <= 0:
        return done("denied", 0, quote["reason"])

    trace.add("plan", {"next": "check_prior_refunds"})
    _investigate(
        conn,
        budget,
        trace,
        seed,
        claim,
        task="check_prior_refunds",
        facts=_order_facts(order),
        tools=["lookup_refund_history"],
    )

    # Full quote, whatever the history says: the host re-reads the order total in its own transaction.
    outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    trace.add("host", {"ok": outcome["ok"], "reason": outcome["reason"], "conflict": outcome["conflict"]})
    if outcome["ok"]:
        return done("resolved", proposal)
    return done("failed" if outcome["conflict"] else "denied", proposal, outcome["reason"])


def _fail_closed(
    conn: sqlite3.Connection | None,
    claim_id: str,
    seed: int,
    budget: Budget,
    trace: Trace,
    reason: str,
) -> RunResult:
    """Report `failed` without raising. Prefer `finish` so the result still matches the ledger."""
    if conn is not None:
        try:
            conn.rollback()
            return finish(
                conn,
                shape=SHAPE,
                claim_id=claim_id,
                seed=seed,
                status="failed",
                proposal_amount=0,
                budget=budget,
                trace=trace,
                error_reason=reason,
            )
        except Exception:  # noqa: BLE001 — the store itself is unusable
            pass
    return RunResult(
        run_id=trace.run_id,
        claim_id=claim_id,
        shape=SHAPE,
        seed=seed,
        status="failed",
        proposal_amount=0,
        refund_effects=[],
        committed_audit_count=0,
        model_calls=budget.model_calls,
        tool_calls=budget.tool_calls,
        input_tokens=budget.input_tokens,
        output_tokens=budget.output_tokens,
        cost_estimate=round(budget.cost_estimate, 6),
        trace_path=trace.write(),
        error_reason=reason,
    )
