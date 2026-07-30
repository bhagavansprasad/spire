"""Module 5 — PO lifecycle.

Everything about the single-PO lifecycle answer lives here: the four
response models, the deterministic builders, the shape detector that
routes a lifecycle record away from the PO-list schema, the validator,
and the system-prompt block. Moved out of synthesizer.py whole, on
purpose — this is the module the seven-place rule was hardest on, and
splitting only the models while leaving the builder and the prompt
elsewhere would have kept the scatter instead of fixing it.

Adding a sixth catalog prompt to this shape is now: touch this file, add
one entry to the registries in synthesizer.py. Everything that used to
require finding five other places to edit is a single class, a single
function or a single dict key inside this module.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from spire.synthesizer.constants import LIFECYCLE_SHAPE
from spire.synthesizer.errors import HallucinationError
from spire.synthesizer.models_common import _SUMMARY_FIELD, _TRUNCATION_FIELD


# ─────────────────────────────────────────────────────────────────────
# Module 5 — PO lifecycle
#
# ONE response for five catalog prompts (A.2, A.3, A.4, A.7, A.10). They
# ask for the same DATA and differ only in emphasis: is it done, why is
# it stuck, should I care. Choosing emphasis from a question is what a
# language model is for; three schemas would triple the five-place work
# and need a routing signal the parser does not emit.
#
# EVERY NUMBER AND EVERY JUDGEMENT IS COPIED, NEVER DERIVED. risk,
# risk_reasons, recommended_action, lifecycle_stage and responsible_team
# are all computed in the tool precisely so they are reproducible and
# auditable. A model that re-derives them produces a different answer to
# the same question on a different day.
# ─────────────────────────────────────────────────────────────────────


class POLifecycleLeg(BaseModel):
    """One leg of the ordered -> received -> invoiced -> paid chain."""

    name: str = Field(
        description="The leg: 'Ordered', 'Received', 'Invoiced' or 'Paid'."
    )
    amount: float | None = Field(
        default=None,
        description="The amount for this leg, copied exactly. NULL for the "
        "paid leg when paid_state is 'unknown' — do NOT substitute 0.",
    )
    remaining: float | None = Field(
        default=None,
        description="What is still outstanding on this leg, copied exactly. "
        "NULL when unknown — do NOT substitute 0.",
    )
    complete: bool | None = Field(
        default=None,
        description="Whether this leg is finished, copied from "
        "fully_received / fully_invoiced / fully_paid. NULL means UNKNOWN, "
        "not false — only the paid leg can be null.",
    )
    note: str | None = Field(
        default=None,
        description="One short clause if this leg needs qualifying — e.g. "
        "that received is derived from quantities, or that the paid leg "
        "cannot be determined. Otherwise null.",
    )


class POLifecycleScheduleRow(BaseModel):
    """One PO schedule line, copied from the schedules array."""

    line_number: int | None = Field(default=None, description="PO line number.")
    status: str | None = Field(default=None, description="Schedule status.")
    amount: float | None = Field(default=None, description="Ordered amount.")
    received_amount: float | None = Field(
        default=None, description="Received amount (DERIVED from quantity)."
    )
    outstanding_amount: float | None = Field(
        default=None, description="Ordered minus received."
    )


class POLifecycleResponse(BaseModel):
    """The lifecycle answer for ONE purchase order.

    Adapts to the question asked. A 'has it been paid' question leads with
    the legs; a 'why is it stuck' question leads with the blockage and the
    owner; a 'summarise this PO' question leads with value and risk. The
    FIELDS are the same either way — only the summary's emphasis moves.
    """

    summary: str = _SUMMARY_FIELD
    order_number: str = Field(
        description="The PO's OrderNumber, copied exactly from the data."
    )
    supplier: str | None = Field(
        default=None, description="Supplier name, copied from the data."
    )
    currency: str | None = Field(default=None, description="PO currency code.")
    legs: list[POLifecycleLeg] = Field(
        default_factory=list,
        description="The four legs in order: Ordered, Received, Invoiced, "
        "Paid. Always all four, even when a leg is unknown.",
    )
    lifecycle_stage: str = Field(
        description="Copied EXACTLY from lifecycle_stage. Do not reword."
    )
    responsible_team: str = Field(
        description="Copied EXACTLY from responsible_team. Do not reword, "
        "and do not decide the owner yourself."
    )
    risk: str = Field(
        description="Copied EXACTLY from risk — 'Low', 'Medium' or 'High'. "
        "NEVER assess the risk yourself; it is computed."
    )
    risk_reasons: list[str] = Field(
        default_factory=list,
        description="Copied from risk_reasons, in order. Do not add, drop "
        "or reword.",
    )
    recommended_action: str = Field(
        description="Copied EXACTLY from recommended_action. Do not invent "
        "an action, and do not soften or extend the one given."
    )
    setup_notes: list[str] = Field(
        default_factory=list,
        description="Supplier and site setup worth stating: status, spend "
        "authorization, site status, matching level, any hold. Copied from "
        "the setup block. Empty when nothing is notable.",
    )
    exceptions: list[str] = Field(
        default_factory=list,
        description="The unresolved findings, copied from notes. Keep each "
        "one's meaning intact — especially any labelled unconfirmed, which "
        "must stay labelled.",
    )
    schedules: list[POLifecycleScheduleRow] = Field(
        default_factory=list,
        description="Per-line detail, copied from the schedules array. "
        "Include when the question asks why the PO is open or which line "
        "is short; otherwise leave empty.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class POLifecycleSummaryResponse(BaseModel):
    """What the LLM is asked for on the lifecycle path: the summary only.

    Everything else in POLifecycleResponse is built by code from the
    record. A first attempt let the model fill the whole schema and it
    reported the paid leg as `amount=0.0` beside the note "cannot be
    determined" — faithfully copying the tool's `paid: 0.0` while
    destroying its meaning. A reader sees 0.00 and concludes nothing was
    paid, which is the exact assertion the tri-state exists to prevent.

    Same reasoning as build_supplier_records: a value copied by code
    cannot be misreported, so the failure mode is removed rather than
    guarded against. It also stops the model inventing fields the data
    does not have — the first run marked the Ordered leg complete=True,
    which no field says.
    """

    summary: str = _SUMMARY_FIELD
    truncation_notes: list[str] = _TRUNCATION_FIELD


def _build_lifecycle_legs(record: dict) -> list[POLifecycleLeg]:
    """The four legs, built from the record. Never from the model.

    The paid leg is the reason this function exists. When paid_state is
    'unknown' its amount is None — NOT the record's `paid` value, which
    is a legitimate 0.0 meaning "no payment has been observed" and reads
    in a table as "nothing was paid". Those are different statements and
    only one of them is true.
    """
    paid_state = record.get("paid_state")
    paid_unknown = paid_state == "unknown"

    received_note = None
    if record.get("received_is_derived"):
        received_note = "derived from quantity — the pod carries no received amount"

    paid_note = None
    if paid_unknown:
        paid_note = (
            "cannot be determined: the schedules record billing but no AP "
            "invoice carries this PO number"
        )
    elif paid_state == "nothing_due":
        paid_note = "nothing was billed, so nothing is due"

    return [
        POLifecycleLeg(
            name="Ordered",
            amount=record.get("ordered"),
            remaining=None,
            complete=None,
            note=None,
        ),
        POLifecycleLeg(
            name="Received",
            amount=record.get("received"),
            remaining=record.get("remaining_to_receive"),
            complete=record.get("fully_received"),
            note=received_note,
        ),
        POLifecycleLeg(
            name="Invoiced",
            amount=record.get("invoiced"),
            remaining=record.get("remaining_to_invoice"),
            complete=record.get("fully_invoiced"),
            note=None,
        ),
        POLifecycleLeg(
            # amount is None, not record["paid"], when the leg is unknown.
            name="Paid",
            amount=None if paid_unknown else record.get("paid"),
            remaining=record.get("remaining_to_pay"),
            complete=record.get("fully_paid"),
            note=paid_note,
        ),
    ]


def _build_lifecycle_setup_notes(record: dict) -> list[str]:
    """Supplier and site setup, phrased from the record. Deterministic.

    Reports what could not be read as unread, never as clean: an absent
    supplier record is unknown setup, not an active supplier.

    Phase 0 defect 4: the payment-terms note used to sit outside the
    site_read gate, so when the site could not be read it printed
    "differ from the site default (None)" — comparing against a value it
    does not have. Same species as defect 2: a null rendered as a
    statement. The comparison is only meaningful when the site was read.
    """
    setup = record.get("setup") or {}
    notes: list[str] = []

    if not setup.get("supplier_read"):
        notes.append("Supplier master could not be read.")
    else:
        bits = [f"Supplier {record.get('supplier')}"]
        if setup.get("supplier_number"):
            bits.append(f"({setup['supplier_number']})")
        bits.append(f"is {setup.get('supplier_status') or 'of unknown status'}")
        if setup.get("business_relationship"):
            bits.append(f"and {setup['business_relationship']}")
        notes.append(" ".join(bits) + ".")
        if setup.get("on_ofac_list"):
            notes.append("Supplier is flagged on the OFAC sanctions list.")

    if not setup.get("site_read"):
        notes.append("Supplier site could not be read.")
    else:
        notes.append(
            f"Site {record.get('supplier_site')} is "
            f"{setup.get('site_status') or 'of unknown status'}, "
            f"purchasing {'enabled' if setup.get('site_purchasing_enabled') else 'not enabled'}, "
            f"pay {'enabled' if setup.get('site_pay_enabled') else 'not enabled'}."
        )
        if setup.get("match_approval_level"):
            notes.append(
                f"Invoice matching is {setup['match_approval_level']} against "
                f"{setup.get('invoice_match_option') or 'an unspecified basis'}."
            )

    if record.get("payment_terms_overridden"):
        if setup.get("site_read"):
            notes.append(
                f"PO payment terms ({record.get('payment_terms')}) differ from the "
                f"site default ({setup.get('site_payment_terms')})."
            )
        else:
            notes.append(
                f"PO payment terms are {record.get('payment_terms')}; the site "
                f"default could not be read to compare."
            )
    return notes

def build_lifecycle_response(
    record: dict, summary: str, truncation_notes: list[str]
) -> POLifecycleResponse:
    """Assemble the full lifecycle answer. Only `summary` comes from the LLM.

    Phase 0 defect 2: when the PO does not exist there are no legs to
    report. Building them anyway yields four nulls, which render as
    "Received: cannot be determined · Invoiced: cannot be determined" —
    implying the order exists and its state is unknowable. The summary
    says correctly that it was not found and the verdict line then
    contradicts it.

    The setup notes are the same error a second time: on a not-found
    record the setup block is absent, so they read "Supplier master could
    not be read", asserting a failed read when there was no PO to carry a
    supplier.

    Both branches of the tool set `found` explicitly — True on success,
    False on the not-found return — so the flag can be trusted. Branch on
    it, never on the truthiness of a leg.
    """
    if not record.get("found"):
        return POLifecycleResponse(
            summary=summary,
            order_number=str(record.get("order_number") or ""),
            supplier=None,
            currency=None,
            legs=[],
            lifecycle_stage="Not found",
            responsible_team="",
            risk="",
            risk_reasons=[],
            recommended_action="",
            setup_notes=[],
            exceptions=list(record.get("notes") or []),
            schedules=[],
            truncation_notes=truncation_notes,
        )

    schedules = [
        POLifecycleScheduleRow(
            line_number=row.get("line_number"),
            status=row.get("status"),
            amount=row.get("amount"),
            received_amount=row.get("received_amount"),
            outstanding_amount=row.get("outstanding_amount"),
        )
        for row in (record.get("schedules") or [])
    ]
    return POLifecycleResponse(
        summary=summary,
        order_number=str(record.get("order_number") or ""),
        supplier=record.get("supplier"),
        currency=record.get("currency"),
        legs=_build_lifecycle_legs(record),
        lifecycle_stage=record.get("lifecycle_stage") or "",
        responsible_team=record.get("responsible_team") or "",
        risk=record.get("risk") or "",
        risk_reasons=list(record.get("risk_reasons") or []),
        recommended_action=record.get("recommended_action") or "",
        setup_notes=_build_lifecycle_setup_notes(record),
        exceptions=list(record.get("notes") or []),
        schedules=schedules,
        truncation_notes=truncation_notes,
    )


def _lifecycle_shape(outputs: dict[str, list[dict]]) -> dict | None:
    """Return the PO lifecycle record if the outputs carry one, else None.

    Unlike _aggregation_shape and _comparison_shape this scans EVERY
    bucket rather than one named one. The lifecycle step is an ordinary
    entity fetch, so the planner names its bucket after the step — there
    is no fixed "lifecycle" key to look under, and hardcoding a guess
    would break the first time a plan named it differently.
    """
    for bucket in outputs.values():
        if not bucket:
            continue
        first = bucket[0]
        if isinstance(first, dict) and first.get("shape") == LIFECYCLE_SHAPE:
            return first
    return None




def _validate_po_lifecycle(
    response: "POLifecycleResponse", valid: dict[str, set]
) -> None:
    """Check the lifecycle answer against its source record.

    The response carries no numeric ids, so there is little for the
    generic id guard to catch. What CAN go wrong here is different and
    worse: the model reporting a different PO than the one asked about,
    or quietly turning an unknown paid leg into a number. Both would read
    as a confident, correct-looking answer.
    """
    order = (response.order_number or "").strip()
    valid_orders = valid.get("lifecycle_order_numbers") or set()
    if valid_orders and order not in valid_orders:
        raise HallucinationError(
            "Synthesizer answered about a purchase order that is not in the "
            f"executor output: order_number={order!r}, "
            f"available={sorted(valid_orders)}"
        )


# The POLifecycle system-prompt block. Kept as a standalone module-
# level constant rather than inline in a dict literal, so it can be
# imported on its own and slotted into _SYSTEM_PROMPT_BY_ENTITY in
# synthesizer.py without duplicating the text.
LIFECYCLE_SYSTEM_PROMPT = (
        "You are answering a question about ONE purchase order's journey "
        "from order to payment. The data is a single reconciliation record "
        "assembled from six Oracle Fusion resources.\n\n"
        "COPY, DO NOT COMPUTE. Every number, stage, team, risk rating and "
        "recommended action in the data was computed deterministically so "
        "that the same question always gets the same answer. Copy them "
        "exactly. Do NOT add up amounts yourself, do NOT decide who is "
        "responsible, and do NOT form your own view of the risk. If you "
        "disagree with a value, copy it anyway.\n\n"
        "THE PAID LEG CAN BE UNKNOWN. When paid_state is 'unknown', the "
        "schedules record billing but no accounts-payable invoice carries "
        "this PO number. That does NOT mean nothing is owed and it does "
        "NOT mean the supplier was paid. It means the bill cannot be "
        "found. Say so plainly. fully_paid and remaining_to_pay are null "
        "in that case: leave them null, never write 0, and never say the "
        "PO is unpaid or fully paid.\n\n"
        "RECEIVED IS DERIVED. The pod carries no received AMOUNT, only a "
        "received QUANTITY, so the received figure is prorated from it. "
        "When you state the received amount, say it is derived from "
        "quantity. Presenting it as a fetched figure is the exact error "
        "this system exists to avoid.\n\n"
        "YOU WRITE THE SUMMARY ONLY. Every other field is assembled from "
        "the record by code, so you cannot get a number wrong here — but "
        "you can get one wrong in the prose. Quote figures exactly as they "
        "appear.\n\n"
        "NO INTERNAL IDENTIFIERS IN THE SUMMARY. Name the supplier, never "
        "its SupplierId, SupplierSiteId, PersonId or any other numeric "
        "key. Write 'supplier JGA', not 'supplier JGA (ID "
        "300000047414635)'. A finance reader has no use for a primary key "
        "and it makes a correct answer look like a system dump. The PO's "
        "own OrderNumber, invoice numbers and supplier NUMBER are business "
        "identifiers, not internal ones — those are fine.\n\n"
        "ANSWER THE QUESTION ASKED. The data is always the same; the "
        "emphasis is not.\n"
        "- 'has it been received / invoiced / paid', 'is it complete' — "
        "lead with the four legs and a direct yes or no per leg, using "
        "'cannot be determined' where a leg is unknown.\n"
        "- 'why is it still open', 'what is blocking it', 'who owns it' — "
        "lead with the stage, the responsible team and the exceptions, and "
        "include the per-line schedule detail so the short line is named.\n"
        "- 'summarise it', 'executive summary', 'from supplier setup "
        "through payment' — lead with supplier, value and risk, then the "
        "legs, then the recommended action.\n"
        "- 'what is the supplier / approval / matching / payment status' — "
        "walk the stages in order, including the setup notes.\n\n"
        "UNCONFIRMED STAYS UNCONFIRMED. Some notes carry an explicit "
        "hypothesis — for example that a PayOnReceipt flag may explain "
        "unmatched billing. Keep the hedge. Never promote a hypothesis to "
        "a cause, and never supply a cause of your own for a difference "
        "the data does not explain.\n\n"
        "Over-invoicing is not an error. An invoice above the order can be "
        "tax, freight or price variance. Report the difference; do not "
        "call it a problem and do not guess its cause."
)
