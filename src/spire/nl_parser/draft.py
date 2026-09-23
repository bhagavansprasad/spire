
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
            "SUPPLIERS by their total invoice spend over a date range), "
            "'top_invoices_by_amount' (rank individual INVOICES by their own "
            "InvoiceAmount, highest first — 'top 10 invoices by amount', "
            "'largest invoices', 'biggest invoices for supplier X'), "
            "'exposure_ranking' (rank customer ACCOUNTS by outstanding "
            "exposure — their open receivables — highest first — 'rank top "
            "accounts by outstanding exposure', 'top accounts by exposure', "
            "'which accounts have the most outstanding receivables'; uses "
            "top_n, no date range), "
            "'receipt_method_distribution' (group a customer's standard "
            "RECEIPTS by ReceiptMethod with a count and total per method — "
            "'receipt method distribution', 'receipts by method', 'receipt "
            "method breakdown for customer X'; the customer scope rides as a "
            "'by_customer_name' filter, NOT in this block)."
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
        description=(
            "How many groups or records to return (e.g. 10 for 'top 10') — "
            "suppliers for 'by_supplier', invoices for 'top_invoices_by_amount', "
            "accounts for 'exposure_ranking'."
        ),
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

    ``unanswerable_kind`` was added in Phase 2 (UX-01). The model was always
    producing an accurate ``unanswerable_reason``; the parser then threw it
    away and re-derived the flavor by scanning that prose for capitalized
    words — which matched "To", "ID", "Filtering" and "Receipt" and so
    returned UNKNOWN_ENTITY for essentially every refusal. Asking the model
    for the kind directly replaces a heuristic that was wrong four times out
    of four with the judgement it had already made.
    """

    unanswerable: bool = Field(
        default=False,
        description=(
            "Set true if the question cannot be expressed using ONLY the "
            "allowed entities and filter types — e.g. it needs an entity or "
            "filter that is not listed, an aggregation, or is too vague to "
            "pin down. When true, do NOT guess a target_entity or map the "
            "request to the closest listed entity; leave the other fields at "
            "their defaults and explain in unanswerable_reason. "
            "IMPORTANT: an unknown COLUMN is NOT a reason to set this true. "
            "If the entity and filters are supported but the question also "
            "asks for a column that is not in the entity's column list, the "
            "question IS answerable: set unanswerable=false, fill "
            "target_entity and filters normally, and put ALL requested "
            "columns in `fields` (see `fields`). The system reports any "
            "unavailable column and returns the rest — do NOT refuse the "
            "whole query because one column is unknown."
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

    unanswerable_kind: str = Field(
        default="",
        description=(
            "When unanswerable is true, WHICH KIND of unanswerable. Exactly "
            "one of these five values. "
            "'missing_identifier': the record type is listed above and the "
            "question is fine, but the prompt never says WHICH record — a "
            "pronoun with nothing to refer back to ('tax lines for that "
            "invoice line'), or no identifier at all ('verify a newly "
            "created AR invoice'). "
            "'unsupported_filter': the entity IS listed above, but the "
            "prompt narrows it by something outside the allowed filter list "
            "('suppliers with more than 50 employees' — headcount is not a "
            "supplier filter). Do NOT map an unsupported value onto a "
            "different filter to make the question answerable. "
            "'unsupported_operation': needs totals, averages, grouping, "
            "ranking or trends ('receipt volume by month', 'cash collection "
            "trends over the period'). "
            "'unknown_entity': the record type itself is absent from the "
            "allowed entity list ('show me our contracts'). "
            "'unparseable': none of the above fit — too vague to pin to any "
            "record type at all ('what is going on with our vendors'). "
            "Choose the most specific kind that fits. If the record type is "
            "listed above, NEVER answer 'unknown_entity'."
        ),
    )

    unanswerable_entity: str = Field(
        default="",
        description=(
            "When unanswerable is true, the record type the question is "
            "ABOUT, when one is clear — 'ReceivablesInvoice' for 'verify a "
            "newly created AR invoice', 'StandardReceipt' for 'the most "
            "recent receipts'. Use a name from the allowed entity list, or "
            "leave empty if no record type is clear. "
            "This is used ONLY to word the reply, so it can name the record "
            "type while explaining what is missing. It does NOT make the "
            "question answerable, and it does NOT change target_entity — "
            "that still stays empty when unanswerable is true."
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
            "list EVERY column the question names, using the entity's column "
            "names below where they match. If the question names a column "
            "that is NOT in the list (e.g. 'credit rating' on a supplier), "
            "still include it here as the user wrote it, and still fill "
            "target_entity and filters normally — do NOT set unanswerable. "
            "The system checks each name against the entity's columns, "
            "returns the ones that exist, and reports the ones that do not; "
            "listing an unknown column here is how it gets reported, so never "
            "drop a requested column. Empty only if the question names no "
            "specific columns."
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

    invoice_limit: int | None = Field(
        default=None,
        description=(
            "Set ONLY on an open-invoices question (the CustomerAccount + "
            "by_customer_name + CustomerTransaction shape with open_only=true) "
            "that also names a row cap — e.g. 'top 5 open invoices for "
            "[customer]', '[customer]'s 10 largest outstanding invoices'. Set "
            "it to that number N (5, 10, ...); the open invoices are returned "
            "highest-balance first, so this keeps the top N. Leave null when "
            "there is no count, or when open_only is not set."
        ),
    )

    balance_only: bool = Field(
        default=False,
        description=(
            "Set true when the question asks for a customer's ACCOUNT "
            "BALANCE or activity summary rather than their invoices — e.g. "
            "'what is the account balance for customer [name]', 'account "
            "activity summary for [name]'. Use target_entity "
            "'CustomerAccount' together with a 'by_customer_name' filter "
            "naming the customer; that filter is REQUIRED and must always "
            "be present. The balance figures ride on the account record "
            "itself. This is NOT an unsupported aggregation — do not set "
            "unanswerable and do not use the aggregate block. Leave false "
            "for a question asking for the customer's invoices, which is "
            "the CustomerTransaction include shape instead."
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

        DOUBLE-ENCODED VALUES (F-044): the model intermittently emits a
        JSON-encoded STRING whose content is the object text — the JSON
        string `"{\\"min\\": 50000}"` rather than `{"min": 50000}`
        itself. One ``json.loads`` yields the string
        ``{"min": 50000}``, which the planner forwards unchanged to a
        tool whose schema rejects it (crash). If the decoded value is
        itself a string whose first character is ``{`` and whose
        content parses as a JSON object, decode a second time. On
        genuine string values the guard is false and nothing changes.
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
            # F-044: the model intermittently double-encodes an OBJECT
            # value — emitting the JSON-string `"{\\"min\\": 50000}"`
            # instead of the object text `{"min": 50000}`. The first
            # json.loads above then yields the STRING `{"min": 50000}`,
            # which the planner forwards unchanged to a tool whose
            # float-typed arg rejects it at Pydantic validation (crash).
            # No filter on this codebase takes a string whose content is
            # a JSON object, so if the decoded string itself parses as
            # one, decode again. On genuine string values ("US", "50000",
            # prose) the first-character test is false and the branch is
            # skipped, and on strings that start with `{` but are not
            # valid JSON the second decode raises and the original string
            # is kept — same leniency as the outer try/except.
            # F-044 / F-011c: loop the decode. The model has been
            # observed to (a) double-encode (F-044), and (b) emit a
            # backslash-escaped object text like `{\"months\":6}`
            # instead of a valid object or a valid JSON string
            # (F-011c, caught on the 15_po_relative_date_filters
            # sweep). The loop peels layers until the value is not a
            # string, or no further progress is made. Each pass
            # tries the string as-is, then with `\"` un-escaped to
            # `"` on the fallback path. Genuine strings ("US",
            # "50000", prose) fail the first-character test and are
            # left alone.
            for _ in range(5):
                if not (isinstance(value, str) and value[:1] == "{"):
                    break
                parsed = None
                try:
                    parsed = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
                if not isinstance(parsed, dict):
                    try:
                        parsed = json.loads(value.replace('\\"', '"'))
                    except (json.JSONDecodeError, TypeError):
                        break
                if not isinstance(parsed, dict):
                    break
                value = parsed
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
            invoice_limit=self.invoice_limit,
            balance_only=self.balance_only,
        )





