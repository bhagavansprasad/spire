# SPIRE — session status snapshot, 2026-11-19

**Purpose.** A complete, evidence-backed capture of where the KG-schema
corpus and SQL-emitter work stands at this window close, so the next
session does not have to re-derive it. Every number below was produced by
a command run in this window; the command/artifact is named beside it.

**Resume in one line.** `master` is clean at `02d6e91`; the KG seed
rebuilds to 22/127/12 and the §3.4 self-check passes; three items are
open — prompt-13's runtime empty answer (highest harm), F-076 (BU
scoping decision), F-070's tax-line id mismatch.

---

## 1. Repository state

| Fact | Value | Evidence |
|---|---|---|
| Branch | `master`, up to date with `origin/master` | `git status --short --branch` |
| HEAD | `02d6e91` | `git log --oneline -1` |
| Working tree | clean (no modified, no untracked) | `git status --short` → empty |
| Last code commit | `d0219a4` (F-073/F-072/F-075) | `git log` |
| Last merge | PR #217 → merge commit `8030439` | `gh pr view 217` |

Commits in order (newest first):

```
02d6e91  gitignore: ignore root scratch evidence (.json/.csv/.sql/.out)
b4aba03  Docs: record PR #217 merge (F-073/F-072/F-075)
8030439  Merge pull request #217 (Phase3-F073-Receipt-Site-Filter)
d0219a4  F-073 customer_site filter via HZ_LOCATIONS.CITY; F-072 balances; F-075 UnappliedAmount
d0aa5b7  Merge pull request #216 (Phase3-Fix-Nullable-Keys)
```

Merged phase branches still present (left in place by convention):
`KG-Schema-Corpus`, `Phase3-F060-Amount-Carrier`,
`Phase3-Fix-Nullable-Keys`, `Phase3-KG-Receivables-RoleMaps`,
`Phase3-Validate-Kg-Schema`, `Phase3-F073-Receipt-Site-Filter`,
plus the older `SQL-Emitter-Multifield-Fix`.

**Next branch** starts off `master` (never a continuation):
`Phase3-Prompt13-Site-Receipts` (proposed), per working style §Branching.

---

## 2. KG state — all twelve tables match expectations

`/home/bhagavan/virtenv/spire/bin/python scripts/print_kg.py` → exit 0,
every table `ok`:

| Table | Rows |
|---|---|
| `kg_entity` | 22 |
| `kg_entity_field` | 227 |
| `kg_entity_sql` | 22 |
| `kg_sql_column` | 127 |
| `kg_derived_projection` | **12** |
| `kg_edge` | 17 |
| `kg_pattern` | 3 |
| `kg_vocabulary` | 131 |
| `kg_pattern_binding` | 3 |
| `kg_entity_tool` | 13 |
| `kg_entity_filter` | 37 |
| `kg_edge_tool` | 16 |

The SQL satellites are 22 entities / 127 direct columns / 12 derived
projections. The 12 derived projections are:

1. `PurchaseOrder.Ordered` — `SUM(L.UNIT_PRICE * L.QUANTITY)`
2. `PurchaseOrderLine.Ordered` — `L.UNIT_PRICE * L.QUANTITY`
3. `PurchaseOrderLine.TotalTax` — `SUM(po_distributions recoverable + nonrecoverable tax)`, NVL 0
4. `PurchaseOrderLine.Total` — line extended + tax, NVL 0
5. `POSchedule.Amount` — line `UNIT_PRICE` × schedule `QUANTITY`
6. `PODistribution.StatusCode` — line status via `PO_LINE_ID`
7. `ReceivablesInvoice.EnteredAmount` — `SUM(AMOUNT_DUE_ORIGINAL)`
8. `ReceivablesInvoice.InvoiceBalanceAmount` — `SUM(AMOUNT_DUE_REMAINING)`
9. `CreditMemo.EnteredAmount` — `SUM(EXTENDED_AMOUNT)` over lines
10. `AccountReceipt.UnappliedAmount` — `-PMT schedule AMOUNT_DUE_REMAINING`
11. `CustomerAccount.TotalOpenReceivablesForAccount` — ledger-currency, all classes
12. `CustomerAccount.TotalTransactionsDueForAccount` — ledger-currency, `INV`/`DM`, due

