"""Unit tests for promptkit's validate decision logic.

--validate's pass/fail is decided by the TOOL alone; a module mismatch on a
tool-correct row is a WARNING, not a failure (the module set only scopes the
parser's grounding and is discarded after the parse, so the selected tool is
what determines the answer). These tests pin that rule via the pure
``_classify_mark`` helper — no LLM, no KG, no execution.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

# promptkit.py lives in scripts/ (not an installed package) — load it by path.
_PK_PATH = Path(__file__).resolve().parents[1] / "scripts" / "promptkit.py"
_spec = importlib.util.spec_from_file_location("promptkit", _PK_PATH)
promptkit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(promptkit)
_classify_mark = promptkit._classify_mark


def test_tool_ok_module_ok_is_clean_pass():
    mark, is_pass, is_warn = _classify_mark(m_ok=True, t_ok=True)
    assert mark == "OK"
    assert is_pass is True
    assert is_warn is False


def test_tool_ok_module_mismatch_passes_with_warning():
    """The rule this change exists for: correct tool + wrong module set is a
    PASS carrying a warning — NOT a failure. Guards against a future revert
    that would make a module mismatch fail the run again."""
    mark, is_pass, is_warn = _classify_mark(m_ok=False, t_ok=True)
    assert mark == "OK*"
    assert is_pass is True      # counts as a pass; does NOT fail the run
    assert is_warn is True      # but is surfaced as a warning


def test_tool_wrong_is_failure_even_if_module_ok():
    """A wrong tool fails regardless of module correctness."""
    mark, is_pass, is_warn = _classify_mark(m_ok=True, t_ok=False)
    assert mark.startswith("TOOL")
    assert is_pass is False
    assert is_warn is False


def test_tool_wrong_and_module_wrong_is_failure():
    mark, is_pass, is_warn = _classify_mark(m_ok=False, t_ok=False)
    assert mark.startswith("TOOL")
    assert is_pass is False
    assert is_warn is False
