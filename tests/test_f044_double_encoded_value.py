"""F-044 regression — a double-encoded value_json must still decode to
its native Python type.

F-044: 'invoices for supplier 1252 above 50000' intermittently crashes
at the executor with

    ERROR: execute: 1 validation error for call[search_invoices]
    amount_min
      Input should be a valid number, unable to parse string as a number
        [type=float_parsing, input_value='{"min": 50000}', input_type=str]

The tool's `amount_min` is typed as float; the planner passes the
filter's raw value through unchanged. When the model emits `value_json`
as a JSON-encoded STRING whose content is the object text — the JSON
string `"{\\"min\\": 50000}"` rather than the object text
`{"min": 50000}` itself — `draft.py::to_intent`'s single `json.loads`
yields the string `{"min": 50000}` (Python str). The planner then
passes the string to the tool, which rejects it at Pydantic input
validation, before the tool body runs.

DIAGNOSTIC EVIDENCE (2026-09-22, f044_diag_20260922_144608.txt):
8 of 9 runs PASS. Two observed failures at different thresholds
(`above 50000` once at 14:26, `above 100000` once at 14:50), both with
the stringified-object form. Same prompt, same phrasing, different
runs — the model double-encodes intermittently.

The fix: after the first decode, if the result is a STRING whose own
content starts with `{` or `[` and parses as JSON, decode again. A
dict or list is not a legitimate filter VALUE on this codebase — the
planner's `_build_entity_fetcher_args` only checks `isinstance(value,
dict)` for range-shaped filters, and no filter in the KG takes a list
— so a string that decodes to a dict is unambiguously double-encoded.

No LLM, no pod. The fix is in a pure function of the draft, and the
tests exercise that function directly.
"""
from __future__ import annotations

from spire.nl_parser.draft import DraftFilter, DraftIntent


def _intent_with(value_json: str) -> DraftIntent:
    """One filter, the given value_json, entity 'Invoice'."""
    return DraftIntent(
        target_entity="Invoice",
        filters=[DraftFilter(type="invoice_amount", value_json=value_json)],
    )


# ── The bug — a double-encoded object must still decode to a dict ────


def test_double_encoded_object_decodes_to_dict():
    """F-044's reproducer.

    `value_json` is a JSON string whose content is the object text. The
    single `json.loads` at draft.py:400 yields the string
    `{"min": 50000}`; the fix decodes the inner layer too, giving the
    dict. Without the fix this asserts `str == dict` and fails.
    """
    # Python literal for the string `"{\"min\": 50000}"`
    value_json = '"{\\"min\\": 50000}"'
    intent = _intent_with(value_json).to_intent()
    assert intent.filters[0]["value"] == {"min": 50000}, (
        f"F-044: double-encoded value_json yielded "
        f"{intent.filters[0]['value']!r}; expected the dict "
        f"{{'min': 50000}}."
    )


def test_double_encoded_max_decodes():
    """The `max` key too, not just `min` — same defect, same shape."""
    value_json = '"{\\"max\\": 20000}"'
    intent = _intent_with(value_json).to_intent()
    assert intent.filters[0]["value"] == {"max": 20000}


def test_double_encoded_range_decodes():
    """A min+max range, the fullest shape of the affected filter."""
    value_json = '"{\\"min\\": 10000, \\"max\\": 50000}"'
    intent = _intent_with(value_json).to_intent()
    assert intent.filters[0]["value"] == {"min": 10000, "max": 50000}


# ── Regressions — the fix must not change the working cases ──────────


def test_single_encoded_object_still_decodes():
    """The normal case (7 passing runs in the diagnostic): value_json is
    the object text itself, decoding once to a dict."""
    value_json = '{"min": 50000}'
    intent = _intent_with(value_json).to_intent()
    assert intent.filters[0]["value"] == {"min": 50000}


def test_single_encoded_string_still_decodes():
    """`"US"` (JSON string) decodes to `US`. The fix must not attempt a
    second decode on a plain string — the content does not start with
    `{` or `[`, so the guard skips it."""
    value_json = '"US"'
    intent = _intent_with(value_json).to_intent()
    assert intent.filters[0]["value"] == "US"


def test_plain_string_fallback_unchanged():
    """Unparseable value_json stays as the plain string (draft.py's
    documented lenient-decoding fallback). The fix must not disturb
    that branch."""
    value_json = "GB"
    intent = _intent_with(value_json).to_intent()
    assert intent.filters[0]["value"] == "GB"


def test_numeric_string_does_not_double_decode():
    """A string whose content is `50000` — the fix's guard requires the
    content to start with `{` or `[`, so this case is untouched: stays
    the string `50000`, which is what the parser contract produces for
    a string-valued filter."""
    value_json = '"50000"'
    intent = _intent_with(value_json).to_intent()
    assert intent.filters[0]["value"] == "50000"


def test_string_starting_with_brace_but_unparseable_is_left_alone():
    """A string starting with `{` that is NOT valid JSON (truncated, or
    arbitrary prose) must not crash and must stay as the string."""
    value_json = '"{\\"min\\": "'
    intent = _intent_with(value_json).to_intent()
    # Whatever it decodes to, the second decode must not raise; the
    # result is the string unchanged (the inner layer does not parse).
    assert isinstance(intent.filters[0]["value"], str)
