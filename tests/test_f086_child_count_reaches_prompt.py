"""F-086 — a capped child's total must reach the synthesizer, not stop at
the executor.

The defect's second half. PR #231 made `get_invoice_lines` report
`total_available=184` instead of 50, and the answer still said "50 line
items", because the number had nowhere to go:

    if truncation and truncation.get("truncated"):
        truncation_by_step[step.output_name] = truncation     # non-iterating
    ...
    else:
        items, metadata = await _execute_iterating_step(...)
        if metadata:
            metadata_by_step[step.output_name] = metadata     # iterating only

`_build_synthesis_prompt` renders the truncation block from
`truncation_by_step`, and its metadata branch read one hardcoded bucket name
(`account_receipt_applications`). So an iterating child's cap reached
`metadata_by_step` and was never shown to the model, which then described the
rows it could see. p13 has two buckets, so it cannot take the deterministic
invoice path either — `plain_invoice_bucket` returns None for a multi-bucket
shape.

These tests pin the three changes: an iterating capped step fills both maps,
the prompt states the total once and only once, and a step whose total the
truncation block already carries is not repeated.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from spire.executor.executor import execute_plan
from spire.planner.planner import Step
from spire.synthesizer.prompts import _build_synthesis_prompt


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _call_tool_result(payload: object) -> SimpleNamespace:
    return SimpleNamespace(content=[_text_block(json.dumps(payload))])


def _session(payloads: list[object]) -> AsyncMock:
    session = AsyncMock()
    session.call_tool.side_effect = [
        _call_tool_result(p) for p in payloads
    ]
    return session


def _envelope(items: list, total, limit, truncated) -> dict:
    return {
        "items": items,
        "total_available": total,
        "limit_applied": limit,
        "truncated": truncated,
    }


def _step(tool: str, args: dict, output: str, iterate=None) -> Step:
    return Step(
        step_id=1,
        tool_name=tool,
        tool_args=args,
        iterate_over=iterate,
        client_filters=(),
        output_name=output,
        output_dedupe_by=None,
    )


# ── the executor half ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_capped_iterating_step_fills_both_maps():
    """A capped child must reach truncation_by_step as well as metadata."""
    header = _step(
        "search_invoices", {"invoice_number": "ERS-53004-755598"}, "invoices"
    )
    lines = _step(
        "get_invoice_lines",
        {"invoice_id": "$iteration_value"},
        "invoiceline",
        iterate={"from_step": "invoices", "field": "InvoiceId"},
    )
    session = _session([
        _envelope([{"InvoiceId": 1601397}], 1, 25, False),
        _envelope([{"LineNumber": i} for i in range(50)], 184, 200, True),
    ])

    outputs, truncation_by_step, metadata_by_step = await execute_plan(
        [header, lines], session
    )

    assert len(outputs["invoiceline"]) == 50
    assert metadata_by_step["invoiceline"]["total_available"] == 184
    assert truncation_by_step["invoiceline"]["total_available"] == 184, (
        "an iterating step's truncation must reach the map the prompt is "
        "built from, or the model describes the 50 rows it can see"
    )


@pytest.mark.asyncio
async def test_uncapped_iterating_step_stays_out_of_truncation_map():
    """A complete child must not be announced as truncated."""
    header = _step("search_invoices", {"invoice_number": "X"}, "invoices")
    lines = _step(
        "get_invoice_lines",
        {"invoice_id": "$iteration_value"},
        "invoiceline",
        iterate={"from_step": "invoices", "field": "InvoiceId"},
    )
    session = _session([
        _envelope([{"InvoiceId": 1}], 1, 25, False),
        _envelope([{"LineNumber": i} for i in range(4)], 4, 200, False),
    ])

    _, truncation_by_step, _ = await execute_plan([header, lines], session)

    assert "invoiceline" not in truncation_by_step


# ── the prompt half ───────────────────────────────────────────────────


def test_prompt_states_the_total_for_a_capped_child():
    """The number the model is given must be the source total, not the page."""
    outputs = {
        "invoices": [{"InvoiceId": 1601397}],
        "invoiceline": [{"LineNumber": i} for i in range(50)],
    }
    prompt = _build_synthesis_prompt(
        outputs,
        truncation_by_step={"invoiceline": _envelope([], 184, 200, True)},
        metadata_by_step={"invoiceline": {"total_available": 184}},
    )

    assert "184" in prompt
    assert "truncated" in prompt.lower()


def test_prompt_does_not_repeat_a_total_the_truncation_block_carries():
    """One statement per split — the reason the hardcoded branch was removed."""
    outputs = {"invoiceline": [{"LineNumber": i} for i in range(50)]}
    truncation = {"invoiceline": _envelope([], 184, 200, True)}
    prompt = _build_synthesis_prompt(
        outputs,
        truncation_by_step=truncation,
        metadata_by_step={"invoiceline": {"total_available": 184}},
    )

    assert prompt.count("184") == 1, (
        "the same split stated twice is the duplication the hardcoded "
        "account_receipt_applications branch caused"
    )


def test_prompt_states_a_total_for_a_non_iterating_capped_step():
    """The case the hardcoded branch existed for must still work."""
    outputs = {"account_receipt_applications": [{"AppliedAmount": 1}]}
    prompt = _build_synthesis_prompt(
        outputs,
        metadata_by_step={
            "account_receipt_applications": {"total_available": 37}
        },
    )

    assert "37" in prompt


def test_prompt_omits_a_total_that_does_not_exceed_the_rows():
    """A total equal to the row count is not a cap and must not be flagged."""
    outputs = {"invoices": [{"InvoiceId": 1}, {"InvoiceId": 2}]}
    prompt = _build_synthesis_prompt(
        outputs,
        metadata_by_step={"invoices": {"total_available": 2}},
    )

    assert "capped page" not in prompt.lower()


def test_prompt_without_metadata_is_unchanged():
    """The block is additive; no metadata must not add prose."""
    prompt = _build_synthesis_prompt({"invoices": [{"InvoiceId": 1}]})

    assert "capped page" not in prompt.lower()
    assert "truncated" not in prompt.lower()
