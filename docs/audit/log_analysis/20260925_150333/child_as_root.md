# child_as_root/smoke

5 prompts, 0 refusals, 0 truncations, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| show invoice lines for invoice 300000248096352 | pass | Transaction 61765, 1 line rendered |
| show tax lines for invoice 1002 | pass | 4 lines, 8 tax lines, per-line tax tables |
| show PO lines for PO 2144 | pass | 2 lines rendered |
| show contacts for supplier EIP Inc | pass | 10 contacts rendered |
| show transactions for customer ABC Application Software | pass | 25 of 484, AccountNumber 26360 resolved |

## Note

This set is the F-007 territory: "show <child> for <root>". All five
prompts render the child correctly with no empty-acknowledgement issue
observed. Positive signal for F-007 regression check in Step 6.

## Candidates

None.