### Self-check

`scripts/validate_kg_schema.py` → **exit 0, `Result: PASS`**
(12 derived projections validated column-by-column against the pod; 5
nullable join keys checked, all `NULLs = 0`).

---

## 3. Test state

Targeted suites (the full suite hangs at ~47% on a pre-existing slow async
test — run files, not the whole tree):

```
tests/test_sql_emitter.py tests/test_kg_metadata.py
tests/test_sql_overlay_coverage.py tests/test_kg_loader.py
→ 41 passed in 1.56s
```

Coverage of this window's work: four new emitter tests —
`test_standard_receipt_customer_site_resolves_name_not_absent_column`,
`test_standard_receipt_customer_name_and_site_both_filter`,
`test_customer_account_balances_use_ledger_currency_aggregates`,
`test_account_receipt_unapplied_amount_reads_pmt_schedule`.

---

## 4. Runtime state (dev)

`./spire-host.sh --status` → MCP 4001 up, API 4002 up, UI 4003 up;
production ports 5000–5002 down (expected).

MCP runs with **reload mode enabled**, so a `src/spire/` edit restarts it
automatically — the holder PID legitimately differs from the recorded
supervisor PID. No errors in `logs/mcp.log`.

---

## 5. Findings ledger

### Fixed and verified this corpus of work

| ID | What | Carrier / fix |
|---|---|---|
| F-060 | `PurchaseOrderLine.amount` bound a stub column | derived `UNIT_PRICE × QUANTITY` |
| F-062 | `POSchedule.amount` bound a stub column | line `UNIT_PRICE` × schedule `QUANTITY` |
| F-063 | `Total`/`TotalTax` read a stub tax column | `PO_DISTRIBUTIONS_ALL` tax, NVL 0 |
| F-064 | PO status named absent `AUTHORIZATION_STATUS` | `DOCUMENT_STATUS` |
| F-065 | `search_purchase_orders.supplier_id` matched `SEGMENT1` | `VENDOR_ID` |
| F-066 | `CustomerTransaction.TransactionId` | `CUSTOMER_TRX_ID` |
| F-067 | `ReceivablesInvoice` header stubs | derived amounts; `COMPLETE_FLAG` |
| F-068 | `AccountCreditMemo.CreditMemoId` | `CUSTOMER_TRX_ID` |
| F-069 | `AccountReceiptApplication` account path | via receipt `PAY_FROM_CUSTOMER` |
| F-070 | `ReceivablesTaxLine` pointed at the wrong table | `ZX_LINES` (one open item) |
| F-071 | DFF overlay entity name mismatch | renamed to `ReceivablesInvoiceTransactionDFF` |
| F-072 | `CustomerAccount` balances had "no clean carrier" | ledger-currency `ACCTD_AMOUNT_DUE_REMAINING`; **29/29 accounts** |
| F-073 | `customer_site` filter named an absent column | site chain → `HZ_LOCATIONS.CITY`; 1,735 = REST |
| F-074 | `StandardReceipt` INNER join dropped 39 receipts | LEFT JOIN with NULL propagation |
| F-075 | `AccountReceipt.UnappliedAmount` overstates | PMT schedule remaining; **8/8 receipts** |

### Decided, no code change

- **F-061** — buyer name `"May Gee"` (SQL) vs `"Gee, May"` (REST).
  Cosmetic; `LAST_NAME`/`FIRST_NAME` are on the same row, so this is a
  display-formatting choice. Leave as-is.

### Open

