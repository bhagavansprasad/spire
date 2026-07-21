
"""
Pydantic mirror of the planner's ``Intent`` dataclass, for the LLM's
structured output.

WHY A MIRROR (see docs/designs/feature_1_nl_parser_design.md, Q1):
The planner's ``Intent`` is a plain dataclass with a loosely typed
``filters: list[dict]``. ``with_structured_output`` needs a Pydantic schema to
lock the model onto, and the synthesizer already proves this pattern works.
So the parser emits a ``DraftIntent`` (Pydantic), then converts it to the real
``Intent`` dataclass before returning. The planner's input contract is
untouched.

WHY THE FILTER VALUE IS A STRING:
A filter's ``value`` is polymorphic across the planner's filter types — a
string ("US"), a bool (True), or a dict ({"months": 6}). A Pydantic Union of
those types behaves badly with Gemini ``with_structured_output`` (same problem
feature 5 hit with a union ``records`` field — see the 2026-06-01 handoff).
To keep the schema union-free, the LLM emits ``value_json``: a JSON-encoded
string. Conversion to ``Intent`` decodes it. This trades a tiny bit of
prompt instruction for a schema Gemini handles reliably.

DRAFT, NOT VALIDATED:
A ``DraftIntent`` is whatever the LLM produced. It is NOT yet checked against
the KG — that is Q2 direction 2 (checkpoint 3). Conversion here only handles
SHAPE (decode value_json, build the dataclass); it does not judge whether the
entity/filters are KG-valid.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from spire.planner.planner import Intent


class DraftFilter(BaseModel):
    """One filter as the LLM emits it.

    ``type`` is the filter type (e.g. "country", "has_open_PO",
    "has_no_recent_invoices"). ``value_json`` is the filter's value encoded as
    a JSON string, because the value's Python type varies by filter and a
    union schema is unreliable with Gemini. Examples of value_json the LLM
    should produce:
        country               -> "\\"US\\""        (a JSON string)
        has_open_PO           -> "true"            (a JSON bool)
        has_no_recent_invoices-> "{\\"months\\": 6}" (a JSON object)
    """

    type: str = Field(description="The filter type, e.g. 'country'.")
    value_json: str = Field(
        description=(
            "The filter's value, encoded as a JSON string. Use a JSON string "
            'for text (e.g. "\\"US\\""), a JSON bool for presence flags '
            '(e.g. "true"), or a JSON object for parameterized filters '
            '(e.g. "{\\"months\\": 6}").'
        )
    )


class DraftAggregate(BaseModel):
    """The aggregation block, when the question asks for a ranking/total
    rather than a list (feature 7).

    The LLM sets this when it detects aggregation/ranking wording ("top
    N by spend", "total ... by supplier", "which suppliers spent most").
    The user never types these fields — the LLM derives them from the
    natural-language prompt.
    """

    op: str = Field(
        description=(
            "The aggregation shape. Supported: 'by_supplier' (rank "
            "suppliers by total invoice spend over a date range)."
        )
    )
    date_from: str = Field(
        default="",
        description="Inclusive ISO lower bound 'YYYY-MM-DD', or empty.",
    )
    date_to: str = Field(
        default="",
        description="Exclusive ISO upper bound 'YYYY-MM-DD', or empty.",
    )
    top_n: int = Field(
        default=10,
        description="How many groups to return (e.g. 10 for 'top 10').",
    )


class DraftCompare(BaseModel):
    """The comparison block, when the question asks how invoiced compares
    to ordered rather than for a list, ranking, or total.

    A comparison joins two sources (purchase orders and invoices) on
    PurchaseOrderNumber and reports ordered vs invoiced and the
    difference. It is distinct from aggregation (which groups and totals a
    single source) — hence its own block, not an aggregate op.

    The LLM sets this when it detects invoiced-vs-ordered wording ("how
    does invoiced compare to ordered", "was PO X over-invoiced", "are our
    biggest suppliers' orders getting invoiced"). The user never types
    these fields — the LLM derives them from the prompt.

    Three ops, each using only the fields it needs:
      - 'po_invoiced_vs_ordered'          -> po_number
      - 'supplier_invoiced_vs_ordered'    -> supplier_name (+ top_n)
      - 'top_suppliers_invoiced_vs_ordered' -> top_n (+ status)
    """

    op: str = Field(
        description=(
            "The comparison shape. Supported: 'po_invoiced_vs_ordered' "
            "(one PO's ordered vs invoiced — set po_number), "
            "'supplier_invoiced_vs_ordered' (one supplier's — set "
            "supplier_name), 'top_suppliers_invoiced_vs_ordered' (the "
            "top-N suppliers by PO value — set top_n, optional status)."
        )
    )
    po_number: str = Field(
        default="",
        description=(
            "For 'po_invoiced_vs_ordered': the PO's OrderNumber exactly as "
            "written (e.g. '162034'). Empty for the other ops."
        ),
    )
    supplier_name: str = Field(
        default="",
        description=(
            "For 'supplier_invoiced_vs_ordered': a substring of the "
            "supplier's name (e.g. 'Lee Supplies'). Empty for the other ops."
        ),
    )
    top_n: int = Field(
        default=5,
        description=(
            "For the supplier and top-suppliers ops: how many rows to "
            "return (suppliers for the top-N op; PO rows for one supplier)."
        ),
    )
    status: str = Field(
        default="",
        description=(
            "For 'top_suppliers_invoiced_vs_ordered' only: an optional PO "
            "StatusCode (e.g. 'OPEN') to bound which POs count toward "
            "'biggest'. Empty to rank across all POs."
        ),
    )


class DraftIntent(BaseModel):
    """Pydantic mirror of ``Intent`` for structured LLM output.

    Mirrors the dataclass fields (``target_entity``, ``filters``, ``include``),
    plus an explicit refusal slot (``unanswerable`` / ``unanswerable_reason``).

    THE REFUSAL SLOT (the structural half of the silent-rewrite fix):
    Without a way to say "I can't", a model instructed not to salvage an
    out-of-scope prompt has nowhere to put that — and may force a wrong but
    valid-looking Intent (e.g. rewriting "contract renewals" as a bare
    Supplier query). Giving the model an explicit ``unanswerable`` flag lets
    it CHOOSE refusal rather than mangle the request. When set, the parser
    turns it into a Refusal directly, without consulting target_entity/filters.
    """

    unanswerable: bool = Field(
        default=False,
        description=(
            "Set true if the question cannot be expressed using ONLY the "
            "allowed entities and filter types — e.g. it needs an entity or "
            "filter that is not listed, an aggregation, or is too vague to "
            "pin down. When true, do NOT guess a target_entity or map the "
            "request to the closest listed entity; leave the other fields at "
            "their defaults and explain in unanswerable_reason."
        ),
    )
    unanswerable_reason: str = Field(
        default="",
        description=(
            "When unanswerable is true, a brief plain statement of what the "
            "question needs that is not available (e.g. 'needs a Contract "
            "entity, which is not supported' or 'needs spend aggregation')."
        ),
    )
    target_entity: str = Field(
        default="",
        description=(
            "The single entity the query is rooted on, e.g. 'Supplier'. Leave "
            "empty when unanswerable is true."
        ),
    )
    filters: list[DraftFilter] = Field(
        default_factory=list,
        description="Zero or more filters constraining the target entity.",
    )
    include: list[str] = Field(
        default_factory=list,
        description=(
            "Related entities to fetch alongside, e.g. ['Buyer']. Empty if none."
        ),
    )
    fields: list[str] = Field(
        default_factory=list,
        description=(
            "When the question asks for specific columns (e.g. 'get the "
            "supplier name and number', 'with invoice number and amount'), "
            "list the EXACT column names from the target entity's column "
            "list below. Empty if the question does not name specific "
            "columns. Use only names that appear in that list."
        ),
    )
    aggregate: DraftAggregate | None = Field(
        default=None,
        description=(
            "Set this (instead of producing a list) when the question asks "
            "for a ranking or total — e.g. 'top 10 suppliers by spend', "
            "'which suppliers did we spend the most with last quarter'. "
            "Leave it null for ordinary list questions. When set, "
            "target_entity/filters/include are ignored."
        ),
    )
    compare: DraftCompare | None = Field(
        default=None,
        description=(
            "Set this (instead of producing a list) when the question asks "
            "how INVOICED compares to ORDERED — e.g. 'how does invoiced "
            "compare to ordered for PO 162034', 'was PO X over-invoiced', "
            "'are our biggest suppliers' orders getting invoiced'. Leave it "
            "null otherwise. When set, target_entity/filters/include are "
            "ignored. Do NOT set both this and aggregate."
        ),
    )

    count_only: bool = Field(
        default=False,
        description=(
            "Set true when the question asks HOW MANY / the COUNT of a set "
            "rather than for the records themselves — e.g. 'count of "
            "suppliers', 'how many active suppliers', 'how many US "
            "suppliers'. Set target_entity and any filters as normal (the "
            "count is of that filtered set); this flag just says to report "
            "the count instead of listing. Leave false for ordinary list "
            "questions. Do NOT set both this and aggregate."
        ),
    )

    open_only: bool = Field(
        default=False,
        description=(
            "Set true when a customer-invoices question asks for only the "
            "OPEN / OUTSTANDING / UNPAID invoices — e.g. 'open invoices for "
            "[customer]', '[customer]'s outstanding invoices'. Used only "
            "with the customer-invoices shape (target_entity 'CustomerAccount' "
            "with a 'by_customer_name' filter and 'CustomerTransaction' in "
            "include); it restricts the listed transactions to those with a "
            "positive open balance. Leave false when the question asks for a "
            "customer's invoices with no open/outstanding qualifier."
        ),
    )

    def to_intent(self) -> Intent:
        """Convert to the planner's ``Intent`` dataclass.

        Decodes each filter's ``value_json`` into its native Python type and
        assembles the ``{"type": ..., "value": ...}`` dicts the planner
        expects.

        LENIENT DECODING:
        ``value_json`` is meant to be JSON ("\\"US\\"", "true", "{\\"months\\":
        6}"). But models do not reliably JSON-quote bare strings — they often
        emit ``GB`` instead of ``\\"GB\\"``. Rather than refuse such values
        (which made every string-valued filter fragile), we fall back to
        treating an unparseable ``value_json`` as a plain string. So:
            "\\"US\\""        -> "US"   (JSON string)
            "true"            -> True   (JSON bool)
            "{\\"months\\":6}" -> {...}  (JSON object)
            "GB"              -> "GB"   (not JSON -> taken as the string "GB")
        The planner still validates values downstream, so leniency here costs
        nothing and removes a whole class of flaky failures.
        """
        decoded_filters: list[dict[str, Any]] = []
        for f in self.filters:
            try:
                value: Any = json.loads(f.value_json)
            except (json.JSONDecodeError, TypeError):
                # Not valid JSON — treat the raw text as a plain string value.
                value = f.value_json
            decoded_filters.append({"type": f.type, "value": value})

        return Intent(
            target_entity=self.target_entity,
            filters=decoded_filters,
            include=list(self.include),
            fields=list(self.fields),
            aggregate=(
                {
                    "op": self.aggregate.op,
                    "date_from": self.aggregate.date_from or None,
                    "date_to": self.aggregate.date_to or None,
                    "top_n": self.aggregate.top_n,
                }
                if self.aggregate is not None
                else None
            ),
            compare=(
                {
                    "op": self.compare.op,
                    "po_number": self.compare.po_number or None,
                    "supplier_name": self.compare.supplier_name or None,
                    "top_n": self.compare.top_n,
                    "status": self.compare.status or None,
                }
                if self.compare is not None
                else None
            ),
            count_only=self.count_only,
            open_only=self.open_only,
        )




