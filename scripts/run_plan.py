"""End-to-end driver for the KG-driven path (Architecture Option 3).

Builds a structured Intent, generates a Plan from KG data via the
planner, runs the Plan against the Spire MCP server via the executor,
synthesizes a coherent answer via an LLM with structured output and
hallucination validation, and prints everything along the way.

This is the script that demonstrates the Design 3 architecture end to
end. The planner and executor contain no LLM. The synthesizer is the
ONLY LLM in the pipeline and produces a Pydantic-typed answer that's
cross-validated against the executor's source data to catch invented IDs.

Usage:
    # Terminal 1:
    python -m spire.mcp_server.server

    # Terminal 2 (default: original Track A prompt with negation):
    python scripts/run_plan.py

    # Or explicitly:
    python scripts/run_plan.py --intent original
    python scripts/run_plan.py --intent anchor

    # Phase A gap-analysis prompts (see docs/design3_gap_analysis.md):
    python scripts/run_plan.py --intent prompt-1   # UK suppliers + open POs
    python scripts/run_plan.py --intent prompt-2   # PO-rooted query
    python scripts/run_plan.py --intent prompt-3   # Simplest possible: all India suppliers
    python scripts/run_plan.py --intent prompt-4   # Two negations
    python scripts/run_plan.py --intent prompt-5   # Aggregation by buyer
    python scripts/run_plan.py --intent prompt-6   # Out-of-scope: contracts
    # prompt-7 (ambiguous "best supplier") has no constructible Intent;
    # documented in the gap analysis without a runnable variant.

Intent options:
    original — "Show me suppliers in US with no invoices in 6 months
                but with open purchase orders, including the buyer
                assigned to each." (The original Track A prompt;
                requires F2's no_invoices_in_N_months pattern.)
    anchor   — "Show me suppliers in US with open purchase orders,
                including the buyer assigned to each." (The v1 anchor;
                negation clause dropped.)
    prompt-1 .. prompt-6 — Phase A gap-analysis prompts.

Per-run JSON trace lands in traces/<timestamp>.jsonl alongside the
agent-based runner's traces.

Exit codes:
    0 — success (plan generated, executed, synthesized)
    1 — plan generation failed
    2 — plan execution failed
    3 — synthesis failed (including hallucination)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from fastmcp import Client

from spire.agent.tracing import make_trace_logger
from spire.executor.executor import execute_plan
from spire.planner.planner import Intent, Plan, generate_plan
from spire.synthesizer.synthesizer import (
    CountResponse,
    HallucinationError,
    InvoiceResponse,
    OpenPOSummaryResponse,
    POStatusBreakdownResponse,
    PurchaseOrderResponse,
    SupplierPOValueRankingResponse,
    SupplierResponse,
    SupplierSpendRankingResponse,
    UnsupportedEntityError,
    synthesize_response,
)
    
from spire.nl_parser.parser import parse as parse_prompt
from spire.nl_parser.result import ParseResult
from spire.nl_parser.capability import capability_message
from spire.nl_parser.vocabulary import load_kg_menu

MCP_SERVER_URL = "http://127.0.0.1:3333/mcp/"


# ─────────────────────────────────────────────────────────────────────
# Built-in intents (anchor + original)
#
# CLI arg --intent selects between them. v1 still hardcodes Intent
# construction (no LLM intent parser yet); --intent is a thin convenience
# for testing both shapes without editing the script.
# ─────────────────────────────────────────────────────────────────────


ANCHOR_INTENT = Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "US"},
        {"type": "has_open_PO", "value": True},
    ],
    include=["Buyer"],
)


# Original Track A prompt:
# "Show me suppliers in US with no invoices in 6 months but with open
#  purchase orders, including the buyer assigned to each."
ORIGINAL_INTENT = Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "US"},
        {"type": "has_no_recent_invoices", "value": {"months": 6}},
        {"type": "has_open_PO", "value": True},
    ],
    include=["Buyer"],
)


# ─────────────────────────────────────────────────────────────────────
# Phase A — gap-analysis intents
#
# Each prompt is deliberately chosen to stress a different part of the
# system. Several of these Intents are EXPECTED to fail at one stage or
# another; that failure is itself the measurement we want.
#
# See docs/design3_gap_analysis.md for the per-prompt rationale and
# expected outcomes.
# ─────────────────────────────────────────────────────────────────────


# Prompt 1 — Vocabulary variant of the anchor.
# "Show me suppliers in the United Kingdom with open purchase orders,
#  including the buyer assigned to each."
# Expected: same shape as anchor, country=GB instead of US.
# Should work cleanly IF the demo pod has UK suppliers.
PROMPT_1_INTENT = Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "United Kingdom"},
        {"type": "has_open_PO", "value": True},
    ],
    include=["Buyer"],
)


# Prompt 2 — Different target entity (PurchaseOrder, not Supplier).
# "Show me open purchase orders over $100,000 with their supplier
#  and buyer."
# Expected: planner raises. Today there is no entity-level fetcher
# for PurchaseOrder in the KG (POs are only reachable via the
# HAS_PURCHASE_ORDER edge). Also no amount-based filter type.
# Both gaps will surface — F1 should catch the unknown filter loudly.
PROMPT_2_INTENT = Intent(
    target_entity="PurchaseOrder",
    filters=[
        {"type": "has_open_PO", "value": True},
        # 'amount_over' is intentionally unknown to v1.1; F1 should raise.
        {"type": "amount_over", "value": {"amount": 100000}},
    ],
    include=["Supplier", "Buyer"],
)


# Prompt 3 — Simplest possible intent.
# "List all suppliers in India."
# Expected: 1-step plan (search_suppliers_by_country, country=IN).
# Sanity check that simple queries still work. Also probes whether
# the demo pod even has India suppliers.
PROMPT_3_INTENT = Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "India"},
    ],
    include=[],
)


# Prompt 4 — Two negations composed.
# "Suppliers in US with no invoices in 6 months and no purchase
#  orders in 3 months."
# Expected: planner raises on 'has_no_recent_POs'. F2 added
# has_no_recent_invoices but no equivalent for POs. Tests whether the
# F2 pattern generalized cleanly (it should be a KG row addition, not
# planner code) or whether each child entity needs separate planner
# work.
PROMPT_4_INTENT = Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "US"},
        {"type": "has_no_recent_invoices", "value": {"months": 6}},
        # 'has_no_recent_POs' is intentionally unknown to v1.1.
        {"type": "has_no_recent_POs", "value": {"months": 3}},
    ],
    include=[],
)


# Prompt 5 — Aggregation; different answer shape.
# "What's the total open PO value by buyer? Top 5 buyers by total."
# Expected: the Intent shape doesn't really fit Design 3's three-block
# planner (entity-fetch + edge-filters + includes). target_entity
# 'Buyer' has no entity-level fetcher; the natural query shape is
# 'aggregate POs grouped by buyer'. Planner will probably raise.
# Even if executor produced data, synthesizer's hardcoded
# SynthesizedResponse schema cannot represent rank/aggregate answers.
# This is the explicit reason Phase B (schema generalization) exists.
PROMPT_5_INTENT = Intent(
    target_entity="Buyer",
    filters=[
        # 'po_aggregate_top_n' is intentionally a placeholder for
        # something the system has no concept of today.
        {"type": "po_aggregate_top_n", "value": {"metric": "Ordered", "n": 5}},
    ],
    include=[],
)


# Prompt 6 — Out of scope: contracts.
# "Show me contract renewals due next quarter."
# Expected: the KG has no Contract entity, no contract MCP tool.
# Planner should raise at the find_entity_tool step (unknown entity).
# Tests whether out-of-scope prompts surface a clean honest error
# vs. silent partial answer vs. hallucination.
PROMPT_6_INTENT = Intent(
    target_entity="Contract",
    filters=[
        {"type": "renewal_due_in", "value": {"period": "next_quarter"}},
    ],
    include=[],
)


# Prompt 7 — Ambiguous: not constructible.
# "Who's our best supplier?"
# There is no defensible Intent that captures this. "Best" by what
# metric? Spend? Reliability? PO count? Recency? Without an intent
# parser that can ask clarifying questions, this prompt cannot be
# turned into a structured Intent at all. Documented in the gap
# analysis; no runnable variant in this script.


INTENT_CHOICES: dict[str, Intent] = {
    "anchor": ANCHOR_INTENT,
    "original": ORIGINAL_INTENT,
    "prompt-1": PROMPT_1_INTENT,
    "prompt-2": PROMPT_2_INTENT,
    "prompt-3": PROMPT_3_INTENT,
    "prompt-4": PROMPT_4_INTENT,
    "prompt-5": PROMPT_5_INTENT,
    "prompt-6": PROMPT_6_INTENT,
}


# ─────────────────────────────────────────────────────────────────────
# Pretty-printers
# ─────────────────────────────────────────────────────────────────────


def _format_intent(intent: Intent) -> str:
    """Render an Intent in a single readable block."""
    lines = ["Intent:"]
    lines.append(f"  target_entity: {intent.target_entity}")
    lines.append("  filters:")
    for f in intent.filters:
        lines.append(f"    - {f}")
    lines.append(f"  include: {intent.include}")
    return "\n".join(lines)


def _format_plan(plan: Plan) -> str:
    """Render a Plan as a numbered list of steps with the fields that
    matter at a glance. Full Step dataclass content would be noisy."""
    lines = ["Plan:"]
    for step in plan:
        lines.append(f"  Step {step.step_id}: {step.tool_name}")
        lines.append(f"    tool_args:      {step.tool_args}")
        if step.iterate_over is None:
            lines.append("    iterate_over:   (none — runs once)")
        elif step.iterate_over.get("fields"):
            # Multi-field iteration: several parent fields feed one call
            # (e.g. distributions need POHeaderId + POLineId +
            # LineLocationId). Render arg=field pairs.
            pairs = ", ".join(
                f"{arg}={parent_field}"
                for arg, parent_field in step.iterate_over["fields"].items()
            )
            lines.append(
                f"    iterate_over:   {step.iterate_over['from_step']}"
                f".{{{pairs}}}"
            )
        else:
            lines.append(
                f"    iterate_over:   {step.iterate_over['from_step']}"
                f".{step.iterate_over['field']}"
            )
        if step.client_filters:
            lines.append(f"    client_filters: {step.client_filters}")
        else:
            lines.append("    client_filters: (none)")
        dedupe = step.output_dedupe_by or "(none)"
        lines.append(f"    dedupe_by:      {dedupe}")
        if step.filter_source_when_empty:
            lines.append(
                "    filter_source:  YES (keeps source items whose "
                "iteration returned empty)"
            )
        lines.append(f"    output_name:    {step.output_name}")
    return "\n".join(lines)


def _format_outputs(
    outputs: dict[str, list[dict]], sample_size: int = 3
) -> str:
    """Render outputs as: per-step count + first-N sample records."""
    lines = ["Outputs:"]
    for name, items in outputs.items():
        lines.append(f"  {name}: {len(items)} record(s)")
        sample = items[:sample_size]
        for i, record in enumerate(sample, start=1):
            rendered = json.dumps(record, default=str)
            if len(rendered) > 240:
                rendered = rendered[:237] + "..."
            lines.append(f"    [{i}] {rendered}")
        if len(items) > sample_size:
            lines.append(f"    ... ({len(items) - sample_size} more)")
    return "\n".join(lines)


def _format_synthesized(response) -> str:
    """Render the synthesized response: prose summary + a structured
    record list whose shape depends on the response type."""
    lines = ["Answer:", "", response.summary, ""]
    if response.truncation_notes:
        lines.append("Truncation:")
        for note in response.truncation_notes:
            lines.append(f"  - {note}")
        lines.append("")
 
    if isinstance(response, SupplierResponse):
        if not response.suppliers:
            lines.append("(No suppliers in the structured result.)")
            return "\n".join(lines)
        lines.append("Suppliers:")
        for s in response.suppliers:
            line = (
                f"  - {s.supplier_name} "
                f"(SupplierId={s.supplier_id}, SupplierNumber={s.supplier_number})"
            )
            # open_po_count is None when the query never asked about POs
            # (P5b made it optional). Only render the PO/buyer clause when
            # there was actually an open_pos bucket — otherwise every
            # supplier answer carried "0 open PO(s); buyer(s): (no buyer)"
            # regardless of the question.
            if s.open_po_count is not None:
                buyer_str = ", ".join(
                    f"{b.display_name} (id={b.person_id})" for b in s.buyers
                ) or "(no buyer)"
                line += f" — {s.open_po_count} open PO(s); buyer(s): {buyer_str}"
            if s.contacts:
                admin = next(
                    (c.contact_name for c in s.contacts if c.is_administrative),
                    None,
                )
                line += f" — {len(s.contacts)} contact(s)"
                if admin:
                    line += f"; admin: {admin}"
            lines.append(line)
        return "\n".join(lines)
 
    if isinstance(response, InvoiceResponse):
        if not response.invoices:
            lines.append("(No invoices in the structured result.)")
            return "\n".join(lines)
        lines.append("Invoices:")
        for inv in response.invoices:
            cur = f" {inv.invoice_currency}" if inv.invoice_currency else ""
            lines.append(
                f"  - {inv.invoice_number} "
                f"(InvoiceId={inv.invoice_id}) — {inv.invoice_date}, "
                f"{inv.invoice_amount}{cur}; "
                f"{inv.supplier_name} (SupplierNumber={inv.supplier_number})"
            )
        return "\n".join(lines)
 
    if isinstance(response, PurchaseOrderResponse):
        if not response.purchase_orders:
            lines.append("(No purchase orders in the structured result.)")
            return "\n".join(lines)
        lines.append("Purchase Orders:")
        for po in response.purchase_orders:
            buyer_str = (
                f"{po.buyer.display_name} (id={po.buyer.person_id})"
                if po.buyer is not None
                else "(no buyer)"
            )
            lines.append(
                f"  - {po.order_number} "
                f"(POHeaderId={po.po_header_id}) — {po.status}; "
                f"{po.supplier_name} (SupplierId={po.supplier_id}); "
                f"buyer: {buyer_str}"
            )
        return "\n".join(lines)
 
    if isinstance(response, SupplierSpendRankingResponse):
        if not response.suppliers:
            lines.append("(No suppliers in the ranking.)")
            return "\n".join(lines)
        lines.append("Supplier spend ranking:")
        for i, s in enumerate(response.suppliers, 1):
            lines.append(
                f"  {i}. {s.supplier_name} "
                f"(SupplierNumber={s.supplier_number}) — "
                f"{s.total_spend:,.2f} across {s.invoice_count} invoice(s)"
            )
        return "\n".join(lines)

    if isinstance(response, SupplierPOValueRankingResponse):
        if not response.suppliers:
            lines.append("(No suppliers in the ranking.)")
            return "\n".join(lines)
        lines.append("Supplier PO-value ranking:")
        for i, s in enumerate(response.suppliers, 1):
            # SupplierId, not SupplierNumber — POs carry no supplier number.
            lines.append(
                f"  {i}. {s.supplier_name} "
                f"(SupplierId={s.supplier_id}) — "
                f"{s.total_ordered:,.2f} across {s.po_count} PO(s)"
            )
        return "\n".join(lines)

    if isinstance(response, POStatusBreakdownResponse):
        if not response.statuses:
            lines.append("(No purchase orders in the breakdown.)")
            return "\n".join(lines)
        lines.append(
            f"PO status breakdown — {response.total_pos} PO(s), "
            f"{response.total_ordered:,.2f} total:"
        )
        for row in response.statuses:
            lines.append(
                f"  {row.status:<22} {row.po_count:>5} PO(s)  "
                f"{row.total_ordered:>16,.2f}"
            )
        return "\n".join(lines)

    if isinstance(response, OpenPOSummaryResponse):
        lines.append(
            f"Open POs: {response.po_count} worth "
            f"{response.total_ordered:,.2f} across "
            f"{response.supplier_count} supplier(s)."
        )
        return "\n".join(lines)

    if isinstance(response, CountResponse):
        qualifier = "" if response.count_is_exact else " (at least)"
        lines.append(
            f"Count: {response.count}{qualifier} {response.entity.lower()}(s)."
        )
        return "\n".join(lines)

    # Should be unreachable — every schema in SYNTHESIS_SCHEMAS and
    # AGGREGATION_SCHEMAS is handled above. It fired for all of P6's first
    # run: the schemas existed but this formatter didn't know them, so the
    # prose came through while the block reported "0 record(s)" for a
    # 5-row ranking. Add a schema, add a branch — here AND in the count
    # summary below.
    lines.append("(Unrecognized response shape.)")
    return "\n".join(lines)

def _format_summary(
    plan: Plan,
    outputs: dict[str, list[dict]],
    response,
) -> str:
    """One-screen end-of-run summary."""
    lines = ["Summary:"]
    lines.append(f"  Steps planned:        {len(plan)}")
    total_records = sum(len(v) for v in outputs.values())
    lines.append(f"  Records returned:     {total_records} (across all steps)")
    last_step = plan[-1] if plan else None
    if last_step is not None and last_step.output_name in outputs:
        final_count = len(outputs[last_step.output_name])
        lines.append(
            f"  Final raw output:     {final_count} record(s) under "
            f"'{last_step.output_name}'"
        )
    if isinstance(response, SupplierResponse):
        n, label = len(response.suppliers), "supplier(s)"
    elif isinstance(response, InvoiceResponse):
        n, label = len(response.invoices), "invoice(s)"
    elif isinstance(response, PurchaseOrderResponse):
        n, label = len(response.purchase_orders), "purchase order(s)"
    elif isinstance(response, SupplierSpendRankingResponse):
        n, label = len(response.suppliers), "ranked supplier(s)"
    elif isinstance(response, SupplierPOValueRankingResponse):
        n, label = len(response.suppliers), "ranked supplier(s)"
    elif isinstance(response, POStatusBreakdownResponse):
        n, label = len(response.statuses), "status(es)"
    elif isinstance(response, OpenPOSummaryResponse):
        n, label = response.po_count, "open PO(s)"
    elif isinstance(response, CountResponse):
        n = response.count if response.count is not None else 0
        label = f"{response.entity.lower()}(s) counted"
    else:
        n, label = 0, "record(s)"
    lines.append(f"  Synthesized answer:   {n} {label}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────


async def _run(intent: Intent, intent_name: str) -> int:
    """Build a plan from the intent, execute it, synthesize an answer,
    print everything. Returns a shell-style exit code."""
    logger, trace_path = make_trace_logger()
    logger.info(
        "run_plan_started",
        intent_name=intent_name,
        intent=asdict(intent),
    )

    # ── Step 1: plan (KG only) ────────────────────────────────────
    print(f"Intent ({intent_name}):")
    print(_format_intent(intent))
    print()
    try:
        plan = generate_plan(intent)
    except Exception as exc:
        logger.error("plan_generation_failed", error=str(exc))
        print(f"ERROR generating plan: {exc}", file=sys.stderr)
        return 1
    logger.info(
        "plan_generated",
        step_count=len(plan),
        steps=[
            {
                "step_id": s.step_id,
                "tool_name": s.tool_name,
                "output_name": s.output_name,
                "filter_source_when_empty": s.filter_source_when_empty,
            }
            for s in plan
        ],
    )
    print(_format_plan(plan))
    print()

    # ── Step 2: execute (MCP -> Fusion) ───────────────────────────
    print("Executing plan against MCP server ...")
    print()
    try:
        async with Client(MCP_SERVER_URL) as client:
            logger.info("mcp_session_initialized", url=MCP_SERVER_URL)

            async def _on_progress(progress, total, message=None):
                # Print tool progress to the caller's terminal as it
                # arrives mid-call (e.g. aggregation paginating the pod).
                shown = message or ""
                if total:
                    print(f"  … progress {progress}/{total} {shown}", flush=True)
                else:
                    print(f"  … progress {shown}", flush=True)

            outputs, truncation_by_step = await execute_plan(
                plan, client, progress_handler=_on_progress
            )
    except Exception as exc:
        logger.error("plan_execution_failed", error=str(exc))
        print(f"ERROR executing plan: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2
    logger.info(
        "plan_executed",
        output_record_counts={k: len(v) for k, v in outputs.items()},
    )
    print(_format_outputs(outputs))
    print()

    # ── Step 3: synthesize (LLM with structured output) ───────────
    print("Synthesizing answer via LLM ...")
    print()
    try:
        response = synthesize_response(
            outputs,
            target_entity=intent.target_entity,
            truncation_by_step=truncation_by_step,
        )
    except UnsupportedEntityError as exc:
        logger.error("synthesis_unsupported_entity", error=str(exc))
        print(
            f"ERROR: no synthesizer schema for target_entity="
            f"{intent.target_entity!r}.",
            file=sys.stderr,
        )
        print(f"Details: {exc}", file=sys.stderr)
        return 3
    except HallucinationError as exc:
        logger.error("synthesis_hallucination", error=str(exc))
        print(
            "ERROR: synthesizer produced output that doesn't match the "
            "executor's data.",
            file=sys.stderr,
        )
        print(f"Details: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        logger.error("synthesis_failed", error=str(exc))
        print(f"ERROR during synthesis: {exc}", file=sys.stderr)
        return 3
    logger.info(
        "synthesis_completed",
        supplier_count=len(response.suppliers),
        summary_length=len(response.summary),
        response=response.model_dump(),
    )

    # ── Present ───────────────────────────────────────────────────
    print(_format_synthesized(response))
    print()
    print(_format_summary(plan, outputs, response))
    print()
    print(f"Trace: {trace_path}")
    logger.info("run_plan_finished")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a KG-driven plan end-to-end."
    )
    parser.add_argument(
        "--intent",
        choices=sorted(INTENT_CHOICES.keys()),
        default="original",
        help=(
            "Which hardcoded Intent to run. 'original' (default) is the "
            "original Track A prompt with the negation clause; 'anchor' "
            "is the v1 simplified prompt without negation; 'prompt-1' "
            "through 'prompt-6' are the Phase A gap-analysis prompts "
            "(see docs/design3_gap_analysis.md)."
        ),
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help=(
            "A natural-language prompt to parse into an Intent via the NL "
            "parser (feature 1), instead of selecting a hand-built --intent. "
            "If the prompt is out of scope, prints a capability message and "
            "exits with code 4."
        ),
    )
    
    return parser.parse_args()

def _print_refusal(prompt: str, result: ParseResult, menu) -> None:
    """Print a parser refusal, capability-framed (feature 8).

    Leads with what Spire CAN do (sourced from the KG menu) and why this
    prompt falls outside it. The blunt flavor/detail is kept as a secondary
    line for developers."""
    r = result.refusal
    print(f"Prompt: {prompt}")
    print()
    print(capability_message(r, menu))
    print()
    print(f"  (refusal: {r.flavor.value} — {r.detail})")
    if r.offending_filters:
        print(f"  Unsupported filters: {r.offending_filters}")
        
def main() -> int:
    args = _parse_args()

    if args.prompt is not None:
        # NL path (feature 1). Parsing is synchronous (Q2): load the KG
        # menu and call the parser before entering the async pipeline.
        # Feature 8: the menu is also what the capability message is built
        # from, so load it once and share it with the parser and the printer.
        menu = load_kg_menu()
        result = parse_prompt(args.prompt, menu=menu)
        if result.is_refusal:
            _print_refusal(args.prompt, result, menu)
            return 4
        # Valid Intent -> run the existing pipeline. intent_name is a
        # short label for tracing/printing.
        return asyncio.run(_run(result.intent, "nl_prompt"))

    # Hand-built path (unchanged).
    intent = INTENT_CHOICES[args.intent]
    return asyncio.run(_run(intent, args.intent))


if __name__ == "__main__":
    sys.exit(main())



