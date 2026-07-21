"""
The NL parser — natural-language prompt to ``Intent`` (feature 1).

This is the interpreter stage of the Design 3 pipeline:

    Prompt -> [parser: LLM] -> Intent -> planner -> executor -> synthesizer

See docs/designs/feature_1_nl_parser_design.md. The parser is modeled on the
synthesizer: a single bounded LLM call with structured output, plus
validation. It owns its KG access via the planner's synchronous path.

CHECKPOINT SCOPE:
This module covers prompt-building, the LLM call, draft production, and the
two-way KG validation of the draft (Q2 direction 2). The LLM emits a
``DraftIntent`` (Pydantic), which is converted to the planner's ``Intent`` and
then validated against the KG menu: out-of-scope entities/filters become typed
refusals (UNKNOWN_ENTITY / UNSUPPORTED_OPERATION / UNSUPPORTED_FILTER); wholly
unparseable output becomes UNPARSEABLE. The pipeline gate (Q5: stop before
planning on a refusal) is the remaining integration step.

LLM INJECTION (Q4):
``parse`` takes an optional ``llm``. Tests inject a mock that returns a canned
``DraftIntent``; production passes None and a real Gemini client is built —
same convention as the synthesizer.
"""

from __future__ import annotations

from typing import Any

from spire.config import GEMINI_MODEL, GEMINI_TEMPERATURE
from spire.nl_parser.capability import derive_flavor
from spire.nl_parser.draft import DraftIntent
from spire.nl_parser.result import ParseResult, RefusalFlavor
from spire.nl_parser.validation import validate_intent
from spire.nl_parser.vocabulary import KGMenu, load_kg_menu


# Model and determinism come from spire.config (single source of truth).
_MODEL_NAME = GEMINI_MODEL
_TEMPERATURE = GEMINI_TEMPERATURE


