"""GraphState → ResponseEnvelope translation (Doc B §5.1.3).

Pure module: no I/O, no HTTP, no globals. Takes the final GraphState
from the LangGraph pipeline and returns a ResponseEnvelope. All the
routing decisions from §5.1.3 are here; server.py just calls this.

Also exports StageTracer, the LangGraph callback that fills
metadata.stages (§5.1.3.4).
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from spire.api.models import (
    ErrorAnswer,
    ErrorDetail,
    Metadata,
    RefusalAnswer,
    RefusalDetail,
    ResponseEnvelope,
    StageTiming,
    TextAnswer,
)


_PIPELINE_NODES = {"parse", "plan", "execute", "synthesize"}


# Response class name → attribute holding the record list. Types not
# listed here render as `text` with records=[] (e.g. CountResponse,
# ComparisonResponse, OpenPOSummaryResponse — scalars only).
# POLifecycleResponse is handled explicitly below.
_RESPONSE_RECORDS_ATTR: dict[str, str] = {
    "SupplierResponse":               "suppliers",
    "InvoiceResponse":                "invoices",
    "PurchaseOrderResponse":          "purchase_orders",
    "AddressResponse":                "addresses",
    "ReceivablesInvoiceResponse":     "receivables_invoices",
    "CustomerAccountResponse":        "customer_accounts",
    "CreditMemoListResponse":         "credit_memos",
    "StandardReceiptResponse":        "standard_receipts",
    "SupplierSpendRankingResponse":   "suppliers",
    "SupplierPOValueRankingResponse": "suppliers",
    "InvoiceAmountRankingResponse":   "invoices",
    "ExposureRankingResponse":        "accounts",
    "ReceiptMethodDistributionResponse": "methods",
    "POStatusBreakdownResponse":      "statuses",
}


# ── Stage timing callback ────────────────────────────────────────────


class StageTracer(BaseCallbackHandler):
    """Fills metadata.stages from LangGraph node callbacks (§5.1.3.4).

    Only the four pipeline nodes are recorded; inner LangChain runs
    (LLM calls, tool invocations) are ignored by the name filter.
    """

    def __init__(self) -> None:
        self._starts: dict[UUID, tuple[str, float]] = {}
        self.stages: list[StageTiming] = []

    def on_chain_start(  # type: ignore[override]
        self,
        serialized: dict | None,
        inputs: dict,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name")
        if name in _PIPELINE_NODES:
            self._starts[run_id] = (name, time.perf_counter())

    def on_chain_end(  # type: ignore[override]
        self,
        outputs: dict,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        entry = self._starts.pop(run_id, None)
        if entry is None:
            return
        name, t0 = entry
        self.stages.append(
            StageTiming(name=name, ms=int((time.perf_counter() - t0) * 1000))
        )


# ── Refusal ──────────────────────────────────────────────────────────


def _attr_or_key(obj: Any, name: str) -> Any:
    """Read obj.name, then obj['name'], then None. Handles both the
    structured Refusal (a Pydantic model) and a plain dict."""
    if obj is None:
        return None
    val = getattr(obj, name, None)
    if val is not None:
        return val
    if isinstance(obj, dict):
        return obj.get(name)
    return None


def _refusal_detail(refusal: Any, fallback_text: str = "") -> RefusalDetail:
    reason = (
        _attr_or_key(refusal, "reason")
        or fallback_text
        or (str(refusal) if refusal is not None else "Refused.")
    )
    return RefusalDetail(
        reason=str(reason),
        solution=_attr_or_key(refusal, "solution"),
        example=_attr_or_key(refusal, "example"),
    )


# ── Error ────────────────────────────────────────────────────────────


def _stage_from_error(msg: str) -> str:
    """The pipeline sets errors as '<node>: <text>' (see graph/pipeline.py)."""
    if ": " in msg:
        head = msg.split(":", 1)[0].strip().lower()
        if head in _PIPELINE_NODES:
            return head
    return "pipeline"


def _retryable(stage: str) -> bool:
    # Pod / network failures are worth retrying; parser and planner
    # failures are not (a re-run of the same prompt will fail the same
    # way). Synthesis failures are internal — leave them non-retryable.
    return stage == "execute"


# ── Response → records ───────────────────────────────────────────────


def _lifecycle_records(response: Any) -> list[dict]:
    """POLifecycleResponse carries .legs + .schedules, not a typed list.
    Both go into records, tagged so the UI can tell them apart."""
    out: list[dict] = []
    for leg in getattr(response, "legs", []) or []:
        out.append({
            "kind": "leg",
            "name": getattr(leg, "name", ""),
            "amount": getattr(leg, "amount", None),
            "remaining": getattr(leg, "remaining", None),
            "complete": getattr(leg, "complete", None),
            "note": getattr(leg, "note", None),
        })
    for row in getattr(response, "schedules", []) or []:
        out.append({
            "kind": "schedule",
            "line_number": getattr(row, "line_number", None),
            "status": getattr(row, "status", None),
            "amount": getattr(row, "amount", None),
            "received_amount": getattr(row, "received_amount", None),
            "outstanding_amount": getattr(row, "outstanding_amount", None),
        })
    return out


def _records_from_response(response: Any) -> list[dict]:
    cls_name = type(response).__name__
    if cls_name == "POLifecycleResponse":
        return _lifecycle_records(response)
    attr = _RESPONSE_RECORDS_ATTR.get(cls_name)
    if attr is None:
        return []
    items = getattr(response, attr, None) or []
    return [r.model_dump() for r in items]


def _truncation_from_response(response: Any) -> tuple[bool, str | None]:
    notes = [str(n) for n in (getattr(response, "truncation_notes", []) or [])]
    return (True, "\n".join(notes)) if notes else (False, None)


# ── Public entry point ───────────────────────────────────────────────


def translate(
    state: dict,
    request_id: str,
    stages: list[StageTiming],
    latency_ms: int,
) -> ResponseEnvelope:
    """Map the pipeline's final GraphState to a ResponseEnvelope.

    Priority order per §5.1.3. Never raises: any unexpected shape falls
    through to an `error` envelope, because the endpoint must always
    return a well-formed response to the UI.
    """
    metadata = Metadata(
        latency_ms=latency_ms,
        llm_calls=0,           # Phase 5 wires real counters via OTel
        tokens_in=0,           # Phase 5
        tokens_out=0,          # Phase 5
        kg_version=None,       # Phase 3g
        stages=stages,
    )

    # 1. Structured refusal (parser, or RefusalError from plan_node).
    refusal = state.get("refusal")
    if refusal is not None:
        return ResponseEnvelope(
            request_id=request_id,
            kind="refusal",
            answer=RefusalAnswer(refusal=_refusal_detail(refusal)),
            metadata=metadata,
        )

    # 2. error + plan_refusal=True → planner declined (Spire answering).
    err = state.get("error")
    if err and state.get("plan_refusal"):
        return ResponseEnvelope(
            request_id=request_id,
            kind="refusal",
            answer=RefusalAnswer(
                refusal=_refusal_detail(None, fallback_text=str(err))
            ),
            metadata=metadata,
        )

    # 3. error alone → genuine failure.
    if err:
        stage = _stage_from_error(str(err))
        return ResponseEnvelope(
            request_id=request_id,
            kind="error",
            answer=ErrorAnswer(
                text=str(err),
                error=ErrorDetail(
                    stage=stage,
                    message=str(err),
                    retryable=_retryable(stage),
                ),
            ),
            metadata=metadata,
        )

    # 4. synth_failed → synthesis overran the cap; records are still valid.
    synth_failed = state.get("synth_failed")
    if synth_failed:
        outputs = state.get("outputs") or {}
        records: list[dict] = []
        for rows in outputs.values():
            if isinstance(rows, list):
                records.extend(r for r in rows if isinstance(r, dict))
        return ResponseEnvelope(
            request_id=request_id,
            kind="table" if records else "text",
            answer=TextAnswer(
                text="",
                records=records,
                truncated=False,
                truncation_note=f"Summary omitted: {synth_failed}",
            ),
            metadata=metadata,
        )

    # 5. Normal response.
    response = state.get("response")
    if response is not None:
        records = _records_from_response(response)
        truncated, note = _truncation_from_response(response)
        text = str(getattr(response, "summary", "") or "")
        return ResponseEnvelope(
            request_id=request_id,
            kind="table" if records else "text",
            answer=TextAnswer(
                text=text,
                records=records,
                truncated=truncated,
                truncation_note=note,
            ),
            metadata=metadata,
        )

    # 6. Defensive — should be unreachable.
    return ResponseEnvelope(
        request_id=request_id,
        kind="error",
        answer=ErrorAnswer(
            text="Pipeline produced no response.",
            error=ErrorDetail(
                stage="pipeline",
                message="GraphState had no refusal, error, or response.",
                retryable=False,
            ),
        ),
        metadata=metadata,
    )