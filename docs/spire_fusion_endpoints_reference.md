# Spire Fusion Endpoints Reference

**Purpose:** A single reference for the Oracle Fusion REST endpoints used in the Spire POC. Each entry describes what the endpoint is for, how to call it, what it returns, and known quirks.

**For:** The KG experiment POC, where the property graph encodes which endpoint to call for what purpose and which join keys connect them.

**Pod:** `https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`
**Auth:** Basic Auth (use `-u "$FUSION_USERNAME:$FUSION_PASSWORD"`)
**API version path:** `/fscmRestApi/resources/11.13.18.05/` (FSCM) and `/hcmRestApi/resources/11.13.18.05/` (HCM)

---

## Discovery log

Findings observed during POC work that updated or corrected this document.

| Date | Endpoint | Discovery |
|---|---|---|
| 2026-05-20 | /invoices       | `PaidStatus` and `ApprovalStatus` exist on default response; values are display strings (`"Paid"`, `"Not required"`), not codes |
| 2026-05-20 | /purchaseOrders | Field is `Ordered` (not `OrderTotalAmount`). Also: `Total` (includes tax), `OrderDate`, `PaymentTerms`, `SupplierSiteId` exist on default response |
| 2026-05-20 | (all)           | The `?fields=...` parameter is strict: if any field in the list is invalid, the whole response is empty with no error |
| 2026-05-22 | /suppliers      | Composite `q=` clauses (e.g., `q=Supplier LIKE '%Lee%' AND Status='ACTIVE'`) silently return 0 items with HTTP 200, even when matches exist. Confirms the composite-`q=` quirk is not just on `/invoices` and `/purchaseOrders` — it applies to `/suppliers` too. Likely applies across all Fusion REST endpoints on this pod. |
---

## Environment setup (run once in your shell)

```bash
export FUSION_BASE_URL="https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com"
export FUSION_USERNAME="<your username>"
export FUSION_PASSWORD="<your password>"

# Sanity check
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?limit=1" \
  -w "\nHTTP %{http_code}\n"
```

Expected: HTTP 200 with a JSON body containing one supplier.

---

## Quick reference table

| Endpoint | Path | Purpose | Spire tool that wraps it |
|---|---|---|---|
| 1 | `/suppliers` | Find suppliers by name fragment | `search_suppliers` |
| 2 | `/suppliers?expand=addresses` | Find suppliers in a country | `search_suppliers_by_country` |
| 3 | `/invoices` | Find invoices by supplier + date | `search_invoices` |
| 4 | `/purchaseOrders` | Find POs by supplier + status | `search_purchase_orders` |
| 5 | `/publicWorkers` (HCM) | Look up a buyer by ID | `get_buyer` |

---

## Join key matrix (critical for the KG)

This is the **SupplierNumber-vs-SupplierId asymmetry** that crashed Track A:

