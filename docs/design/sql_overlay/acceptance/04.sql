-- Prompt: Suppliers with a site in US1 Business Unit
-- Captured: 2026-10-07

[statement 1 of 2]
SELECT P.VENDOR_ID,
       P.SEGMENT1,
       HP.PARTY_NAME,
       P.ENABLED_FLAG
FROM POZ_SUPPLIERS P
JOIN HZ_PARTIES HP ON HP.PARTY_ID = P.PARTY_ID;

-- ASSUMPTION [party_type_not_filtered]: POZ_SUPPLIERS.PARTY_ID is assumed to point at an organization row only; no HZ_PARTIES.PARTY_TYPE predicate is emitted. OQ-3, unverified.

[statement 2 of 2]
-- Step 2: search_suppliers_by_site_bu (keep parents where this returns rows)
SELECT S.VENDOR_SITE_ID,
       S.VENDOR_SITE_CODE,
       S.PRC_BU_ID
FROM POZ_SUPPLIER_SITES_ALL_M S
WHERE S.PRC_BU_ID = 300000046987012
  AND S.VENDOR_ID = :supplier_id;

-- ASSUMPTION [bu_literal_from_overlay]: Business-unit name resolves to a numeric BU_ID from kg_sql_literal. Resolution happens upstream of the emitter (Resolution A). If the pod changes, the literals are reseeded. OQ-4.
