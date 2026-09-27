# receivables/smoke

6 prompts, 1 refusal, 1 truncation, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| Get the AR invoice with CustomerTransactionId 300000248096352 | pass | Transaction 61765 |
| Show the AR invoice with CustomerTransactionId 300000248096352 and its lines | pass | Line 1 Consultation 39969 GBP |
| Show me AR invoices for customer ABC Corporation Americas | pass | AccountNumber 26370, 25 of 486 |
| List recent credit memos | pass | strongest disclosure in the run |
| Show me the account balance for customer ABC Application Software | pass | AccountNumber 26360 |
| show invoice lines for invoice | pass | correct refusal, missing_identifier |

## Strong positive — prompt 4 disclosure

"List recent credit memos" closes with:

  Not totalled: these are the 25 most recent of 2248 credit memos. A sum
  over only the sampled rows would misstate the full set — ask for a
  bounded set (e.g. a date range or a single customer) and I'll total that.

The cleanest truncation disclosure in the run. It explicitly refuses to
total over the sample, explains why, and offers a bounded alternative.
Positive signal for F-012 and F-015.

## Resolved observation (not a candidate)

Same customer ABC Corporation Americas, same AccountNumber 26370, three
prompts across three sets:

- modes prompt 2      25 of 276
- dipstick prompt 5   25 of 486
- receivables prompt 3 25 of 486

Not a bug. modes prompt 2 Intent carries open_only: True. The other two
do not. 276 open vs 486 total. Consistent.

## Candidates

None.