| To search this | Use this join key on the supplier side | Numeric or string? |
|---|---|---|
| `/invoices` | `SupplierNumber` | string (e.g., `"1252"`) |
| `/purchaseOrders` | `SupplierId` | numeric (e.g., `300000047572113`) |
| `/publicWorkers` | `PersonId` | numeric (matches PO's `BuyerId`) |

**The KG must encode this per-edge.** The same conceptual entity (a supplier) is identified differently by different endpoints. Don't assume one ID works everywhere.

---

## Known Fusion quirks (apply to multiple endpoints)

These hit you on more than one endpoint, so call them out once:

1. **Composite q= filters fail**. Multi-clause q= strings (q=Field1=X AND Field2=Y) return HTTP 500 or silently empty results on every endpoint tested so far (/suppliers, /invoices, /purchaseOrders). Assume this quirk applies to all Fusion REST endpoints on this pod until proven otherwise. Workaround used in Spire: send the most selective single clause via q=, over-fetch (limit=200), filter the rest client-side.

2. **Country isn't on supplier directly.** Suppliers have addresses as a child resource. Country lookup needs `?expand=addresses`, then filter client-side for any address with matching `Country` code.

3. **No FSCM `buyers` endpoint.** Buyers are HCM workers. There is no `/fscmRestApi/.../buyers`. Use `/hcmRestApi/.../publicWorkers` with `PersonId = BuyerId`.

4. **OWSM 401 noise.** Sometimes REST calls return 401 with empty body and `WWW-Authenticate: Basic realm="owsm"` for ~30 minutes mid-day. Resolves itself. Not a credential problem; it's pod-side.

5. **Pagination via `offset` and `limit`.** Standard Fusion pattern. Default `limit` is often small (10 or 25). If you need more, pass `limit=N`. Max practical limit before things get slow: ~200.

6. **Fields parameter to project.** Use `?fields=Field1,Field2,Field3` to limit what comes back. Spire tools project to small field sets to avoid bloating LLM context.

7. **`?fields=` is strict on invalid names.** If even one field in a `?fields=...` list doesn't exist on the endpoint, the entire response comes back empty with no error and no warning. Verify each field name against a live response before relying on a projection.

---

## 1. `/suppliers` — find suppliers by name fragment

**Purpose:** Search for suppliers whose name contains a substring. Used when the user names a supplier (e.g., "find Lee Supplies").

**Spire tool:** `search_suppliers(name_contains: str)`

**Curl — search for "Lee":**

```bash
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?q=Supplier+LIKE+%27%25Lee%25%27&fields=SupplierId,SupplierNumber,Supplier,Status&limit=25" \
  | python -m json.tool
```

**The `q=` clause unencoded:** `Supplier LIKE '%Lee%'`

**Response shape (truncated):**

```json
{
  "items": [
    {
      "SupplierId": 300000047572113,
      "SupplierNumber": "1252",
      "Supplier": "Lee Supplies",
      "Status": "ACTIVE",
      "links": [...]
    },
    {
      "SupplierId": 300000133943993,
      "SupplierNumber": "1342",
      "Supplier": "Lee Testing for UK BU",
      "Status": "ACTIVE",
      "links": [...]
    }
  ],
  "count": 2,
  "hasMore": false,
  "limit": 25,
  "offset": 0,
  "links": [...]
}
```

**Fields used by Spire:** `SupplierId`, `SupplierNumber`, `Supplier`, `Status`.

**Notes:**
- `SupplierId` is the canonical ID (numeric).
- `SupplierNumber` is a human-readable string ID (used by `/invoices`).
- `Supplier` is the display name.
- `q=` here is single-clause, so it's reliable.

---

## 2. `/suppliers?expand=addresses` — find suppliers in a country

**Purpose:** Filter suppliers by country. Country lives on the child `addresses` resource, not on the supplier itself.

**Spire tool:** `search_suppliers_by_country(country: str)`

**Curl — find US suppliers:**

```bash
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?expand=addresses&fields=SupplierId,SupplierNumber,Supplier,Status,addresses&limit=200" \
  | python -m json.tool
```

**Response shape (truncated):**

```json
{
  "items": [
    {
      "SupplierId": 300000047572113,
      "SupplierNumber": "1252",
      "Supplier": "Lee Supplies",
      "Status": "ACTIVE",
      "addresses": {
        "items": [
          {
            "AddressId": 300000047572200,
            "Country": "US",
            "AddressLine1": "...",
            "City": "...",
            "State": "..."
          }
        ]
      }
    },
    ...
  ],
  "count": 200,
  "hasMore": true
}
```

**How filtering works in Spire:** the tool fetches with `expand=addresses`, then iterates client-side: a supplier matches if **any** of its addresses has `Country == "US"`. A supplier with addresses in multiple countries matches multiple country filters — that's correct behavior.

**Notes:**
- This endpoint over-fetches (limit=200) because there's no server-side filter on a nested-resource field.
- For the demo pod, US-supplier count is ~25.
- Country code is the ISO 2-letter form (`"US"`, `"GB"`, `"FR"`, etc.).

---

## 3. `/invoices` — find invoices by supplier + date

**Purpose:** Find invoices for a specific supplier, optionally filtered by date. Used for "no invoices in the last 6 months" checks.

**Spire tool:** `search_invoices(supplier_number, supplier_name, invoice_date_after)`

**Curl — invoices for supplier 1252 since 2025-11-19:**

```bash
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/invoices?q=SupplierNumber%3D%271252%27&fields=InvoiceId,InvoiceNumber,SupplierNumber,Supplier,InvoiceDate,InvoiceAmount,InvoiceCurrency,PaidStatus,ApprovalStatus&limit=200" \
  | python -m json.tool
```

**The `q=` clause unencoded:** `SupplierNumber='1252'`

**Response shape (truncated):**

```json
{
  "items": [
    {
      "InvoiceId": 300000095000123,
      "InvoiceNumber": "INV-2024-001",
      "SupplierNumber": "1252",
      "Supplier": "Lee Supplies",
      "InvoiceDate": "2024-08-15",
      "InvoiceAmount": 1500.00,
      "InvoiceCurrency": "USD",
      "PaidStatus": "Paid",
      "ApprovalStatus": "Not required"
    },
    ...
  ],
  "count": 5,
  "hasMore": false
}
```

**Notes on status fields:**
- `PaidStatus` values are display strings: `"Paid"`, `"Unpaid"`, etc. — **not** codes.
- `ApprovalStatus` values are display strings: `"Not required"`, `"Approved"`, etc. — **not** codes.
- If you ever build invoice-status vocabulary in the KG, mirror the existing `po_status` pattern but map to these display strings (`"unpaid"` → `"Unpaid"`).

**Date filtering — the workaround:**

Spire does NOT pass `InvoiceDate>='2025-11-19'` as a second `q=` clause. Composite `q=` is broken on this endpoint. Instead:

1. Server-side: `q=SupplierNumber='1252'` (single clause)
2. Over-fetch up to `limit=200`
3. Client-side: filter `items` where `InvoiceDate >= cutoff_date`

The `invoice_date_after` parameter on the Spire tool becomes a client-side filter, not a `q=` clause.

**Notes:**
- Join key from supplier: **`SupplierNumber`** (string), NOT `SupplierId`.
- `InvoiceDate` is ISO date (`YYYY-MM-DD`).
- Currency varies; convert with caution.

---

## 4. `/purchaseOrders` — find POs by supplier + status

**Purpose:** Find purchase orders for a supplier, optionally filtered by status. Used for "has open purchase orders" checks.

**Spire tool:** `search_purchase_orders(supplier_id, supplier_name, status)`

**Curl — open POs for supplier_id 300000047572113:**

```bash
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders?q=SupplierId%3D300000047572113&fields=POHeaderId,OrderNumber,SupplierId,Supplier,StatusCode,BuyerId,Buyer,ApprovedDate,Ordered,Total&limit=200" \
  | python -m json.tool
```

**The `q=` clause unencoded:** `SupplierId=300000047572113`

**Response shape (truncated):**

```json
{
  "items": [
    {
      "POHeaderId": 300000115234567,
      "OrderNumber": "163588",
      "SupplierId": 300000047572113,
      "Supplier": "Lee Supplies",
      "StatusCode": "OPEN",
      "BuyerId": 300000047340498,
      "Buyer": "Calvin Roth",
      "ApprovedDate": "2024-06-12",
      "Ordered": 3.00,
      "Total": 3.30
    },
    ...
  ],
  "count": 3,
  "hasMore": false
}
```

**Status filtering — same workaround as invoices:**

Composite `q=` is broken here too. Spire does:
1. Server-side: `q=SupplierId=300000047572113`
2. Over-fetch up to `limit=200`
3. Client-side: filter `items` where `StatusCode == "OPEN"`

**StatusCode values observed:**
- `OPEN` — open and active
- `CLOSED`
- `CANCELED`
- `PENDING_APPROVAL`
- (and others)

**Notes:**
- Join key from supplier: **`SupplierId`** (numeric), NOT `SupplierNumber`. **This is the asymmetry that crashed Track A.**
- `BuyerId` is what you pass to `/publicWorkers` to look up the buyer's HCM record.
- `Buyer` (display name) is sometimes present inline, sometimes not — depends on the PO. Don't rely on it.
- The amount field is `Ordered` (excluding tax). `Total` includes tax. The field name `OrderTotalAmount` does NOT exist; do not project it.

---

## 5. `/publicWorkers` (HCM) — look up buyer by PersonId

**Purpose:** Get buyer details (full name, email, username). Buyers live in HCM, not FSCM. The `BuyerId` from `/purchaseOrders` maps to `PersonId` here.

**Spire tool:** `get_buyer(buyer_id: int)`

**Curl — look up buyer with BuyerId 300000047340498:**

```bash
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/hcmRestApi/resources/11.13.18.05/publicWorkers?q=PersonId%3D300000047340498&fields=PersonId,PersonNumber,DisplayName,WorkEmail,Username&limit=1" \
  | python -m json.tool
```

**The `q=` clause unencoded:** `PersonId=300000047340498`

**Response shape:**

```json
{
  "items": [
    {
      "PersonId": 300000047340498,
      "PersonNumber": "1010",
      "DisplayName": "Roth, Calvin",
      "WorkEmail": "CALVIN.ROTH_esll-dev37@oraclepdemos.com",
      "Username": "CALVIN.ROTH"
    }
  ],
  "count": 1,
  "hasMore": false
}
```

**Notes:**
- **Cross-pillar lookup:** this is the only endpoint in this list that's on the HCM API, not FSCM. The path is `/hcmRestApi/...`, not `/fscmRestApi/...`.
- `BuyerId` from `/purchaseOrders` equals `PersonId` here. The KG should encode this explicitly.
- There is NO `/fscmRestApi/.../buyers` endpoint. Don't waste a request looking.
- `DisplayName` is "Last, First" formatted. If you need "First Last", parse it.
- Single buyer at a time. To look up many, call N times (or batch via parallel requests).

---

## End-to-end example: solving the anchor prompt

To answer the POC anchor question:

> *"Show me suppliers in US with open purchase orders, including the buyer assigned to each."*

The conceptual sequence of endpoint calls:

```
Step 1. List US suppliers
        → GET /suppliers?expand=addresses
        → Client-side filter: any address with Country='US'
        → Returns: ~25 US suppliers, each with SupplierId + SupplierNumber

For each US supplier:
  Step 2. Check open POs
          → GET /purchaseOrders?q=SupplierId=<id>
          → Client-side filter: StatusCode == 'OPEN'
          → Keep only suppliers with at least one open PO
          → Collect each open PO's BuyerId

For each unique BuyerId collected:
  Step 3. Look up buyer details
          → GET /publicWorkers?q=PersonId=<buyer_id>
          → Returns: DisplayName, WorkEmail, etc.
```

**Total requests for the anchor prompt against the demo pod:**
- 1 call to `/suppliers?expand=addresses`
- ~25 calls to `/purchaseOrders` (one per US supplier)
- ~3–5 calls to `/publicWorkers` (one per unique buyer found)

So: ~30 endpoint calls total to fully answer the prompt.

**The KG-driven POC's job is to derive this sequence deterministically from the prompt structure**, then execute it. The LLM-based Spire agent variably executes 1–59 of these calls depending on the run (which is exactly why we're trying the KG-driven approach).

