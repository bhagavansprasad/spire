-- Prompt: List active suppliers
-- Captured: 2026-10-07

SELECT P.VENDOR_ID,
       P.SEGMENT1,
       HP.PARTY_NAME,
       P.ENABLED_FLAG
FROM POZ_SUPPLIERS P
JOIN HZ_PARTIES HP ON HP.PARTY_ID = P.PARTY_ID
WHERE P.ENABLED_FLAG = 'Y';

-- ASSUMPTION [status_maps_to_enabled_flag]: Supplier ACTIVE/INACTIVE maps to POZ_SUPPLIERS.ENABLED_FLAG ('Y'/'N'). Confirmed by Oracle PO Prism Q24 (2026-10-07). OQ-1.
-- ASSUMPTION [party_type_not_filtered]: POZ_SUPPLIERS.PARTY_ID is assumed to point at an organization row only; no HZ_PARTIES.PARTY_TYPE predicate is emitted. OQ-3, unverified.