_SYSTEM_PROMPT_PREAMBLE = (
    "You convert a natural-language question about Oracle Fusion procurement "
    "data into a single structured Intent. You do NOT answer the question, "
    "fetch data, or call tools. You only produce the Intent.\n\n"
    "An Intent has:\n"
    "- target_entity: the ONE entity the question is rooted on.\n"
    "- filters: zero or more constraints, each a type plus a JSON-encoded "
    "value.\n"
    "- include: related entities to fetch alongside (e.g. the buyer on a PO).\n\n"
    "You may ONLY use the entities and filter types listed below.\n\n"
    "COMPLETENESS — extract EVERY in-scope detail:\n"
    "When the question maps onto the allowed vocabulary, you MUST capture "
    "ALL of its constraints and relationships — do not omit any. Map natural "
    "language to the allowed filters/includes, for example:\n"
    "- a country ('US', 'in the United Kingdom') -> a 'country' filter, with "
    "the value normalized to the canonical code from the COUNTRY list below.\n"
    "- 'with open POs' / 'has open purchase orders' -> a 'has_open_PO' "
    "filter with value true.\n"
    "- 'no invoices in the last N months' / 'without recent invoices' / "
    "'no recent invoices' / 'haven't invoiced in N months' -> a "
    "'has_no_recent_invoices' filter with value {\"months\": N}. This clause "
    "is easy to miss — whenever the prompt mentions an absence of invoices "
    "over a time window, you MUST emit this filter.\n"
    "- 'suppliers with an invoice over N' / 'suppliers with invoice amount "
    "greater than N' / 'suppliers who invoiced more than N' -> a "
    "'has_invoice_over_amount' filter with value N (the numeric threshold, "
    "e.g. 10000). This roots on Supplier and keeps suppliers that have at "
    "least one invoice at/over that amount. Distinct from an Invoice-target "
    "query: here the answer is SUPPLIERS, not invoices.\n"
    "- 'suppliers with a site in business unit X' / 'suppliers with a "
    "supplier site based on business unit X' / 'suppliers with a site in "
    "the X business unit' / 'suppliers that operate in the X business "
    "unit' -> a 'has_site_in_bu' filter whose value is the canonical "
    "display string for that business unit. Known business units and "
    "their canonical forms: 'us1' -> 'US1 Business Unit'; 'uk' -> 'UK "
    "Business Unit'; 'france' -> 'France Business Unit'; 'germany' -> "
    "'Germany Business Unit'; 'italy' -> 'Italy Business Unit'; 'china' -> "
    "'China Business Unit'; 'japan' -> 'Japan Business Unit'; 'india' -> "
    "'India Business Unit'; 'sweden' -> 'Sweden Business Unit'; "
    "'healthcare us' -> 'Healthcare US Business Unit'. Use this filter "
    "whenever the phrase names a business unit together with the words "
    "'site' or 'business unit' — this includes country-named business "
    "units like 'UK business unit' or 'France business unit'. A bare "
    "country with NO 'site'/'business unit' wording — e.g. 'US "
    "suppliers', 'suppliers in the UK' — is a 'country' filter instead. "
    "Roots on Supplier and keeps suppliers that have at least one site in "
    "that BU. The answer is SUPPLIERS.\n"
    "- 'suppliers that are X' / 'suppliers with the X classification' / "
    "'X-certified suppliers' where X is a business classification -> a "
    "'has_classification' filter whose value is the canonical display "
    "string for that classification. Known classifications and their "
    "canonical forms: 'small business' -> 'Small Business'; 'woman owned' "
    "-> 'Woman Owned'; 'minority owned' -> 'Minority Owned'; 'veteran "
    "owned' -> 'Veteran Owned'; 'hub zone' -> 'Hub Zone'; 'iso 14001' -> "
    "'ISO 14001'; 'general liability insurance' -> 'General Liability "
    "Insurance'; 'workers compensation insurance' -> \"Workers' "
    "Compensation Insurance\"; 'kbis' -> 'Kbis'. Only use this filter when "
    "the phrase clearly names one of these classifications. Roots on "
    "Supplier and keeps suppliers holding that classification. The answer "
    "is SUPPLIERS.\n"
    "- 'active suppliers' / 'inactive suppliers' -> a 'status' filter with "
    "value 'active' or 'inactive'.\n"
    "- 'spend authorized suppliers' / 'prospective suppliers' / 'suppliers "
    "with business relationship X' -> a 'business_relationship' filter with "
    "value 'spend authorized' or 'prospective'.\n"
    "- 'suppliers named X' / 'called X' / 'with X in the name' -> a "
    "'name_fragment' filter with value the substring X.\n"
    "- 'created after X' / 'created between X and Y' / 'created in <period>' "
    "-> a 'created_date' filter with value {\"from\": \"YYYY-MM-DD\", "
    "\"to\": \"YYYY-MM-DD\"}. Include only the bounds the prompt gives; omit "
    "the other key. Convert every date to YYYY-MM-DD (e.g. 'Jan 2025' -> "
    "from '2025-01-01'; 'March 2025' as an end -> to '2025-04-01').\n"
    "- 'invoices for supplier X' / 'invoices for supplier 1252' / 'invoices "
    "for Lee Supplies' -> target_entity 'Invoice' with a 'supplier' filter "
    "whose value is the supplier reference as written (a number like '1252' "
    "or a name like 'Lee Supplies'). Invoice queries MUST include this "
    "supplier filter.\n"
    "- 'invoices in 2023' / 'invoices after 2023-01-01' / 'invoices "
    "between Jan and Mar 2023' -> an 'invoice_date' filter with value "
    "{\"from\": \"YYYY-MM-DD\", \"to\": \"YYYY-MM-DD\"}. Include only the "
    "bounds given; omit the other key. Convert dates to YYYY-MM-DD.\n"
    "- 'invoices over 10000' / 'invoices above 10000' / 'invoices between "
    "1000 and 5000' -> an 'invoice_amount' filter with value "
    "{\"min\": N, \"max\": N} (numbers, not strings). Include only the "
    "bounds given; omit the other key.\n"
    "- 'addresses for supplier X' / 'supplier 1252 addresses' / 'US "
    "supplier addresses' / 'addresses in the UK' -> target_entity "
    "'Address' with a 'supplier' filter (the supplier reference as "
    "written) and/or a 'country' filter (canonical code). Address queries "
    "MUST include a supplier or a country.\n"
    "- 'include the buyer' / 'with the buyer' / 'show the buyer assigned' -> "
    "add 'Buyer' to include.\n"
    "- 'PO 2144' / 'purchase order 2144' / 'what is PO US164932 about' / "
    "'show PO 162352' -> target_entity 'PurchaseOrder' with a 'by_id' "
    "filter whose value is the purchase-order id or number exactly as "
    "written (e.g. '2144' or '162034'). A single purchase order named by "
    "its id or order number is ALWAYS a 'by_id' filter — never invent an "
    "'OrderNumber' or other filter. Pass the number through EXACTLY as "
    "given and do not try to work out which kind it is: an order number "
    "and a header id look identical in a question, and the tool resolves "
    "either. This 'by_id' rule applies to purchase orders and AR invoices "
    "only. A bare "
    "number attached to another entity is NOT a by_id filter: e.g. "
    "'supplier 1262' is a SUPPLIER reference, not a purchase order, and "
    "must never produce a 'by_id' filter.\n"
    "- 'and its lines' / 'show its lines' / 'with the line items' / 'show "
    "the PO lines' on a purchase-order question -> add 'PurchaseOrderLine' "
    "to include (alongside the 'by_id' filter).\n"
    "- 'the AR invoice with CustomerTransactionId 300000248096352' / 'AR "
    "invoice 300000248096352' / 'the AR invoice with CustomerTransactionId "
    "1002' / 'receivables invoice X' / 'invoice details "
    "for CustomerTransactionId X' -> target_entity 'ReceivablesInvoice' "
    "with a 'by_id' filter whose value is the CustomerTransactionId exactly "
    "as written. Like the purchase-order by_id rule, a single AR invoice "
    "named by its CustomerTransactionId is ALWAYS a 'by_id' filter — "
    "REGARDLESS of the id's length. Short numeric ids (e.g. 1002) are valid "
    "CustomerTransactionIds and MUST get a 'by_id' filter just like the long "
    "18-digit form; never drop the filter because the id looks short. This "
    "is the accounts-receivable invoice, distinct from the AP 'invoice'/"
    "'bill' which maps to Invoice.\n"
    "- 'and its lines' / 'show its lines' / 'with the line items' on an "
    "AR-invoice question -> add 'ReceivablesInvoiceLine' to include "
    "(alongside the 'by_id' filter).\n"
    "- 'and its tax lines' / 'show the tax lines' / 'what tax was charged' / "
    "'the tax breakdown' on an AR-invoice question -> add BOTH "
    "'ReceivablesInvoiceLine' AND 'ReceivablesTaxLine' to include, in that "
    "order (alongside the 'by_id' filter). Tax lines hang off invoice lines, "
    "so the line hop is always needed to reach them.\n"
    "- 'fetch DFF values for this invoice' / 'and its DFF values' / 'its "
    "DFF' / 'show the DFF' / 'the descriptive flexfield' / 'its flexfield "
    "values' on an AR-invoice question -> add "
    "'ReceivablesInvoiceTransactionDFF' to include (alongside the 'by_id' "
    "filter). The DFF hangs directly off the invoice (a single hop, no line "
    "needed), unlike tax lines. Of the two DFF children this is the "
    "transaction DFF, the populated one.\n"
    "- 'AR invoices for ABC Corporation Americas' / 'receivables invoices "
    "for [name]' / 'invoices for customer [name]' / 'show me customer "
    "[name]'s invoices' -> target_entity 'CustomerAccount' with a "
    "'by_customer_name' filter whose value is the customer name exactly as "
    "written, AND add 'CustomerTransaction' to include. This is a "
    "customer-scoped AR query: it resolves the customer to their account, "
    "then lists that account's transactions. IMPORTANT: route here ONLY "
    "when the request carries an explicit AR/customer signal ('AR', "
    "'receivables', or 'customer'). A bare 'invoices for [name]' with NO "
    "such signal is the AP supplier-invoice case -> 'Invoice' with a "
    "'supplier' filter (above), NOT this. And a single AR invoice named by "
    "its CustomerTransactionId is 'ReceivablesInvoice' with 'by_id' "
    "(above), NOT this.\n"
    "- 'and its schedules' / 'show its schedules' / 'with the shipment "
    "schedules' on a purchase-order question -> add 'POSchedule' to include "
    "(alongside the 'by_id' filter).\n"
    "- 'and its distributions' / 'show the distribution accounts' / 'what "
    "accounts is it booked to' on a purchase-order question -> add BOTH "
    "'POSchedule' AND 'PODistribution' to include, in that order "
    "(alongside the 'by_id' filter). Distributions hang off schedules, so "
    "the schedule hop is always needed to reach them.\n"
    "- 'POs created before 2015' / 'purchase orders created since March "
    "2024' -> target_entity 'PurchaseOrder' with a 'created_before' or "
    "'created_since' filter whose value is an ISO date 'YYYY-MM-DD'. A "
    "date bound satisfies the PurchaseOrder root requirement, so no PO id "
    "is needed. Use ONLY when the question names an ABSOLUTE date or "
    "year. If it says something RELATIVE — 'older than 6 months', 'stale', "
    "'in the last year' — do NOT compute the date yourself and do NOT set "
    "these filters; relative PO date windows are not supported yet, so "
    "set unanswerable.\n"
    "- 'invoices for PO 162034' / 'invoices raised against PO X' / 'which "
    "invoices reference this PO' -> target_entity 'Invoice' with a "
    "'purchase_order' filter whose value is the PO NUMBER exactly as "
    "written (e.g. '162034'). This is an Invoice query, NOT a "
    "PurchaseOrder one — do not use 'by_id'.\n"
    "- 'how much of PO 2144 was received' / 'received vs ordered for PO X' "
    "/ 'has PO X been received' / 'how much has been billed against PO X' "
    "-> target_entity 'PurchaseOrder' with a 'by_id' filter AND add "
    "'POSchedule' to include. The schedule rows carry the received/billed "
    "quantities and amounts against the ordered ones.\n"
    "- 'contacts for supplier X' / 'show supplier X and its contacts' / "
    "'who are the contacts for X' / 'with the contacts' -> target_entity "
    "'Supplier' with a 'name_fragment' filter whose value is the supplier "
    "NAME X (e.g. 'EIP Inc'), and add 'Contact' to the include list. "
    "Identify the supplier by NAME. A bare supplier NUMBER (e.g. 'supplier "
    "1262') cannot root a Supplier query — there is no supplier-number "
    "filter — so if only a number is given and no name, this is out of "
    "scope; do not emit a 'by_id' or other invented filter.\n"
    "- 'suppliers with their addresses' / 'list suppliers with their "
    "address' / 'suppliers and their addresses' -> target_entity "
    "'Supplier' (NOT Address) with 'Address' added to include. This roots "
    "on the supplier list and nests each supplier's addresses underneath. "
    "Distinguish from 'addresses for supplier X', which roots on Address "
    "as the target — here the suppliers are the list, addresses hang off "
    "each one.\n"
    "- 'get the supplier name and number' / 'with invoice number and "
    "amount' / 'show only the city and country' -> put the EXACT column "
    "names in 'fields' (from the COLUMNS list below). Leave 'fields' empty "
    "when the question does not name specific columns.\n"
    "If a prompt mentions several of these, emit ALL of them. A common error "
    "is dropping a constraint (e.g. forgetting the country, or omitting the "
    "buyer include) — do not do this.\n\n"
    "OUT OF SCOPE — refuse, do not salvage:\n"
    "If the question needs ANY entity or filter that is not in the lists "
    "below, or is too vague to pin to a specific entity and filters, you "
    "MUST set unanswerable=true and briefly say why in unanswerable_reason. "
    "In that case do NOT guess a target_entity and do NOT map the request to "
    "the closest listed entity. It is WRONG to turn an unanswerable question "
    "into a broad in-scope query (for example, answering 'contract renewals' "
    "by listing all suppliers). Refusing is correct; salvaging is not.\n\n"
    "AGGREGATION — use the aggregate block, do NOT refuse:\n"
    "If the question asks for a RANKING or TOTAL rather than a list, set the "
    "aggregate block instead of producing a list. Pick the op by WHAT IS "
    "MEASURED — the source and the measure decide it, not just the "
    "grouping:\n"
    "- op='by_supplier' — suppliers ranked by INVOICE SPEND (what was "
    "billed). Use for 'top 10 suppliers by spend', 'which suppliers did we "
    "spend the most with last quarter', 'total invoiced by supplier in "
    "2025'. Fill date_from/date_to from any time window (as 'YYYY-MM-DD') "
    "and top_n from any 'top N' wording (default 10).\n"
    "- op='po_value_by_supplier' — suppliers ranked by PURCHASE ORDER VALUE "
    "(what was ordered/committed, NOT billed). Use for 'top 5 suppliers by "
    "purchase order value', 'which suppliers have the most committed', 'top "
    "suppliers by PO value'. Set top_n from any 'top N' wording; set "
    "status='OPEN' if the question says open/outstanding POs. This op takes "
    "NO date range — PO dates are not filterable.\n"
    "  SPEND vs PO VALUE is the distinction that matters: 'spend' and "
    "'invoiced' mean invoices (op='by_supplier'); 'purchase order value', "
    "'ordered' and 'committed' mean POs (op='po_value_by_supplier'). If the "
    "question names purchase orders, it is NOT the spend ranking.\n"
    "- op='po_count_by_status' — purchase orders broken down BY STATUS, with "
    "a count and total value per status. Use for 'how many purchase orders "
    "are there and what are they worth', 'break POs down by status', 'PO "
    "status summary'. Takes no parameters.\n"
    "- op='open_po_summary' — the committed total across OPEN purchase "
    "orders, with the count. Use for 'how much have we committed in open "
    "POs', 'what is our open PO commitment', 'total value of outstanding "
    "purchase orders'. Takes no parameters.\n"
    "Do NOT set unanswerable for any of these — they ARE supported.\n\n"
    "COMPARISON — use the compare block, do NOT refuse:\n"
    "If the question compares what was ORDERED (purchase orders) against "
    "what was INVOICED (bills) — 'invoiced vs ordered', 'over/under-"
    "invoiced', 'are the orders getting billed' — set the compare block "
    "instead of a list. Pick the op by SCOPE:\n"
    "- op='po_invoiced_vs_ordered' — ONE purchase order. Use for 'how does "
    "invoiced compare to ordered for PO 162034', 'was PO X over-invoiced'. "
    "Set po_number to the PO number exactly as written.\n"
    "- op='supplier_invoiced_vs_ordered' — ONE supplier. Use for 'how does "
    "invoiced compare to ordered for Lee Supplies'. Set supplier_name; set "
    "top_n from any 'top N' wording (default 5).\n"
    "- op='top_suppliers_invoiced_vs_ordered' — the TOP-N suppliers by PO "
    "value, each compared. Use for 'compare ordered vs invoiced for our top "
    "3 suppliers', 'invoiced vs ordered for our biggest suppliers', "
    "concentration risk. Set top_n from any 'top N' wording (default 5); "
    "set status='OPEN' if the question says open POs.\n"
    "The signal is BOTH sides: a question naming ORDERED and INVOICED "
    "together is a comparison, not an aggregation ranking (one measure) and "
    "not a list. Do NOT set unanswerable for these — they ARE supported. Do "
    "NOT set both compare and aggregate.\n\n"
    "COUNT — set count_only, do NOT refuse:\n"
    "If the question asks HOW MANY or for the COUNT of a set rather than "
    "the records — e.g. 'count of suppliers', 'how many active suppliers', "
    "'how many US suppliers' — set count_only=true. Still set target_entity "
    "and any filters as normal (the count is of that filtered set); the flag "
    "only says to report the count instead of listing. This is NOT the "
    "aggregate block — do not set both.\n\n"
    "OPEN INVOICES — set open_only, do NOT refuse:\n"
    "If a customer-invoices question (the CustomerAccount + by_customer_name "
    "+ CustomerTransaction shape above) asks for only the OPEN, OUTSTANDING, "
    "or UNPAID invoices — e.g. 'open invoices for [name]' — set "
    "open_only=true. Set target_entity, the by_customer_name filter, and the "
    "CustomerTransaction include exactly as normal; the flag only restricts "
    "the listed transactions to those still open. Leave false when there is "
    "no open/outstanding/unpaid qualifier.\n\n"
    "TOP-N OPEN INVOICES — set invoice_limit:\n"
    "If that same open-invoices question also names a row cap — e.g. 'top 5 "
    "open invoices for [name]', '[name]'s 10 largest outstanding invoices' — "
    "set invoice_limit to that number N. Set open_only=true as above; the "
    "open invoices come back highest-balance first, so invoice_limit keeps "
    "the top N. Leave invoice_limit null when no number is named, or when "
    "open_only is not set.\n\n"
    "So: capture everything when in scope; refuse cleanly when out of scope. "
    "Only produce a normal Intent (unanswerable=false) when the question maps "
    "cleanly onto the allowed entities and filters.\n"
)