> **Historical note:** an earlier version of the anchor prompt included absence reasoning ("no invoices in 6 months"). That clause is out of scope for v1 of the KG (the `no_Y_in_N_months` pattern was removed). If/when absence reasoning is added back, an invoice-check step would precede the PO step.

---

## Date arithmetic (you'll need this)

The "last N months" cutoff is computed by the client, not Fusion. Use Python's `datetime`:

```python
from datetime import date, timedelta

today = date.today()  # e.g., date(2026, 5, 19)
cutoff = today - timedelta(days=180)  # e.g., date(2025, 11, 19)
cutoff_iso = cutoff.isoformat()  # "2025-11-19"
```

Then filter dates where `<DateField> >= cutoff_iso`.

**Important:** the LLM does NOT have a reliable sense of "today" — every phase 10 run got this date wrong by months or years. In a KG-driven executor, this computation MUST happen in Python with `date.today()`, never asked of the LLM.

---

## Curl command quick reference (copy-paste for testing)

All commands assume `FUSION_BASE_URL`, `FUSION_USERNAME`, `FUSION_PASSWORD` are set.

### 1. Find suppliers with "Lee" in name
```bash
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?q=Supplier+LIKE+%27%25Lee%25%27&fields=SupplierId,SupplierNumber,Supplier,Status&limit=25"
```

