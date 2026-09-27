# payables/smoke

6 prompts, 1 refusal, 5 truncations, exit 1.

## Classification

| prompt | class | note |
|---|---|---|
| invoices for supplier 1252 | pass | 25 of 1327, honest disclosure |
| invoices for Lee Supplies | pass | 25 of 1327, honest disclosure |
| invoices over 100000 for supplier 1252 | pass | F-012 language present |
| invoices in 2024 | pass | F-012 language present |
| invoices in the last 30 days | wrong-but-no-error | see C-001 |
| invoices | pass | correct refusal, missing_identifier |

## F-052 signature

- One Reason line at 402.
- No ERROR banner.
- File ends after the refusal.
- Matches F-052 at signature level.

## Candidate

- C-001: invoices in the last 30 days returns future-dated rows.
