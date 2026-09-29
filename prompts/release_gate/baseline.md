# Release gate - wall-clock and pass/fail baseline

**Run:** 2026-09-29T13:18:36+05:30 to 13:24:54+05:30
**Pod:** fa-euth-dev49 (persona default_dev)
**Capture:** trash/t_litmus_10.txt (local, gitignored)
**Invocation:** python scripts/promptkit.py --run --prompt "<p>" --show-planner
**Total:** 6m18s

| # | Prompt | Module / depth | Wall | Class |
|---|---|---|---|---|
| 1 | Count of suppliers | supplier / count | 17s | pass |
| 2 | Show PO 2144 and its lines | procurement / by_id + child | 16s | pass |
| 3 | Which suppliers have open purchase orders? | procurement_supplier / cross-module | 178s | pass (watchlist) |
| 4 | Top 5 suppliers by spend this year | payables_supplier / aggregate | 58s | pass |
| 5 | Show me invoices for supplier 1252 | payables / supplier-number filter | 24s | pass |
| 6 | invoices for supplier 1252 over 10000 | payables / composite over-fetch | 15s | pass |
| 7 | Suppliers with their addresses | supplier / expand=addresses | 14s | pass |
| 8 | Get the AR invoice with CustomerTransactionId 300000248096352 | receivables / by_id header | 18s | pass |
| 9 | Show me AR invoices for customer ABC Corporation Americas | receivables / CustomerAccount traversal | 23s | pass |
| 10 | show me contract renewals due next quarter | refusals | 15s | pass (refusal) |

## Notes

**Prompt 1 - 6575 vs 6576.** Window 27 closed F-059 as not-a-bug on N=20
clean runs, all returning 6575. This run returns 6576. Prompts 1, 3, and 7
all report 6576 as the source total in the same session, consistent with a
stable pod at a new value rather than renewed nondeterminism. Not confirmed
at N=20; the F-059 re-open clause governs.

**Prompt 3 - watchlist.** The answer reports "Examined 25 of 6,576
suppliers. Of those 25, 17 match the filter." The count is scoped to the
sample, not stated as a total. The truncation block confirms: "suppliers:
6576 total in source; 25 returned." Honest narration, but 17 is a lower
bound. This is one of the delivery message's quick-try prompts.

## Re-baselining

After any release that changes a prompt's wall-clock by more than 2x, or
after any pod re-provisioning, re-run and update this file. Keep the prior
table under a dated heading - do not overwrite.