def _format_menu(menu: KGMenu) -> str:
    """Render the KG menu as the allowed-vocabulary block of the prompt."""
    lines: list[str] = []

    lines.append("ALLOWED target_entity values (these have a fetcher):")
    for e in sorted(menu.target_entities):
        desc = menu.entity_descriptions.get(e, "")
        lines.append(f"  - {e}: {desc}")
    lines.append("")

    lines.append(
        "OTHER known entities (recognized, but NOT valid as target_entity — "
        "a query rooted on these is out of scope):"
    )
    others = sorted(set(menu.entity_descriptions) - set(menu.target_entities))
    for e in others:
        lines.append(f"  - {e}")
    lines.append("")

    lines.append("ALLOWED filter types:")
    for ft in sorted(menu.filter_types):
        lines.append(f"  - {ft}")
    lines.append("")

    if menu.entity_columns:
        lines.append(
            "COLUMNS per entity (use these EXACT names when the question "
            "asks for specific fields; put them in 'fields'):"
        )
        for e in sorted(menu.entity_columns):
            cols = ", ".join(menu.entity_columns[e])
            lines.append(f"  - {e}: {cols}")
        lines.append("")

    lines.append(
        "COUNTRY values accepted (map any of these terms to the canonical "
        "code on the right when building a 'country' filter):"
    )
    for term, canonical in sorted(menu.country_terms.items()):
        lines.append(f"  - {term} -> {canonical}")

    return "\n".join(lines)


