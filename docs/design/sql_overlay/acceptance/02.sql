-- Prompt: Active suppliers in US
-- Captured: 2026-10-07

SELECT P.VENDOR_ID,
       P.SEGMENT1,
       HP.PARTY_NAME,
       P.ENABLED_FLAG
FROM POZ_SUPPLIERS P
JOIN HZ_PARTIES HP ON HP.PARTY_ID = P.PARTY_ID
LEFT JOIN HZ_PARTY_SITES PS ON PS.PARTY_ID = P.PARTY_ID
LEFT JOIN HZ_LOCATIONS L ON L.LOCATION_ID = PS.LOCATION_ID
WHERE P.ENABLED_FLAG = 'Y'
  AND L.COUNTRY = 'US';

-- ASSUMPTION [status_maps_to_enabled_flag]: Supplier ACTIVE/INACTIVE maps to POZ_SUPPLIERS.ENABLED_FLAG ('Y'/'N'). Confirmed by Oracle PO Prism Q24 (2026-10-07). OQ-1.
-- ASSUMPTION [address_join_for_country]: Supplier country lives on the child address, not the supplier row. The join is POZ_SUPPLIERS.PARTY_ID -> HZ_PARTY_SITES.PARTY_ID -> HZ_LOCATIONS.LOCATION_ID. OQ-3 covers PARTY_TYPE, not this.
-- ASSUMPTION [party_type_not_filtered]: POZ_SUPPLIERS.PARTY_ID is assumed to point at an organization row only; no HZ_PARTIES.PARTY_TYPE predicate is emitted. OQ-3, unverified.
