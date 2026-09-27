# truncation/smoke

4 prompts, 1 refusal, 3 truncations, exit 1.

## Classification

| prompt | class | note |
|---|---|---|
| invoices for supplier 1252 over 10000 | pass | F-012 language present |
| invoices for supplier 1252 | pass | 25 of 1327, honest disclosure |
| Suppliers with their addresses | pass | 25 of 695, honest disclosure |
| invoices | pass | correct refusal, missing_identifier |

## F-052 signature

- One Reason line at 254.
- No ERROR banner.
- File ends after the refusal.
- Matches F-052 at signature level.

## Notes

- F-012 language ("the true matching count is not known") is present in
  prompt 1. Useful for the Step 6 regression cross-check.
- F-015 relevant: prompt 3 uses the same disclosure shape.
