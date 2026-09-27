# 20260925_150333 smoke - action items

One entry per candidate. Walk S0-S8. S1 is the gate: no harm, no F-NNN.

---

## A-001 (for C-001, payables invoices in the last 30 days)

### 1. Reproduce outside the batch

- Command: run the single prompt against the same pod.
- Capture full log to a file. No filter at capture time.
- Check: plan emits invoice_date_after='2026-08-25' with no upper bound.
- Check: future-dated rows appear in the answer.
- Gate: if it does not reproduce, close as not-a-bug.

### 2. Walk S0-S8

- S0 observed:   answer includes future-dated rows.
- S1 harm:       user is misled. "Last 30 days" implies window ends today.
- S2 scope:      not yet measured.
- S3-S8:         not yet walked.

### 3. Scope blast radius

- Check date_filters/smoke: 6 prompts, all date-based.
- Check payables "invoices in 2024": has after and before, not affected.
- Check procurement "Purchase orders created before 2015": past-only, not
  affected.
- Determine shared mechanism: any "in the last N days/months" filter that
  compiles to a one-sided after and omits the upper bound.

### 4. Review gate

- Bring reproducer, S0-S8 walk, blast radius.
- Decide: log as F-NNN, link to existing, or close-as-not-a-bug.
- Decide priority relative to F-052.

---

## A-002 (for C-002, batch exit code depends on final prompt)

- Confirm at runtime trace level that state carrying error is per-prompt
  and reset between prompts.
- Confirm that batch exit code is taken from the final prompt's state.
- If confirmed, this is a distinct finding from F-052, adjacent to it.


---

## A-003 (for C-003, procurement_supplier suppliers with open purchase orders)

### 1. Reproduce outside the batch

- Run the single prompt against the same pod.
- Capture full log. No filter at capture time.
- Check: plan step 2 does not set `filter_source_when_nonempty`.
- Check: answer includes suppliers with Open POs = 0.

### 2. Walk S0-S8

- S0 observed:   answer lists suppliers with 0 open POs in response to
                 a prompt that asks for suppliers with open POs.
- S1 harm:       user is misled. The list is the answer; showing
                 suppliers with 0 open POs contradicts the question.
- S2 scope:      not yet measured.
- S3-S8:         not yet walked.

### 3. Scope blast radius

- Compare with payables_supplier prompt 2, which sets
  `filter_source_when_nonempty: True` and filters correctly.
- Check other "suppliers with X" prompts across the 16 sets for the
  same pattern.
- Decide: is this one plan-selection bug, or a class of plans that
  omit `filter_source_when_nonempty`?

### 4. Review gate

- Bring reproducer, S0-S8 walk, blast radius.
- Decide: log as F-NNN, link to F-010, or close-as-not-a-bug.


---

## A-004 (for C-004, columns list active suppliers with address)

### 1. Reproduce outside the batch

- Run the single prompt against the same pod.
- Capture full log. No filter at capture time.
- Check: [parse] empty draft line appears.
- Check: refusal reason is unparseable.

### 2. Walk S0-S8

- S0 observed:   unparseable refusal on a prompt that is structurally
                 the same as columns prompt 1 plus address.
- S1 harm:       user asked a reasonable list question, got a refusal.
                 Directly blocks the user from getting the answer.
- S2 scope:      not yet measured.
- S3-S8:         not yet walked.

### 3. Scope blast radius

- Compare columns prompt 1 (passed) against prompt 5 (failed).
- Compare truncation prompt 3 "Suppliers with their addresses" (passed).
- Determine what triggers the parser to produce no target_entity:
  order of fields, presence of "List", presence of "and address",
  or a combination.
- Check other prompts across the 16 sets for the same "List ... with
  fields ... and address" shape.

### 4. Review gate

- Bring reproducer, S0-S8 walk, blast radius.
- Decide: log as F-NNN, link to F-001, or close-as-not-a-bug.
