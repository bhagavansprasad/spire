# modes/smoke

4 prompts, 0 refusals, 0 truncations, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| count of suppliers | pass | answer 695, correct total not sample |
| open invoices for ABC Corporation Americas | pass | AccountNumber 26370 resolved, 25 of 276 |
| top 5 open invoices for ABC Corporation Americas | pass | limit 5 applied, 5 of 276 |
| Show me the account balance for customer ABC Application Software | pass | AccountNumber 26360 resolved |

## Positive observation

count of suppliers returns "There are 695 suppliers." while the summary
shows Records returned: 25. That is the F-010 shape working correctly:
the count is over the full set, not over the sample. Log for Step 6 as
a positive signal, not a candidate.

## Candidates

None.
