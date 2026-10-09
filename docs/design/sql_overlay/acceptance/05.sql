-- Prompt: Count of suppliers
-- Captured: 2026-10-07

SELECT P.VENDOR_ID,
       P.SEGMENT1,
       HP.PARTY_NAME,
       P.ENABLED_FLAG
FROM POZ_SUPPLIERS P
JOIN HZ_PARTIES HP ON HP.PARTY_ID = P.PARTY_ID;

-- ASSUMPTION [party_type_not_filtered]: POZ_SUPPLIERS.PARTY_ID is assumed to point at an organization row only; no HZ_PARTIES.PARTY_TYPE predicate is emitted. OQ-3, unverified.
