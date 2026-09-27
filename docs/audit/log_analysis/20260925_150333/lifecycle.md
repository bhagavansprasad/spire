# lifecycle/smoke

5 prompts, 0 refusals, 0 truncations, exit 0.

## Classification

| prompt | class | note |
|---|---|---|
| Has PO 701337 been fully received, fully invoiced, and fully paid? | pass | Received no, Invoiced no, Paid cannot be determined |
| Why is PO 701337 still open? | pass | Stage Awaiting receipt, reasons given |
| Give me an end-to-end summary of PO 701337 from supplier setup through payment. | pass | Full template rendered |
| What is the risk rating on PO 701337 and why? | pass | Risk Medium with 4 reasons |
| What is the supplier status, approval status, receipt status, invoice matching status and payment status of PO 701337? | pass | See observations |

## Observations (not candidates)

1. All five prompts return the same 80-line po_lifecycle_status body,
   regardless of the question. Prompt-specificity is missing in this
   shape, but nothing is stated falsely. Observation only.
2. Prompt 5 asks for "approval status" among five statuses. Approval
   status is not present as a distinct line. Supplier status, receipt,
   invoice matching, and payment are covered. Nothing false. Observation
   only.

## Candidates

None.