def _build_system_prompt(menu: KGMenu) -> str:
    return _SYSTEM_PROMPT_PREAMBLE + "\n" + _format_menu(menu)


def parse(
    prompt: str,
    llm: Any | None = None,
    menu: KGMenu | None = None,
) -> ParseResult:
    """Parse a natural-language prompt into a ParseResult.

    Args:
        prompt: The user's natural-language question.
        llm: Optional pre-built LangChain LLM. Tests inject a mock whose
            ``with_structured_output(DraftIntent).invoke(...)`` returns a
            canned DraftIntent (or dict). Production passes None and a fresh
            ChatGoogleGenerativeAI is built (reads GEMINI_API_KEY).
        menu: Optional pre-loaded KGMenu. Tests pass a fixture to avoid a DB
            hit; production passes None and the menu is read synchronously
            from the KG via load_kg_menu().

    Returns:
        ParseResult — ``ok`` wrapping an Intent when the LLM produced a
        shape-valid draft, or a ``refuse`` with flavor UNPARSEABLE when the
        LLM produced nothing usable or a malformed value.

        NOTE (checkpoint 2): a shape-valid draft is NOT yet validated against
        the KG. Entity/filter KG-checks (and their UNKNOWN_ENTITY /
        UNSUPPORTED_FILTER / UNSUPPORTED_OPERATION refusals) arrive in
        checkpoint 3.
    """
    if menu is None:
        menu = load_kg_menu()

    if llm is None:
        # Imported lazily so unit tests (which inject a mock) don't require
        # an LLM dep or API key to import this module. build_llm picks the
        # configured provider (gemini today).
        from spire.config import build_llm

        llm = build_llm(_TEMPERATURE)

    structured_llm = llm.with_structured_output(DraftIntent, include_raw=True)
    system_prompt = _build_system_prompt(menu)

    result = structured_llm.invoke(
        [("system", system_prompt), ("human", prompt)]
    )

    # With include_raw=True the real LLM returns
    # {"raw": AIMessage, "parsed": DraftIntent|None, "parsing_error": ...}.
    # Unit tests inject a mock that returns the bare model (or a dict);
    # handle both so token logging never breaks the mock path.
    if isinstance(result, dict) and "parsed" in result:
        from spire.config import log_usage

        log_usage(result.get("raw"), stage="parse")
        response = result["parsed"]
    else:
        response = result

    # Normalize to a DraftIntent (the synthesizer guards the same way: some
    # backends return a dict rather than the model instance).
    if isinstance(response, dict):
        response = DraftIntent(**response)

    if response is None:
        return ParseResult.refuse(
            flavor=RefusalFlavor.UNPARSEABLE,
            detail="The model did not produce a structured Intent for this prompt.",
        )

    # The model explicitly declared the prompt out of scope (the structural
    # half of the silent-rewrite fix). Trust the REFUSAL, but don't trust the
    # model to know WHICH kind of refusal it is — feature 1 tagged every
    # self-declared refusal UNPARSEABLE. Feature 8 re-derives the flavor from
    # the draft + KG menu (UNKNOWN_ENTITY for contracts, UNSUPPORTED_OPERATION
    # for aggregation), falling back to UNPARSEABLE only when nothing more
    # specific fits.
    if response.unanswerable:
        reason = response.unanswerable_reason or "The prompt is out of scope."
        flavor = derive_flavor(reason, response.target_entity, menu)
        offending = (
            response.target_entity
            if flavor is RefusalFlavor.UNKNOWN_ENTITY and response.target_entity
            else None
        )
        return ParseResult.refuse(
            flavor=flavor,
            detail=reason,
            offending_entity=offending,
        )

    # Shape-level conversion. A malformed filter value (non-JSON) is an
    # unparseable result, not a crash.
    try:
        intent = response.to_intent()
    except ValueError as exc:
        return ParseResult.refuse(
            flavor=RefusalFlavor.UNPARSEABLE,
            detail=f"The model's Intent was malformed: {exc}",
        )

    # Feature 7: an aggregation intent is validated by the planner's
    # aggregation-op registry, not by the entity/filter KG menu (its
    # target_entity/filters are unused). Skip validate_intent, which
    # would reject it for not having a KG-valid target entity.
    if intent.aggregate is not None:
        return ParseResult.ok(intent)

    # P6c: a comparison intent is validated by the planner's comparison-op
    # registry, not the entity/filter KG menu (its target_entity/filters
    # are unused). Skip validate_intent, same as aggregate — otherwise it
    # refuses the empty target_entity at Gate 1.
    if intent.compare is not None:
        return ParseResult.ok(intent)

    # Q2 direction 2: validate the draft back against the KG. Out-of-scope
    # entities/filters become typed refusals (checkpoint 3).
    refusal = validate_intent(intent, menu)
    if refusal is not None:
        return ParseResult(refusal=refusal)

    return ParseResult.ok(intent)