| ID | Class | Summary | Next action |
|---|---|---|---|
| **Prompt-13 runtime** (unnumbered — needs an F-ID) | **Wrong answer** | `Show receipts for ABC Corporation Americas at Santa Clara` answers *"No receipts found"* although 742 exist: the tool server-filters by account, over-fetches the newest 500, and filters site client-side — and the newest 500 are all null-site. Truncation *is* disclosed, but the prose says "No receipts found". The emitted SQL now carries the complete answer (745 rows vs REST 742). | Choose: server-side `q=CustomerSite` first (1,735 site-wide) then match account client-side; or paginate until N matches; or disclose-only. Record as F-077. |
| **F-076** | Candidate | Emitted AR SQL has no `ORG_ID`/BU predicate, so it is a business-unit **superset** of REST. Account 26370 exists in three orgs (1,692 REST BU + 605 + 544). This is why the site query returns 745 vs REST's 742 (3 extra receipts in `ORG_ID=300000047498175`). | Needs a product decision: bind session BU, or document BU-superset as intentional. Do **not** guess a BU id. |
| **F-070 open item** | Candidate | REST `CustomerTransactionLineId` on a tax line is the GL-dist id (112/113); the role map binds `ZX_LINES.TAX_LINE_ID` (9039/9040) — different id spaces. | Decide whether to re-point the canonical id at the GL-dist line id. |

---

## 6. Standing operational notes

- **Interpreter:** `/home/bhagavan/virtenv/spire/bin/python` — bare
  `python`/`pytest` lack `oracledb`.
- **Pod SQL validator:** `./runsql.sh "<SQL>"` (`FORMAT=csv` for parseable
  output; `-f file.sql` to run from a file). One statement per file — the
  report chokes on multi-statement input.
- **Restart:** `export PATH="/home/bhagavan/virtenv/spire/bin:$PATH"`
  before `./spire-host.sh --restart dev`, else MCP/API/UI fail to bind
  (`spire-host.sh` calls bare `python`/`fastmcp`).
- **`git pull origin master`** can fail with "Cannot fast-forward to
  multiple branches"; the working equivalent is
  `git fetch origin && git merge --ff-only origin/master`.
- **Scratch evidence:** root `t_*` files are gitignored (`.txt` historically,
  and `.json`/`.csv`/`.sql`/`.out` since `02d6e91`); `scripts/t_s1_*.py`
  stays tracked. Evidence is cited by filename in `FIX_PLAN.md`.
- **DBMS_XMLGEN quirks:** trailing statements after the first are ignored
  or error; scalar subqueries in `GROUP BY` raise ORA-22818; a NULL-only
  result set can raise ORA-24333.
- **Column existence ≠ populated.** `t_task2_all.txt` proves a column
  exists; a `COUNT(col)` proves it carries data. The R-7 stub class (F-060,
  F-062, F-063, F-067) is entirely this distinction.

---

## 7. What the SQL emitter does today

- Columns for all 22 entities come from the KG
  (`kg_sql_column` + `kg_derived_projection`) via `kg_sql_loader.py` and
  `_kg_backed_overlay()`; `emit_sql(plan)` defaults to the KG-backed
  overlay.
- **Filters remain hand-authored** in `sql_overlay.py` (`_FILTERS`), as do
  the Receivables `EntitySpec` shells (joins and aliases).
- Emitted SQL is **validated by execution** (`runsql.sh`) *and* by
  agreement with Spire's REST answer. "It executes" is not the bar.
- Emitted SQL is **not yet self-contained** where a step iterates: the
  `:iteration_value` bind is unbound at emission. Two candidate mechanisms
  are recorded but **undecided** (sentinel-resolving driver vs
  plan→single-query composition).

---

## 8. Recommended next session

1. **Prompt-13 runtime empty answer** — highest harm (wrong answer on a
   primary prompt). Record as F-077, reproduce, decide the filter strategy,
   verify against REST.
2. **F-076** — bring a recommendation and get the scoping decision.
3. **F-070 open item** — narrow; finish when the id-space question is
   settled.

Verification bar for all three: emitted SQL **runs** via `runsql.sh`
**and agrees** with the REST answer.
