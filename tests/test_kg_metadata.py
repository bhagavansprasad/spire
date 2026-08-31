

"""Integration tests for the KG metadata tables in Oracle.

These verify that the v1 KG, populated by scripts/rebuild_kg.sh,
is readable from Spire code via OracleClient. They are not unit tests —
they hit the real Oracle 26ai container and assume the seed scripts
have run.

If a test here fails, the most likely cause is that the SPIRE schema
is empty or stale. To repopulate:

    ./scripts/rebuild_kg.sh

Skipped if personas.yaml is missing — same gate as the other
integration tests.

Note on CLOB columns:
oracledb's async driver returns CLOB values as AsyncLOB *handles*,
not as strings. Reading them goes back over the wire, which means
the read must happen INSIDE the `async with OracleClient(...)` block,
before the connection closes. Tests below follow this discipline.
"""

import json

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.oracle.client import OracleClient


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


async def _read_clob(value) -> str:
    """Coerce a possibly-CLOB column value to a Python str.

    MUST be called while the OracleClient connection is still open
    (i.e. inside the `async with` block that produced `value`).
    AsyncLOB.read() is a network round-trip; closing the connection
    first will raise DPY-1001 ("not connected to database").
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return await value.read()


# ----- Counts and basic existence ------------------------------------


@pytest.mark.asyncio
async def test_kg_entity_has_twentytwo_rows():
    """Entities: Supplier, Invoice, PurchaseOrder, Buyer, Address, Site,
    Classification, PurchaseOrderLine.

    Phase 12 added Site (supplier sites child). Phase 13 added
    Classification (supplier businessClassifications child), used by the
    has_classification edge filter. P2 added PurchaseOrderLine (the PO
    lines child), used by the HAS_LINE expansion edge. P4 added Contact (supplier contacts child), used by
    the HAS_CONTACT expansion edge. P3b added PODistribution (the
    deepest PO child), used by the HAS_DISTRIBUTION multi-field
    iteration edge. AR-P2 added ReceivablesInvoice (the AR invoice header,
    fetched by_id on CustomerTransactionId) and ReceivablesInvoiceLine
    (its lines child, reached via the HAS_AR_LINE expansion edge).
    AR-P2b added CustomerAccount (the AR customer account, resolved by
    CustomerName) and CustomerTransaction (the account's payment-schedule
    transactions, reached via the HAS_CUSTOMER_TRANSACTION expansion edge).
    AR-P3 added ReceivablesTaxLine (the invoice-line tax grandchild,
    reached via HAS_TAX_LINE) and ReceivablesInvoiceTransactionDFF (the
    invoice TransactionDFF child, reached via HAS_TRANSACTION_DFF).
    AR-P4 added CreditMemo (the top-level receivablesCreditMemos resource,
    listed by its own fetcher — a rooted entity, no edge).
    AR-P5 prompt 7 added AccountCreditMemo (the per-account creditMemos
    child, reached via HAS_ACCOUNT_CREDIT_MEMO). It is a DIFFERENT entity
    from CreditMemo: different id space (CreditMemoId vs
    CustomerTransactionId) and a different field projection — the
    installment view rather than the transaction view.
    AR-P5 prompt 8 added AccountReceipt (the per-account standardReceipts
    child, reached via HAS_ACCOUNT_RECEIPT) — cash received from a
    customer. The same receipts are also reachable via the TOP-LEVEL
    /standardReceipts resource with a DIFFERENT projection (Status vs
    ProcessStatus, plus customer and bank columns), and the two disagree
    on count; only the child is modeled as an entity.
    """
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT entity_name FROM kg_entity ORDER BY entity_name"
        )
    names = [row[0] for row in rows]
    assert names == [
        "AccountCreditMemo", "AccountReceipt", "AccountReceiptApplication",
        "Address", "Buyer", "Classification", "Contact", "CreditMemo",
        "CustomerAccount", "CustomerTransaction", "Invoice",
        "PODistribution", "POSchedule", "PurchaseOrder",
        "PurchaseOrderLine", "ReceivablesInvoice", "ReceivablesInvoiceLine",
        "ReceivablesInvoiceTransactionDFF", "ReceivablesTaxLine", "Site",
        "StandardReceipt", "Supplier"
    ]

@pytest.mark.asyncio
async def test_kg_entity_module_mapping():
    """Every entity carries its correct Fusion module.

    Phase 1 (parser context modularization) added a `module` column to
    kg_entity: the KG's source of truth for which Fusion module an entity
    belongs to, read by the selective-load harness and the Phase-2 router.
    The CHECK constraint guarantees the value is one of the four modules, but
    NOT that it is the RIGHT one — this test pins the actual mapping so a
    mis-assignment (e.g. a PO tagged 'receivables') fails loudly instead of
    silently mis-scoping router context.

    Children take the module of the endpoint they hang off (a PO line is
    procurement, a tax line is receivables). See
    docs/features/parser_context_modularization.md §4.3.
    """
    expected = {
        # payables
        "Invoice": "payables",
        # procurement
        "PurchaseOrder": "procurement",
        "PurchaseOrderLine": "procurement",
        "PODistribution": "procurement",
        "POSchedule": "procurement",
        "Buyer": "procurement",
        # receivables
        "ReceivablesInvoice": "receivables",
        "ReceivablesInvoiceLine": "receivables",
        "ReceivablesTaxLine": "receivables",
        "ReceivablesInvoiceTransactionDFF": "receivables",
        "CreditMemo": "receivables",
        "AccountCreditMemo": "receivables",
        "CustomerAccount": "receivables",
        "CustomerTransaction": "receivables",
        "StandardReceipt": "receivables",
        "AccountReceipt": "receivables",
        "AccountReceiptApplication": "receivables",
        # supplier
        "Supplier": "supplier",
        "Address": "supplier",
        "Site": "supplier",
        "Classification": "supplier",
        "Contact": "supplier",
    }

    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT entity_name, module FROM kg_entity ORDER BY entity_name"
        )
    actual = {row[0]: row[1] for row in rows}

    # Collect every discrepancy before asserting (same discipline as the
    # row-count test) so one run surfaces all of them.
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    wrong = sorted(
        f"{name}: expected {expected[name]!r}, got {actual[name]!r}"
        for name in expected
        if name in actual and actual[name] != expected[name]
    )

    problems = []
    if missing:
        problems.append(f"entities missing from kg_entity: {missing}")
    if unexpected:
        problems.append(f"unexpected entities in kg_entity: {unexpected}")
    if wrong:
        problems.append("wrong module:\n  " + "\n  ".join(wrong))

    assert not problems, "entity->module mapping drifted:\n" + "\n".join(problems)
    
@pytest.mark.asyncio
async def test_kg_table_row_counts_match_v1_1():
    """All 9 KG tables match the current row counts.

    v1.0 had 5 tables; v1.1 added 3 more (kg_pattern_binding,
    kg_entity_tool, kg_edge_tool) for the planner.
    The KG-expansion work added a 9th (kg_entity_filter) to hold filter
    definitions formerly hardcoded in the planner.
    v1.0 had 2 patterns (status_filter, country_filter_via_address);
    F2 added a 3rd (no_child_in_N_months) for the negation-by-absence
    semantic.
    kg_entity_tool is now 3 (Supplier default, Invoice default, Address
    default). The country filter has no dedicated tool; it routes through
    the default supplier fetcher with combined args.
    Phase 8 added the supplier business_relationship filter: +1 filter row
    (kg_entity_filter 11->12) and +2 vocab rows (kg_vocabulary 44->46).
    Phase 11 added the has_invoice_over_amount edge filter: +1 filter row
    (kg_entity_filter 12->13).
    Phase 12 added the has_site_in_bu edge filter (suppliers by site
    ProcurementBU): +1 entity (Site, 5->6), +1 edge (HAS_SITE, 4->5),
    +1 edge tool (HAS_SITE, 3->4), +1 filter row (kg_entity_filter
    13->14), and +10 vocab rows (supplier_site_bu, 46->56).
    Phase 13 added the has_classification edge filter (suppliers by
    business classification): +1 entity (Classification, 6->7), +1 edge
    (HAS_CLASSIFICATION, 5->6), +1 edge tool (HAS_CLASSIFICATION, 4->5),
    +1 filter row (kg_entity_filter 14->15), and +9 vocab rows
    (supplier_classification, 56->65).
    P2 (PO detail + lines) added a single-PO fetch and its line
    children: +1 entity (PurchaseOrderLine, 7->8), +12 line fields
    plus +2 PurchaseOrder projection fields (Total, TotalTax)
    (kg_entity_field 27->41), +1 edge (HAS_LINE, 6->7), +1 edge tool
    (HAS_LINE, 5->6), +1 entity tool (PurchaseOrder by_id, 3->4), and
    +1 filter row (PurchaseOrder by_id, kg_entity_filter 15->16). No
    new vocab.
    AR-P2 (AR invoice detail + lines) added a by-id AR-invoice fetch and
    its line children: +2 entities (ReceivablesInvoice,
    ReceivablesInvoiceLine, 11->13), +27 fields (14 header + 13 line,
    kg_entity_field 84->111), +1 edge (HAS_AR_LINE, 10->11), +1 edge tool
    (HAS_AR_LINE, 9->10), +1 entity tool (ReceivablesInvoice by_id, 5->6),
    +1 filter row (ReceivablesInvoice by_id, kg_entity_filter 19->20), and
    +4 vocab rows (AR-invoice entity synonyms, 81->85).
    AR-P2b (customer invoices via account) added the customer-account
    resolve + transaction traversal: +2 entities (CustomerAccount,
    CustomerTransaction, 13->15), +14 fields (6 account + 8 transaction,
    111->125), +1 edge (HAS_CUSTOMER_TRANSACTION, 11->12), +1 edge tool
    (11), +1 entity tool (CustomerAccount by_customer_name, 6->7), +1 filter
    row (by_customer_name, 20->21). No new vocab.
    AR-P3 tax lines added the invoice-line tax grandchild: +1 entity
    (ReceivablesTaxLine, 15->16), +12 fields (125->137), +1 edge
    (HAS_TAX_LINE, 12->13), +1 edge tool (12). No new entity tool, filter,
    or vocab (extends an existing traversal, not a rooted entity).
    AR-P3 DFF (prompt 4) added the invoice TransactionDFF child: +1 entity
    (ReceivablesInvoiceTransactionDFF, 16->17), +3 fields (137->140), +1
    edge (HAS_TRANSACTION_DFF, 13->14), +1 edge tool (12->13). A plain
    single-parent expansion (like HAS_AR_LINE); no entity tool, filter, or
    vocab. The DFF child echoes the parent id as CustomerTrxId (short
    spelling), not CustomerTransactionId.
    AR-P4 credit memos (prompts 5, 14) added the top-level
    receivablesCreditMemos resource as a ROOTED entity: +1 entity
    (CreditMemo, 17->18), +8 fields (140->148), +1 entity tool (CreditMemo
    none/list_receivables_credit_memos, 7->8), +2 vocab rows (credit-memo
    entity synonyms, 85->87). No edge (top-level, no traversal) and no
    entity filter (list-only; the default fetcher orders recent-first and
    limits server-side).
    AR-P5 prompt 7 (account credit memos) added the per-account
    creditMemos child as a TRAVERSED entity: +1 entity (AccountCreditMemo,
    18->19), +10 fields (148->158), +1 edge (HAS_ACCOUNT_CREDIT_MEMO,
    14->15), +1 edge tool (13->14), +2 vocab rows (account-scoped memo
    synonyms, 87->89). No entity tool (reached by traversal, not rooted)
    and no entity filter (the edge carries the account id; there is
    nothing to filter on). NOTE the vocab rows deliberately cover only
    the ACCOUNT-SCOPED terms — bare 'credit memo'/'credit memos' stay
    bound to AR-P4's CreditMemo, so a prompt naming no customer still
    routes to the top-level list.
    AR-P5 prompt 8 (account receipts) added the per-account
    standardReceipts child as a TRAVERSED entity: +1 entity
    (AccountReceipt, 19->20), +11 fields (158->169), +1 edge
    (HAS_ACCOUNT_RECEIPT, 15->16), +1 edge tool (14->15), +4 vocab rows
    (receipt synonyms, 89->93). No entity tool (reached by traversal) and
    no entity filter. Unlike the credit-memo vocab, the BARE terms
    'receipt'/'receipts' are bound here — nothing else in the KG claimed
    them, and Spire models no PO receiving transaction to collide with.

    The standard-receipts work added TWO entities (20->22), +25 fields
    (169->194), +1 edge (16->17), +1 edge tool (15->16), +2 entity tools
    (8->10), +4 filter rows (21->25) and +4 vocab rows (93->97). COL-02
    multi-field expansions add +6 vocab rows (97->103): who/audit columns,
    creator details. COL-02 single-field synonyms add +15 vocab rows
    (103->118): legacy EBS (vendor/vendor number/trx) and field-level
    (creation/updated dates, qty, uom).
    StandardReceipt is the TOP-LEVEL /standardReceipts resource, ROOTED,
    with two fetchers of its own (search and aggregate-by-method) — hence
    +2 entity tools and no edge. AccountReceiptApplication is the
    per-receipt applications child, reached by traversal — hence the edge
    and edge tool, and no entity tool.

    Two later corrections. (1) A stale StandardReceipt account_number
    filter was removed (25->24 then ->23 with the lag row below): the
    tool takes customer_name/customer_site and has no account_number
    parameter, so the row built an argument the tool rejects. (2) A
    lag_query filter and a get_receipts_with_lag entity tool were live
    in the DATABASE but in neither the seed nor master — the code is on
    feature/ar-prompt-18-parking. The KG was advertising a tool the
    running server does not have. Both rows are gone (kg_entity_tool
    10->9, kg_entity_filter 24->23) and belong with prompt 18 when it
    lands. Seed and database now agree; before this they did not, and a
    rebuild would have silently changed behaviour.

    NOTE this REVERSES a decision recorded above. AR-P5 prompt 8 stated
    that the top-level resource was deliberately NOT modeled ("only the
    child is modeled as an entity") because its projection differs from
    the child's AND THE TWO DISAGREE ON COUNT. Both are modeled now. Two
    entities over the same underlying receipts, with different
    projections and different counts, are both routable by the planner —
    so two near-identical prompts can return different numbers. That is a
    modelling hazard rather than a test concern, but this row count is
    where it becomes visible, so it is recorded here.

    Module 5 phase 5 (PO lifecycle) added the lifecycle reconciliation as
    a FILTER on the existing PurchaseOrder entity, not as an entity of its
    own: +1 entity tool (PurchaseOrder/lifecycle_status ->
    get_purchase_order_lifecycle_status, 9->10) and +1 filter row
    (kg_entity_filter 23->24). Nothing else moved.

    No new entity, because the vocabulary already binds 'purchase order',
    'PO' and 'order' to PurchaseOrder — a POLifecycle entity would compete
    with those for the same words and lose. The lifecycle view is not a
    different thing, it is a different QUESTION about the same PO, which
    is what filter_type expresses. PurchaseOrder/by_id is the precedent.

    No new kg_entity_field rows either. The tool returns paid_state, risk,
    recommended_action, setup and schedules, none of which is a field on
    /purchaseOrders — they are the tool's return contract (pinned by
    tests/test_po_lifecycle_tool.py::test_result_shape_is_stable) and are
    consumed by the synthesizer. kg_entity_field catalogs what the
    ENDPOINT exposes; a computed field there would misdescribe it.

    One filter, not three, although five catalog prompts (A.2, A.3, A.4,
    A.7, A.10) route here across three output shapes. They ask for the
    same DATA and differ only in rendering, which is the synthesizer's
    choice, not the planner's.

    COL-03 layer 3 (2026-08-04) added FOUR who-columns to Supplier as
    projectable fields (kg_entity_field 194->198): CreatedBy, CreationDate,
    LastUpdatedBy, LastUpdateDate. Curl-confirmed on /suppliers — they
    exist, return real values, and survive fields= projection. Role
    'projection' (display-only; the creation-date FILTER already exists
    separately in kg_entity_filter). No other table moved.

    COL-02 Group 4 (2026-08-12) extended the same four who-columns to
    PurchaseOrder, Invoice and ReceivablesInvoice (kg_entity_field
    198->210, +12 = 4 x 3 entities): CreatedBy, CreationDate,
    LastUpdatedBy, LastUpdateDate. Curl-confirmed on /purchaseOrders,
    /invoices and /receivablesInvoices — all four exist with real values.
    Makes the existing 'who columns'/'audit columns' field_synonym resolve
    on these entities too (the synonym is global; it needed the target
    columns to exist).

    NOTE the counts in this test are one of FOUR places that must move
    together, not two as earlier notes implied: this dict,
    scripts/print_kg.py's expected_rows, and the two
    "PROMPT Seeded ... (N rows)" banners inside the seed file itself.
    """
    persona = load_persona("default_dev")
    expected = {
        "kg_entity": 22,
        "kg_entity_field": 210,
        "kg_edge": 17,
        "kg_pattern": 3,
        "kg_vocabulary": 120,
        "kg_pattern_binding": 3,
        "kg_entity_tool": 10,
        "kg_entity_filter": 24,
        "kg_edge_tool": 16,
    }
    # Collect ALL mismatches before asserting. The previous loop asserted
    # per table and stopped at the first failure, so a phase that moved
    # several counts surfaced them one run at a time.
    actual: dict[str, int] = {}
    async with OracleClient(persona) as oc:
        for table in expected:
            row = await oc.fetch_one(f"SELECT COUNT(*) FROM {table}")
            assert row is not None, f"{table}: COUNT(*) returned nothing"
            actual[table] = row[0]

    mismatches = [
        f"{table}: expected {expected[table]}, got {actual[table]}"
        for table in expected
        if actual[table] != expected[table]
    ]
    assert not mismatches, (
        "KG row counts drifted:\n  " + "\n  ".join(mismatches)
    )


# ----- The asymmetry that crashed Track A ----------------------------


@pytest.mark.asyncio
async def test_edge_join_field_asymmetry_supplier_number_vs_supplier_id():
    """The SupplierNumber-vs-SupplierId asymmetry is encoded correctly.

    Track A's baseline runs 4 and 5 crashed because the agent passed
    supplier_number to a tool that expects supplier_id (and vice versa).
    The KG records the right join field per edge so phase 04+ tools
    can read it instead of guessing.
    """
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT edge_name, from_join_field, to_join_field "
            "FROM kg_edge "
            "WHERE edge_name IN ('HAS_INVOICE', 'HAS_PURCHASE_ORDER') "
            "ORDER BY edge_name"
        )
    edges = {row[0]: (row[1], row[2]) for row in rows}
    # HAS_INVOICE joins via SupplierNumber (the invoices endpoint exposes that, not SupplierId).
    assert edges["HAS_INVOICE"] == ("SupplierNumber", "SupplierNumber")
    # HAS_PURCHASE_ORDER joins via SupplierId (the PO endpoint exposes that, not SupplierNumber).
    assert edges["HAS_PURCHASE_ORDER"] == ("SupplierId", "SupplierId")


@pytest.mark.asyncio
async def test_assigned_to_edge_crosses_pillars():
    """ASSIGNED_TO encodes the FSCM->HCM cross-pillar lookup."""
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        row = await oc.fetch_one(
            "SELECT from_entity, to_entity, from_join_field, to_join_field, notes "
            "FROM kg_edge WHERE edge_name = 'ASSIGNED_TO'"
        )
        assert row is not None
        from_entity, to_entity, from_field, to_field, notes = row
        # Read CLOB-able fields inside the `async with` block.
        notes_str = await _read_clob(notes)
    # Plain assertions can happen after close — these are normal Python values.
    assert from_entity == "PurchaseOrder"
    assert to_entity == "Buyer"
    assert from_field == "BuyerId"
    assert to_field == "PersonId"
    # The notes field must explicitly mention cross-pillar so the agent sees it.
    assert "CROSS-PILLAR" in notes_str.upper()


# ----- FK relationships -----------------------------------------------


@pytest.mark.asyncio
async def test_supplier_has_projection_fields():
    """FK from kg_entity_field to kg_entity works; Supplier has its
    declared projection fields — the original four (SupplierId,
    SupplierNumber, Supplier, Status) plus the four COL-03 who-columns
    (CreatedBy, CreationDate, LastUpdatedBy, LastUpdateDate). Eight total.

    Order below is ASCII (ORDER BY field_name): uppercase sorts before
    lowercase, so LastUpdateDate precedes LastUpdatedBy."""
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT field_name FROM kg_entity_field "
            "WHERE entity_name = 'Supplier' "
            "ORDER BY field_name"
        )
    field_names = [row[0] for row in rows]
    assert field_names == [
        "CreatedBy",
        "CreationDate",
        "LastUpdateDate",
        "LastUpdatedBy",
        "Status",
        "Supplier",
        "SupplierId",
        "SupplierNumber",
    ]


# ----- Vocabulary lookups --------------------------------------------


@pytest.mark.asyncio
async def test_country_vocabulary_resolves_us_aliases():
    """All four US-aliasing terms resolve to canonical 'US'."""
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT term, canonical_value FROM kg_vocabulary "
            "WHERE vocab_kind = 'country' AND canonical_value = 'US' "
            "ORDER BY term"
        )
    terms = [row[0] for row in rows]
    # Sort order: 'US' < 'USA' < 'United States' < 'United States of America' lexicographically.
    assert terms == [
        "US",
        "USA",
        "United States",
        "United States of America",
    ]
    # Every row maps to canonical 'US'.
    assert all(row[1] == "US" for row in rows)


@pytest.mark.asyncio
async def test_po_status_open_synonyms():
    """Both 'open' and 'active' map to StatusCode 'OPEN'."""
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT term, canonical_value FROM kg_vocabulary "
            "WHERE vocab_kind = 'po_status' AND canonical_value = 'OPEN' "
            "ORDER BY term"
        )
    by_term = {row[0]: row[1] for row in rows}
    assert by_term == {"active": "OPEN", "open": "OPEN"}


# ----- Patterns (parameters parse as JSON) ----------------------------


@pytest.mark.asyncio
async def test_no_child_in_n_months_pattern_has_parseable_parameters():
    """kg_pattern.parameters is stored as a JSON string. It must parse,
    and the no_child_in_N_months pattern (added in F2 for negation-by-
    absence) must declare parent, child_edge, date_field, and months_param.

    This pattern is the KG side of the 'has_no_recent_invoices' filter:
    keep parent entities whose per-iteration call returned empty.
    """
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        row = await oc.fetch_one(
            "SELECT parameters FROM kg_pattern "
            "WHERE pattern_name = 'no_child_in_N_months'"
        )
        assert row is not None
        # Read CLOB inside the `async with` block; the connection must
        # still be open when AsyncLOB.read() runs.
        params_str = await _read_clob(row[0])
    params = json.loads(params_str)
    param_names = {p["name"] for p in params}
    assert param_names == {"parent", "child_edge", "date_field", "months_param"}








