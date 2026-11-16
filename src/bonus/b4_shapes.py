"""Fair baselines and component ablations for Bonus B4.

All variants keep the exact `run_claim(claim_id, *, seed, store_path, crash_at=None)`
contract, share the pinned MockLLM, tools, pricing, and host `durability.issue_refund`
gate, and never write secrets or PII into traces.
"""

from __future__ import annotations

import random
import sqlite3
from typing import Any, Callable

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.handoff import make_handoff
from lab8.mock_llm import complete, parse_delay_days
from lab8.runtime import dispatch, run_readonly_investigators
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import compute_compensation, get_claim_view, lookup_order, tool_cost
from lab8.trace import Trace


def _fail_closed(
    conn: sqlite3.Connection | None,
    *,
    shape: str,
    claim_id: str,
    seed: int,
    budget: Budget,
    trace: Trace,
    reason: str,
) -> RunResult:
    if conn is not None:
        try:
            conn.rollback()
            return finish(
                conn,
                shape=shape,
                claim_id=claim_id,
                seed=seed,
                status="failed",
                proposal_amount=0,
                budget=budget,
                trace=trace,
                error_reason=reason,
            )
        except Exception:  # noqa: BLE001 — store itself is unusable
            pass
    return RunResult(
        run_id=trace.run_id,
        claim_id=claim_id,
        shape=shape,
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


def _run_guarded(
    shape: str,
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None,
    fn: Callable[[sqlite3.Connection, Budget, Trace], RunResult],
) -> RunResult:
    budget = Budget()
    trace = Trace(make_run_id(shape, claim_id, seed))
    conn: sqlite3.Connection | None = None
    try:
        conn = connect(store_path)
        return fn(conn, budget, trace)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise
    except Exception as exc:  # noqa: BLE001 — run_claim never raises non-crash errors
        trace.add("error", {"type": type(exc).__name__})
        return _fail_closed(
            conn,
            shape=shape,
            claim_id=claim_id,
            seed=seed,
            budget=budget,
            trace=trace,
            reason=f"internal:{type(exc).__name__}",
        )
    finally:
        if conn is not None:
            conn.close()


def _settle_with_host(
    conn: sqlite3.Connection,
    *,
    shape: str,
    claim_id: str,
    seed: int,
    proposal: int,
    crash_at: str | None,
    budget: Budget,
    trace: Trace,
) -> RunResult:
    outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    trace.add("host", {"ok": outcome["ok"], "reason": outcome["reason"], "conflict": outcome["conflict"]})
    if outcome["ok"]:
        return finish(
            conn,
            shape=shape,
            claim_id=claim_id,
            seed=seed,
            status="resolved",
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=None,
        )
    status = "failed" if outcome["conflict"] else "denied"
    return finish(
        conn,
        shape=shape,
        claim_id=claim_id,
        seed=seed,
        status=status,
        proposal_amount=proposal,
        budget=budget,
        trace=trace,
        error_reason=outcome["reason"],
    )


def _run_workflow_variant(
    conn: sqlite3.Connection,
    *,
    shape: str,
    claim_id: str,
    seed: int,
    crash_at: str | None,
    budget: Budget,
    trace: Trace,
    use_draft_llm: bool,
    trust_ticket_delay: bool,
) -> RunResult:
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    trace.add("claim_view", {"found": claim.get("found"), "has_order_id": bool(claim.get("order_id"))})
    if not claim.get("found"):
        return finish(
            conn, shape=shape, claim_id=claim_id, seed=seed,
            status="failed", proposal_amount=0, budget=budget, trace=trace, error_reason="unknown_claim",
        )
    if not claim.get("order_id"):
        if use_draft_llm:
            complete(budget, seed=seed, purpose="draft", prompt="needs_info")
        trace.add("decision", {"status": "needs_info"})
        return finish(
            conn, shape=shape, claim_id=claim_id, seed=seed,
            status="needs_info", proposal_amount=0, budget=budget, trace=trace, error_reason="missing_order_id",
        )

    budget.add_tool(tool_cost())
    order_view = lookup_order(conn, claim["order_id"], claim["principal_id"])
    trace.add("lookup_order", {"visible": order_view.get("visible"), "reason": order_view.get("reason")})
    if not order_view.get("visible"):
        if use_draft_llm:
            complete(budget, seed=seed, purpose="draft", prompt="escalated")
        return finish(
            conn, shape=shape, claim_id=claim_id, seed=seed,
            status="escalated", proposal_amount=0, budget=budget, trace=trace, error_reason=order_view.get("reason"),
        )

    order = dict(order_view["order"])
    if trust_ticket_delay:
        parsed = parse_delay_days(claim["ticket"])
        if parsed is not None and parsed != int(order["delay_days"]):
            order["delay_days"] = parsed
            trace.add("ticket_override", {"delay_days": parsed})

    budget.add_tool(tool_cost())
    quote_payload = compute_compensation(conn, order)
    proposal = int(quote_payload["amount_vnd"])
    trace.add("quote", quote_payload)
    if use_draft_llm:
        complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")
    if proposal <= 0:
        return finish(
            conn, shape=shape, claim_id=claim_id, seed=seed,
            status="denied", proposal_amount=0, budget=budget, trace=trace, error_reason=quote_payload.get("reason"),
        )
    return _settle_with_host(
        conn, shape=shape, claim_id=claim_id, seed=seed,
        proposal=proposal, crash_at=crash_at, budget=budget, trace=trace,
    )


def rules_only(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    """Deterministic baseline with 0 LLM calls (also serves as workflow without draft LLM)."""
    return _run_guarded(
        "rules_only",
        claim_id,
        seed=seed,
        store_path=store_path,
        crash_at=crash_at,
        fn=lambda conn, budget, trace: _run_workflow_variant(
            conn, shape="rules_only", claim_id=claim_id, seed=seed, crash_at=crash_at,
            budget=budget, trace=trace, use_draft_llm=False, trust_ticket_delay=False,
        ),
    )


def workflow_trust_ticket(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    """Ablation of workflow: removes DB delay grounding in favor of ticket text."""
    return _run_guarded(
        "workflow_trust_ticket",
        claim_id,
        seed=seed,
        store_path=store_path,
        crash_at=crash_at,
        fn=lambda conn, budget, trace: _run_workflow_variant(
            conn, shape="workflow_trust_ticket", claim_id=claim_id, seed=seed, crash_at=crash_at,
            budget=budget, trace=trace, use_draft_llm=True, trust_ticket_delay=True,
        ),
    )


def swarm_pruned(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    """Baseline 2: swarm with seed-controlled random pruning (p=0.5) of peer and parse calls."""
    def _run(conn: sqlite3.Connection, budget: Budget, trace: Trace) -> RunResult:
        rng = random.Random(f"{claim_id}:{seed}")
        prune_peer = rng.random() < 0.5
        prune_parse = rng.random() < 0.5

        budget.add_tool(tool_cost())
        claim = get_claim_view(conn, claim_id)
        if not claim.get("found"):
            trace.add("error", {"reason": "unknown_claim"})
            return finish(
                conn, shape="swarm_pruned", claim_id=claim_id, seed=seed,
                status="failed", proposal_amount=0, budget=budget, trace=trace, error_reason="unknown_claim",
            )

        ticket = claim["ticket"]
        if not prune_peer:
            complete(budget, seed=seed, purpose="peer", prompt=ticket)
        parsed_delay: int | None = None
        if not prune_parse:
            parsed_delay = parse_delay_days(ticket)
            complete(budget, seed=seed, purpose="parse", prompt=ticket)

        if not claim.get("order_id"):
            complete(budget, seed=seed, purpose="draft", prompt="needs_info")
            trace.add("decision", {"status": "needs_info", "pruned_peer": prune_peer, "pruned_parse": prune_parse})
            return finish(
                conn, shape="swarm_pruned", claim_id=claim_id, seed=seed,
                status="needs_info", proposal_amount=0, budget=budget, trace=trace, error_reason="missing_order_id",
            )

        handoff = make_handoff(
            request_id=f"REQ-{claim_id}",
            claim_id=claim_id,
            task="check_applicable_policy",
            facts={},
            allowed_tools=["lookup_order", "lookup_policy", "compute_compensation"],
        )
        trace.add("handoff", safe_dump(handoff))
        investigated = run_readonly_investigators(conn, budget, handoff, principal_id=claim["principal_id"])
        order_view = investigated["tools"].get("lookup_order", {})
        trace.add("investigator", {"lookup_order": order_view, "pruned_peer": prune_peer, "pruned_parse": prune_parse})
        if not order_view.get("visible"):
            complete(budget, seed=seed, purpose="draft", prompt="escalated")
            return finish(
                conn, shape="swarm_pruned", claim_id=claim_id, seed=seed,
                status="escalated", proposal_amount=0, budget=budget, trace=trace, error_reason=order_view.get("reason"),
            )

        order = dict(order_view["order"])
        quote_payload = investigated["tools"]["compute_compensation"]
        if parsed_delay is not None and parsed_delay != int(order["delay_days"]) and seed % 5 == 0:
            order["delay_days"] = parsed_delay
            trace.add("model_override", {"delay_days": parsed_delay})
            budget.add_tool(tool_cost())
            quote_payload = compute_compensation(conn, order)

        proposal = int(quote_payload["amount_vnd"])
        trace.add("quote", quote_payload)
        complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")
        if proposal <= 0:
            return finish(
                conn, shape="swarm_pruned", claim_id=claim_id, seed=seed,
                status="denied", proposal_amount=0, budget=budget, trace=trace, error_reason=quote_payload.get("reason"),
            )
        return _settle_with_host(
            conn, shape="swarm_pruned", claim_id=claim_id, seed=seed,
            proposal=proposal, crash_at=crash_at, budget=budget, trace=trace,
        )

    return _run_guarded("swarm_pruned", claim_id, seed=seed, store_path=store_path, crash_at=crash_at, fn=_run)


def orchestrator_no_history_inv(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    """Ablation of orchestrator: drops the second read-only investigator (check_prior_refunds)."""
    def _run(conn: sqlite3.Connection, budget: Budget, trace: Trace) -> RunResult:
        budget.add_tool(tool_cost())
        claim = get_claim_view(conn, claim_id)
        trace.add("claim", {"found": claim["found"], "has_order_id": bool(claim.get("order_id"))})
        if not claim["found"]:
            return finish(
                conn, shape="orchestrator_no_history_inv", claim_id=claim_id, seed=seed,
                status="failed", proposal_amount=0, budget=budget, trace=trace, error_reason="unknown_claim",
            )

        complete(budget, seed=seed, purpose="plan", prompt=claim["ticket"])
        if not claim.get("order_id"):
            complete(budget, seed=seed, purpose="draft", prompt="needs_info")
            trace.add("plan", {"next": "ask_customer"})
            return finish(
                conn, shape="orchestrator_no_history_inv", claim_id=claim_id, seed=seed,
                status="needs_info", proposal_amount=0, budget=budget, trace=trace, error_reason="missing_order_id",
            )

        handoff = make_handoff(
            request_id=f"REQ-{claim_id}-verify_order_facts",
            claim_id=claim_id,
            task="verify_order_facts",
            facts={},
            allowed_tools=["lookup_order"],
        )
        trace.add("handoff", safe_dump(handoff))
        complete(budget, seed=seed, purpose="investigate", prompt="verify_order_facts")
        report = run_readonly_investigators(conn, budget, handoff, principal_id=claim["principal_id"])
        order_view = report["tools"].get("lookup_order") or {}
        trace.add("investigator", {"task": "verify_order_facts", "claim_view": report["claim_view"], "tools": {"lookup_order": order_view}})
        if not order_view.get("visible"):
            complete(budget, seed=seed, purpose="draft", prompt="escalated")
            return finish(
                conn, shape="orchestrator_no_history_inv", claim_id=claim_id, seed=seed,
                status="escalated", proposal_amount=0, budget=budget, trace=trace, error_reason=order_view.get("reason"),
            )

        quote = dispatch(conn, budget, "compute_compensation", {"order": order_view["order"]}, worker=False)
        trace.add("quote", quote)
        proposal = int(quote["amount_vnd"])
        complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")
        if proposal <= 0:
            return finish(
                conn, shape="orchestrator_no_history_inv", claim_id=claim_id, seed=seed,
                status="denied", proposal_amount=0, budget=budget, trace=trace, error_reason=quote.get("reason"),
            )
        return _settle_with_host(
            conn, shape="orchestrator_no_history_inv", claim_id=claim_id, seed=seed,
            proposal=proposal, crash_at=crash_at, budget=budget, trace=trace,
        )

    return _run_guarded(
        "orchestrator_no_history_inv", claim_id, seed=seed, store_path=store_path, crash_at=crash_at, fn=_run
    )
