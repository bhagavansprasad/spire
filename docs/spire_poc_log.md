# Spire POC — Working Log

A single rolling log of POC progress. One section per phase. Curl commands, sample outputs (trimmed), and status live inline. Updated as work progresses.

---

## Environment

- **Pod:** `https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`
- **Pod type:** Oracle Fusion demo pod (multi-pillar: FSCM + HCM)
- **API version path:** `/fscmRestApi/resources/11.13.18.05/`
- **Auth:** Basic Auth
- **Env vars used:** `FUSION_BASE_URL`, `FUSION_USERNAME`, `FUSION_PASSWORD`
- **Credential storage:** Shell environment variables (see Phase 1 deviation note)

---

## Phase 1 — Environment & Access Setup  ✅ DONE

**Verified:** 2026-05-15

### What was confirmed

- Pod reachable, FSCM REST API enabled
- Service account authenticates (Basic Auth)
- `GET /suppliers` returns valid JSON
- Call is repeatable (limit=1 and limit=5 both return 200)

### Working command

```bash
curl -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?limit=5" \
  -w "\nHTTP %{http_code}\n"
```

### Sample response (trimmed)

```json
{
  "items": [
    {
      "SupplierId": 300000047414503,
      "Supplier": "Lee Supplies",
      "SupplierNumber": "1252",
      "Status": "ACTIVE",
      "BusinessRelationship": "Spend Authorized",
      "TaxpayerCountryCode": "US",
      "CreationDate": "2013-11-07T20:14:36.428+00:00"
    }
  ],
  "count": 1,
  "hasMore": true,
  "limit": 1,
  "offset": 0
}
```

Full response also includes child resource links: `addresses`, `sites`, `contacts`, `businessClassifications`, `DFF` (custom fields), etc. The `addresses` child is relevant for Phase 4 (`search_suppliers_by_country`).

### Exit criteria

| Criterion | Status |
|---|---|
| Service account authenticates | ✅ |
| Manual GET returns valid JSON with supplier records | ✅ |
| Credentials documented securely | ⚠️ See deviation below |
| Call is reliably repeatable | ✅ |

### Deviation from plan

Master plan Phase 1 requires credentials stored in a password manager. Currently held in shell environment variables only. Owner accepts this risk; to be revisited if/when secret hygiene becomes a Spire-level concern.

---

## Phase 2 — Single Endpoint Wrapped as a Tool  ⏳ PENDING

Not started.