### 2. List all US suppliers (with addresses expanded)
```bash
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?expand=addresses&fields=SupplierId,SupplierNumber,Supplier,Status,addresses&limit=200"
```

### 3. Get all invoices for supplier number "1252"
```bash
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/invoices?q=SupplierNumber%3D%271252%27&fields=InvoiceId,InvoiceNumber,SupplierNumber,Supplier,InvoiceDate,InvoiceAmount,InvoiceCurrency,PaidStatus,ApprovalStatus&limit=200"
```

### 4. Get all POs for supplier_id 300000047572113
```bash
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders?q=SupplierId%3D300000047572113&fields=POHeaderId,OrderNumber,SupplierId,Supplier,StatusCode,BuyerId,Buyer,ApprovedDate,Ordered,Total&limit=200"
```

### 5. Look up buyer with PersonId 300000047340498
```bash
curl -s -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/hcmRestApi/resources/11.13.18.05/publicWorkers?q=PersonId%3D300000047340498&fields=PersonId,PersonNumber,DisplayName,WorkEmail,Username&limit=1"
```

---

## Notes for the KG experiment

When you build the property graph:

1. **Vertex tables encode entity *types*** — `Supplier`, `Invoice`, `PurchaseOrder`, `Buyer`, `Address`. Five rows total (one per type). Each row records the endpoint path, the canonical ID field, and the field projection list.

