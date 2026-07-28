# Findings: LLM Degenerate Parse — Repetition Loop

**Date:** 2026-07-22  
**Session:** Investigation of parser runaway (AR‑P5, prompt 6)  
**Status:** Root cause identified; fix proposed.  

---

## 1. Symptom

On the prompt `"What is the account balance for customer ABC Application Software?"`, the parser consumes ~7983 output tokens (the `LLM_MAX_OUTPUT_TOKENS` cap) and returns a degenerate `ParseResult` where:

- `target_entity` is correctly set to `"CustomerAccount"`.
- `unanswerable` is `false`.
- `unanswerable_reason` contains a massive repetition of the same phrase (see raw trace).

The pipeline then refuses the query with `finish_reason=MAX_TOKENS`.

---

## 2. Raw Capture Evidence

The guard added in `parser.py` saved the raw output to `traces/degenerate_parse_20260722_225216.txt`.

**Key excerpt:**

```json
{
  "target_entity": "CustomerAccount",
  "unanswerable": false,
  "unanswerable_reason": "null_value_not_provided_in_input_schema_for_unanswerable_reason_field_but_is_nullable_in_json_schema_so_should_be_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in_output_if_not_provided_in_input_and_not_required_in_schema_for_output_but_also_not_allowed_to_be_omitted_or_be_null_in"
}
```

The model repeats a long phrase about "null_value_not_provided_in_input_schema..." to the token limit.

---

## 3. Root Cause Analysis

The parser's system prompt includes the instruction:

> "If the question needs ANY entity or filter that is not in the lists below, or is too vague to pin to a specific entity and filters, you MUST set unanswerable=true and briefly say why in unanswerable_reason."

The model seems to interpret `unanswerable_reason` as required even when `unanswerable=false`, and attempts to fill it with a repetitive justification about the field's nullability in the JSON schema. This is a classic case of the model over‑fitting to a vague instruction and generating a loop.

---

## 4. Impact

- This affects prompts that are **in‑scope** but where the model is uncertain about the exact structure (e.g., account balance questions).
- The degenerate parse leads to a refusal, preventing the user from getting a valid answer.
- The failure mode is deterministic on the affected prompts.

---

## 5. Proposed Fix

Update the parser system prompt to **explicitly** state that `unanswerable_reason` MUST be an empty string **when `unanswerable` is false**, and only provide a reason when `unanswerable` is true.

### 5.1 Change to `_SYSTEM_PROMPT_PREAMBLE` (in `src/spire/nl_parser/parser.py`)

Add a clarifying sentence near the top of the `OUT OF SCOPE` section:

> "When `unanswerable` is false, set `unanswerable_reason` to an empty string and do not include any explanatory text in it."

Also, in the `DraftIntent` model, we can add a default `""` and a field description that reinforces this.

---

## 6. Additional Guard (optional)

We could add a validation step in `parse()` to reject responses where `unanswerable_reason` exceeds a safe length (e.g., 1000 characters) and treat it as degenerate. This would catch repetition even if token count is not at the cap.

---

## 7. Next Steps

1. Apply the prompt change.
2. Verify that the degenerate prompt now parses correctly (expected: `target_entity=CustomerAccount`, `balance_only=true`, `by_customer_name` filter).
3. Remove the debug guard (or keep it as a safety net) and test the full pipeline.

---
