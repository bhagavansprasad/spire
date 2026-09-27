# Step 6 — regression cross-check

Six Phase 2 fixes with reproducers in the smoke tier:
F-001, F-007, F-008, F-010, F-012, F-015.

For each: reproducer prompt, expected behavior, observed behavior,
regression yes/no.

---

## F-001 — list_all flag on explicit PO list

- Reproducer in this tier: none direct.
- Closest analog: columns prompt 5 "List active suppliers with supplier
  name, supplier number, and address".
- Observed: refused unparseable (C-004). Different failure mode than
  F-001. Not a regression of F-001.
- Verdict: no direct reproducer in smoke. Cannot confirm or deny. Note
  C-004 as related but distinct.

---

## F-007 — empty requested child acknowledgement

- Reproducer in this tier: child_as_root (5 prompts, all child-shaped).
- Observed: all five child_as_root prompts returned children correctly
  (invoice lines, tax lines, PO lines, contacts, transactions).
- No empty-child case was triggered in this run.
- Verdict: no regression observed. Positive signal.

---

## F-008 — expired supplier classification

- Reproducer in this tier: none direct.
- Observed: no expired suppliers appeared in any set. All supplier
  statuses were ACTIVE.
- Verdict: not reproducible in this run. Cannot confirm or deny.

---

## F-010 — filtered count over the matched bucket

Two "suppliers with X" prompts, one passes, one fails.

### payables_supplier prompt 2 — "suppliers with invoice amount greater than 10000"

- Plan step 2 sets `filter_source_when_nonempty: True`.
- Answer: "Examined 25 of 695 suppliers. Of those 25, 19 match the filter."
- Count 19 is over the matched bucket, not over 695.
- Verdict: PASS. F-010 holds for this shape.

### procurement_supplier prompt 2 — "suppliers with open purchase orders"

- Plan step 2 does NOT set `filter_source_when_nonempty`.
- Answer: "Showing 25 of 695 suppliers. These 25 suppliers have 67 open
  purchase orders between them."
- Table includes 9 suppliers with Open POs = 0.
- Verdict: FAIL for this shape. Regression candidate. Logged as C-003.

### Summary

- F-010 holds when `filter_source_when_nonempty` is set.
- F-010 does not hold when it is not set.
- The two prompts use the same natural-language shape "suppliers with X"
  but produce different plans.

---

## F-012 — truncation sample sentence

- Reproducers: all list-shaped prompts with truncation.
- Observed disclosure language across the run:
  - "Showing 25 of N" (many)
  - "Showing N invoices from an examined sample; the true matching count
    is not known." (payables prompt 3, truncation prompt 1)
  - "Not totalled: these are the 25 most recent of 2248 credit memos. A
    sum over only the sampled rows would misstate the full set — ask for
    a bounded set (e.g. a date range or a single customer) and I'll total
    that." (receivables prompt 4)
- One list-shaped answer lacks disclosure: "Addresses for supplier 1252"
  in dipstick and supplier. Recorded as observation in those set files.
- Verdict: F-012 holds. Positive signal. The addresses case is
  observation-only, not a regression of F-012.

---

## F-015 — empty bucket truncation acknowledgement

- Reproducer in this tier: none direct.
- Observed: no empty-bucket case was triggered. All list prompts
  returned at least some rows.
- Verdict: not reproducible in this run. Cannot confirm or deny.

---

## Summary table

| F-NNN | reproduced | verdict |
|---|---|---|
| F-001 | no direct reproducer | cannot confirm |
| F-007 | yes (all pass) | no regression |
| F-008 | no reproducer | cannot confirm |
| F-010 | yes | PASS for payables_supplier, FAIL for procurement_supplier (C-003) |
| F-012 | yes | no regression |
| F-015 | no reproducer | cannot confirm |

## Regression candidate produced

- C-003 (procurement_supplier prompt 2) is a partial F-010 regression.
  The same shape passes in payables_supplier and fails here.