2. **Edge tables encode *declarations*** — `HAS_INVOICE`, `HAS_ADDRESS`, `HAS_PURCHASE_ORDER`, `ASSIGNED_TO`. Each row records:
   - From-entity and to-entity
   - **From-join-field and to-join-field** (this is where the SupplierNumber/SupplierId asymmetry lives)
   - The Fusion API path for the join

3. **Pattern templates encode reusable query shapes** — v1 patterns are `status_filter` (e.g., "open POs") and `country_filter_via_address` (e.g., "suppliers in US"). The `no_Y_in_N_months` (absence) and `cross_pillar_lookup` patterns were dropped from v1 scope; the latter because `ASSIGNED_TO` already encodes the only cross-pillar case.

4. **Vocabulary handles term-to-canonical translation** — `"US"` → `"US"`, `"United States"` → `"US"`, `"open"` → `"OPEN"`, `"active"` → `"OPEN"`, etc.

The PGQ executor's job: take structured input (e.g., `{entity: "Supplier", filters: [country=US, has_open_po=true]}`) and produce the sequence of endpoint calls listed above.

---

## What's NOT covered here

This doc covers only the endpoints Spire's existing 5 tools use. Other Fusion endpoints exist for the same domain:
- `/suppliers/{id}/child/addresses` — addresses as separate resource (Spire uses `expand=` instead)
- `/suppliers/{id}/child/sites` — supplier site records
- `/items` — items catalog
- `/orders` — sales orders (separate from purchase orders)
- `/journals`, `/ledgers` — financials

If the KG experiment needs any of these, you'll be building net-new tool integrations.

---

**End of reference. Verify each curl against the live pod before relying on the exact field names — Fusion's response shapes can vary slightly by pod configuration.**
