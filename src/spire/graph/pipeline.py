"""
Design 3 pipeline expressed as a LangGraph custom graph.

This is the SAME bounded pipeline as scripts/run_plan.py — parse, plan,
execute, synthesize — re-expressed as an explicit LangGraph graph. It is
deliberately NOT an agent: there is no tool-calling loop and no
LLM-driven control flow. The edges are fixed; the LLM is bounded to the
two single-shot roles it already had (parser + synthesizer). The graph
structure exists so the orchestration is explicit and extensible, not to
introduce agent behavior.

Each node wraps the existing function rather than reimplementing it, so
behavior matches Design 3 exactly:

    parse ──(refusal)──────────────► END
      │
      └─(intent)─► plan ─► execute ─► synthesize ─► END

State flows as a typed dict. The MCP client/session needed by the
execute node is passed in at invocation time (config), since LangGraph
nodes are otherwise pure functions of state.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from spire.executor.executor import execute_plan
from spire.nl_parser.parser import parse as parse_prompt
from spire.planner.planner import generate_plan
from spire.nl_parser.result import RefusalError
from spire.synthesizer.synthesizer import DegenerateOutputError, synthesize_response


class GraphState(TypedDict, total=False):
    """State threaded through the graph.

    Inputs:
        prompt: the natural-language question.
        menu: the KG menu (loaded once by the caller).
        session: an open MCP client, used by the execute node.
        progress_handler: optional async (progress, total, message)
            callback; the execute node forwards it to execute_plan so a
            long tool call reports progress back to the caller.
    Produced along the way:
        intent, refusal, plan, outputs, truncation_by_step, metadata_by_step, response.
        error: set if a node failed; downstream nodes short-circuit.
        plan_refusal: True when `error` is a planner REFUSAL (Spire
            declining an under-specified or unsupported query) rather
            than a failure. Read this instead of matching on the
            message text.
    """

    prompt: str
    menu: Any
    session: Any
    progress_handler: Optional[Any]

    # Execution cache (2026-08-04). Set by the caller; read only by
    # execute_node. See _cache_path for what is stored and why it is
    # only the executor's output.
    #   cache_mode: "save" | "use" | None
    #   cache_slot: a name the caller chooses, e.g. "po_status"
    cache_mode: Optional[str]
    cache_slot: Optional[str]

    intent: Optional[Any]
    refusal: Optional[Any]
    plan: Optional[Any]
    outputs: Optional[dict]
    projected_outputs: Optional[dict]
    truncation_by_step: Optional[dict]
    metadata_by_step: Optional[dict]   # added
    response: Optional[Any]
    synth_failed: Optional[str]        # set when synthesis overran the cap
    error: Optional[str]
    # True when `error` is Spire DECLINING rather than Spire BREAKING.
    # Callers render a refusal differently from a failure, and used to
    # tell them apart by grepping the message ("require" in err) — so
    # rewording a guard silently reclassified it. It did: a planner
    # message reworded to name the supported filters stopped matching,
    # and a perfectly good refusal started being counted as a crash.
    plan_refusal: Optional[bool]


# ── Nodes ─────────────────────────────────────────────────────────────


def parse_node(state: GraphState) -> dict:
    result = parse_prompt(state["prompt"], menu=state["menu"])
    if result.is_refusal:
        return {"refusal": result.refusal}
    return {"intent": result.intent}


def plan_node(state: GraphState) -> dict:
    try:
        plan = generate_plan(state["intent"])
        return {"plan": plan}
    except RefusalError as exc:
        # A guard that has been converted to the structured path. Route the
        # wrapped Refusal into the SAME channel parse_node uses for a parser
        # decline, so run_graph renders it through capability_message — the
        # readable Reason/Solution/Example shape — instead of printing a raw
        # guard string. No plan_refusal flag: that flag drives the legacy
        # "REFUSED (planner guard): ..." render, which this path replaces.
        return {"refusal": exc.refusal}
    except (ValueError, NotImplementedError) as exc:
        # Spire DECLINING, not Spire breaking — both carry a message
        # written for the user, naming what is missing and giving an
        # example to type:
        #   ValueError          an entity guard: the query has no root
        #                       reference ("Invoice queries require a
        #                       supplier ...")
        #   NotImplementedError an unsupported filter for this entity
        #                       ("Spire can't filter CustomerAccount
        #                       by 'account_number' ...")
        # The distinction between the two matters inside the planner
        # (and its tests) but not to a caller: both are answers.
        return {"error": f"plan: {exc}", "plan_refusal": True}
    except Exception as exc:  # a genuine planner failure
        return {"error": f"plan: {exc}"}


def _project_outputs(outputs: dict, fields: list) -> dict:
    """Trim each record in each output bucket to the requested fields.

    Phase 7 projection. Only columns named in `fields` are kept; a record
    missing all of them is left untouched (better to show something than
    an empty row). Returns a new dict; the original outputs are unchanged,
    so the synthesizer still sees full records.
    """
    if not fields:
        return outputs
    wanted = list(fields)
    projected: dict = {}
    for name, records in outputs.items():
        new_records = []
        for rec in records:
            if not isinstance(rec, dict):
                new_records.append(rec)
                continue
            trimmed = {k: rec[k] for k in wanted if k in rec}
            new_records.append(trimmed if trimmed else rec)
        projected[name] = new_records
    return projected


# ── Execution cache ───────────────────────────────────────────────────
#
# A page-capped aggregation takes minutes: "top 5 suppliers by spend"
# walks 50 pages of 500 invoices, and timed out mid-fetch once on
# 2026-08-04. Iterating on the SYNTHESIZER against that is a poor trade —
# the layer being changed runs in milliseconds and the fetch in front of
# it runs for minutes.
#
# WHAT IS CACHED, AND WHY ONLY THIS
# The executor's three outputs and nothing else. Parse and plan still run
# live on every replay, so:
#
#   - intent and plan never need serialising. They are Pydantic objects
#     and rebuilding them from JSON would be a second, drifting
#     definition of what the graph already produces.
#   - a parser or planner change is still exercised. Only the POD is
#     removed, which is the slow part and the only part.
#   - projected_outputs is DERIVED (outputs + intent.fields), so it is
#     recomputed rather than stored. Storing it would let it disagree
#     with outputs after a projection change.
#
# The cost of a live parse is one cheap LLM call, ~9k tokens. Worth it to
# avoid a serialised copy of two Pydantic models.
#
# WHAT THIS CANNOT CATCH
# A tool whose return shape changed. The cache keeps answering with the
# old shape and everything looks fine — the same drift that makes stale
# context bundles dangerous. Hence the header: every replay prints the
# prompt and the age of the file it is reading, to stderr, before the
# answer. A view that does not announce its own limits produces confident
# wrong answers indefinitely.

_CACHE_DIR = Path(".spire_cache")


def _cache_path(slot: str) -> Path:
    """File for a named slot. Named, not hashed, deliberately.

    A hash of the prompt is automatic and unreadable: `ls .spire_cache`
    shows nothing about what is in there, and two variants of the same
    question cannot both be kept. A slot the caller names survives
    rephrasing and is greppable.
    """
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in slot)
    return _CACHE_DIR / f"{safe}.json"


def _save_execution(slot: str, prompt: str, payload: dict) -> None:
    """Write the executor's output for a slot, overwriting any previous.

    Overwrite IS the refresh mechanism — re-running with --save-cache
    replaces the file. A confirm-before-clobber step was considered and
    rejected: friction there means stale caches survive longer, which is
    the failure this whole thing is meant to avoid.
    """
    _CACHE_DIR.mkdir(exist_ok=True)
    record = {
        "prompt": prompt,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "outputs": payload["outputs"],
        "truncation_by_step": payload["truncation_by_step"],
        "metadata_by_step": payload["metadata_by_step"],
    }
    _cache_path(slot).write_text(json.dumps(record, indent=2, default=str))


def _load_execution(slot: str) -> dict:
    """Read a slot, or raise.

    Raises rather than falling back to a live fetch. A --use-cache run
    that silently went to the pod would be indistinguishable from a
    cached one except by how long it took, and the whole point is to know
    which you are looking at.
    """
    path = _cache_path(slot)
    if not path.exists():
        raise FileNotFoundError(
            f"No cached execution in slot {slot!r} ({path}). "
            f"Run once with --save-cache {slot} first."
        )
    return json.loads(path.read_text())


async def execute_node(state: GraphState) -> dict:
    mode = state.get("cache_mode")
    slot = state.get("cache_slot")

    try:
        if mode == "use":
            record = _load_execution(slot)
            # To stderr, always, ungated — same reasoning as the progress
            # lines and the counts footer. A replay that does not announce
            # itself is a trap.
            print(
                f"[cache] replaying slot {slot!r} saved "
                f"{record.get('saved_at')} for prompt "
                f"{record.get('prompt')!r} — no pod call",
                file=sys.stderr,
                flush=True,
            )
            outputs = record["outputs"]
            truncation = record["truncation_by_step"]
            metadata = record["metadata_by_step"]
        else:
            outputs, truncation, metadata = await execute_plan(
                state["plan"],
                state["session"],
                progress_handler=state.get("progress_handler"),
            )
            if mode == "save":
                _save_execution(
                    slot,
                    state["prompt"],
                    {
                        "outputs": outputs,
                        "truncation_by_step": truncation,
                        "metadata_by_step": metadata,
                    },
                )
                print(
                    f"[cache] saved slot {slot!r} -> {_cache_path(slot)}",
                    file=sys.stderr,
                    flush=True,
                )

        fields = getattr(state.get("intent"), "fields", []) or []
        projected = _project_outputs(outputs, fields)
        return {
            "outputs": outputs,
            "projected_outputs": projected,
            "truncation_by_step": truncation,
            "metadata_by_step": metadata,   # added
        }
    except Exception as exc:
        return {"error": f"execute: {exc}"}


def _filtered_fields(intent) -> list[str]:
    """Field names the user filtered on, for the local summary.

    A locally-built summary may describe a field the reader can SEE or a
    field the reader ASKED for. This supplies the second half.

    Without it the rule collapses to displayed-fields-only, and on the
    commonest query in the system — "list active suppliers" — the whole
    summary becomes the count line: build_supplier_records renders name,
    number and addresses, so Status is not on screen and could not be
    mentioned. "All 25 are ACTIVE" is worth saying, and the reader can
    check it, because they are the one who said "active".

    Filters carry a `type` (status, country, name), which is the field
    in the user's vocabulary rather than the pod's. That is the right
    end to take it from: the reader recognises what they asked for, not
    what Oracle calls it.
    """
    out: list[str] = []
    for f in getattr(intent, "filters", None) or []:
        ftype = f.get("type") if isinstance(f, dict) else getattr(f, "type", None)
        if ftype and ftype not in out:
            out.append(str(ftype))
    return out


def synthesize_node(state: GraphState) -> dict:
    try:
        intent = state["intent"]
        target_entity = intent.target_entity
        response = synthesize_response(
            state["outputs"],
            target_entity=target_entity,
            truncation_by_step=state.get("truncation_by_step"),
            count_only=getattr(intent, "count_only", False),
            metadata_by_step=state.get("metadata_by_step"),   # added
            filtered_fields=_filtered_fields(intent),
        )
        return {"response": response}
    except DegenerateOutputError as exc:
        # The summary overran the token cap. Do NOT abort the run: fall
        # through with a flag so the print step can show the table alone
        # (the table is always available from `outputs`). Only applies when
        # the intent carries `fields`; a degenerate synthesis on a normal
        # query still leaves response=None and prints no summary.
        return {"synth_failed": str(exc)}
    except Exception as exc:
        return {"error": f"synthesize: {exc}"}


# ── Edges ─────────────────────────────────────────────────────────────


def _after_parse(state: GraphState) -> str:
    # Refusal short-circuits straight to END (mirrors run_plan exit 4).
    return "refusal" if state.get("refusal") else "plan"


def _continue_or_end(state: GraphState) -> str:
    # Any node that set `error` ends the run early.
    return "end" if state.get("error") else "continue"


def build_graph():
    """Compile and return the Design 3 pipeline graph.

    If SPIRE_GRAPH_PNG is set (to a path, or "1" for a default path), the
    compiled graph is also rendered to PNG. Rendering is opt-in because it
    needs pyppeteer and is slow; normal runs/imports skip it.
    """
    g = StateGraph(GraphState)

    g.add_node("parse", parse_node)
    g.add_node("plan", plan_node)
    g.add_node("execute", execute_node)
    g.add_node("synthesize", synthesize_node)

    g.set_entry_point("parse")

    g.add_conditional_edges(
        "parse", _after_parse, {"refusal": END, "plan": "plan"}
    )
    g.add_conditional_edges(
        "plan", _continue_or_end, {"continue": "execute", "end": END}
    )
    g.add_conditional_edges(
        "execute", _continue_or_end, {"continue": "synthesize", "end": END}
    )
    g.add_edge("synthesize", END)

    compiled = g.compile()
    _maybe_save_png(compiled)
    return compiled


def _maybe_save_png(compiled) -> None:
    """Render the compiled graph to PNG if SPIRE_GRAPH_PNG is set.

    SPIRE_GRAPH_PNG="1" -> default path docs/pipeline_graph.png
    SPIRE_GRAPH_PNG="<path>" -> that path
    Failures (no pyppeteer, etc.) are logged to stderr, never fatal."""
    import os

    val = os.environ.get("SPIRE_GRAPH_PNG")
    if not val:
        return
    path = "docs/pipeline_graph.png" if val == "1" else val
    try:
        png = compiled.get_graph().draw_mermaid_png()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(png)
        print(f"[graph] wrote {path}", flush=True)
    except Exception as exc:  # rendering is best-effort (needs network)
        import sys

        print(f"[graph] PNG render skipped: {exc}", file=sys.stderr)


# Module-level compiled graph (compilation is cheap and reusable).
GRAPH = build_graph()


