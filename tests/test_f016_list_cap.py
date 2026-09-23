"""F-016 regression tests — plain-list row-cap extraction and injection.

Covers three sites:

  1. ``_extract_list_cap`` (nl_parser/parser.py) — the deterministic
     post-LLM extractor that reads "top N" / "first N" / "N biggest"
     from the raw prompt.
  2. ``Intent.list_limit`` (planner/models.py) — the field it writes.
  3. ``_apply_list_limit`` + ``_LIMIT_CAPABLE_TOOLS`` (planner) — the
     injection into the entity fetcher's tool_args.

Pre-fix, the module-level imports for the three names above fail, so
this file collects to ImportError. That is the expected V7 red shape:
the fix introduces the symbols these tests exercise.
"""

from __future__ import annotations

import pytest

from spire.nl_parser.parser import _extract_list_cap
from spire.planner.models import Intent
from spire.planner.plan_builders import _apply_list_limit
from spire.planner.registries import _LIMIT_CAPABLE_TOOLS


# ── 1. _extract_list_cap — the extractor ────────────────────────────


@pytest.mark.parametrize("prompt,expected", [
    # Leading cap word
    ("List recent credit memos, top 5", 5),
    ("show me the top 10 suppliers", 10),
    ("first 3 invoices for Lee Supplies", 3),
    ("last 7 purchase orders", 7),
    # Trailing adjective
    ("the 5 biggest invoices", 5),
    ("10 largest suppliers", 10),
    ("3 most recent credit memos", 3),
    ("20 newest purchase orders", 20),
    ("2 oldest purchase orders", 2),
])
def test_extract_list_cap_fires_on_known_shapes(prompt, expected):
    assert _extract_list_cap(prompt) == expected


@pytest.mark.parametrize("prompt", [
    "",
    "list recent credit memos",
    "show suppliers",
    "invoices for Lee Supplies",
    "active suppliers in US",
    "count of suppliers",
    "Show PO 2144 and its lines",
])
def test_extract_list_cap_returns_none_when_no_cap(prompt):
    assert _extract_list_cap(prompt) is None


@pytest.mark.parametrize("prompt", [
    "purchase orders in the last 7 months",
    "invoices from the last 12 months",
    "suppliers created in the last 30 days",
    "POs in the last year",
])
def test_extract_list_cap_ignores_time_window(prompt):
    # "last N months/years/days" is a TIME window, not a row cap. The
    # extractor must not mistake it for one.
    assert _extract_list_cap(prompt) is None


def test_extract_list_cap_rejects_out_of_range():
    # 0 has no rows; >200 is not a list cap on any prompt we serve.
    # Out-of-range N returns None rather than a bound integer.
    assert _extract_list_cap("top 0 invoices") is None
    assert _extract_list_cap("top 999999 invoices") is None


def test_extract_list_cap_ignores_amounts():
    # A bare number is not a cap unless preceded by a cap word or
    # followed by a size adjective.
    assert _extract_list_cap("invoices above 50000") is None
    assert _extract_list_cap("suppliers created before 2024") is None


# ── 2. Intent.list_limit — the field ────────────────────────────────


def test_intent_has_list_limit_defaulting_none():
    intent = Intent(target_entity="CreditMemo")
    assert intent.list_limit is None


def test_intent_accepts_list_limit():
    intent = Intent(target_entity="CreditMemo", list_limit=5)
    assert intent.list_limit == 5


# ── 3. The injection into tool_args ─────────────────────────────────


def test_limit_capable_tools_covers_the_six_list_fetchers():
    expected = {
        "search_suppliers",
        "search_invoices",
        "search_addresses",
        "search_purchase_orders",
        "list_receivables_credit_memos",
        "search_standard_receipts",
    }
    assert expected <= _LIMIT_CAPABLE_TOOLS


def test_apply_list_limit_injects_for_capable_tool():
    args: dict = {}
    _apply_list_limit("list_receivables_credit_memos", args, 5)
    assert args == {"limit": 5}


def test_apply_list_limit_skips_for_non_capable_tool():
    # A tool not in the set — e.g. a get-by-id fetcher — must not have
    # a limit injected even when the intent carries one.
    args: dict = {}
    _apply_list_limit("get_purchase_order_by_id", args, 5)
    assert args == {}


def test_apply_list_limit_no_op_when_none():
    args = {"already": "here"}
    _apply_list_limit("search_suppliers", args, None)
    assert args == {"already": "here"}


def test_apply_list_limit_preserves_existing_args():
    args = {"status": "ACTIVE"}
    _apply_list_limit("search_suppliers", args, 5)
    assert args == {"status": "ACTIVE", "limit": 5}
