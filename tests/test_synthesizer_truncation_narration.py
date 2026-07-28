"""The synthesizer must NARRATE truncation, not just record it.

THE BUG THESE PIN
"List recent credit memos" produced:

    Answer:     There are 25 credit memos listed. ...
    Truncation: credit_memos: 2111 total in source; 25 examined ...

Both came from the same response object. The truncation_notes field was
correct; the summary contradicted it. A reader stops at the sentence.

The cause was instructional, not mechanical. The preamble told the model
to POPULATE truncation_notes and nothing more. Only the aggregation
shapes ("If 'truncated' is true, say plainly that the figures cover only
...") asked for it in the prose. So for every list shape the behaviour
was uninstructed and therefore inconsistent — the QA run narrated it for
one supplier list (425 available) and stayed silent on another (428)
and on 1,343 invoices.

These tests assert the INSTRUCTION exists, which is what can be checked
without an LLM. Whether the model obeys is verified end to end; the
value here is that nobody can quietly delete the instruction and leave
the suite green.
"""

import pytest

from spire.synthesizer.synthesizer import (
    _SUMMARY_FIELD,
    _SYSTEM_PROMPT_BY_ENTITY,
    _build_system_prompt,
)


# Shapes that render a LIST of records — the ones that were silent. The
# aggregation shapes already had their own "if truncated, say so" clause.
_LIST_SHAPES = ["Supplier", "Invoice", "CreditMemo"]


@pytest.mark.parametrize("entity", _LIST_SHAPES)
def test_summary_must_narrate_truncation(entity):
    """Every list shape's prompt must require the SUMMARY to state it —
    populating truncation_notes alone is what produced the contradiction."""
    prompt = _build_system_prompt(entity)
    assert "the SUMMARY must say so too" in prompt


@pytest.mark.parametrize("entity", _LIST_SHAPES)
def test_prompt_still_requires_the_notes_field(entity):
    """The new instruction ADDS to the old one. Narrating in prose must
    not replace the structured notes — the display renders those."""
    prompt = _build_system_prompt(entity)
    assert "populate truncation_notes" in prompt


@pytest.mark.parametrize("entity", _LIST_SHAPES)
def test_prompt_forbids_passing_the_row_count_off_as_the_total(entity):
    """The specific failure was a true statement read as a false one:
    'there are 25 credit memos' when 25 were shown of 2,111."""
    prompt = _build_system_prompt(entity)
    assert "Never state a count as the total" in prompt


def test_summary_field_carries_the_constraint():
    """Belt and braces: the instruction also rides on the schema field the
    model fills, not only in the system prompt."""
    description = _SUMMARY_FIELD.description
    assert "truncation_notes" in description
    assert "is NOT the number that exist" in description


def test_every_shape_inherits_the_instruction():
    """The preamble is shared, so no shape can be missed — that asymmetry
    (aggregations instructed, lists not) is what caused this."""
    for entity in _SYSTEM_PROMPT_BY_ENTITY:
        prompt = _build_system_prompt(entity)
        assert "the SUMMARY must say so too" in prompt, entity
