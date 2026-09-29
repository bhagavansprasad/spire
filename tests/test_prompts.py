"""Unit tests for spire.agent.prompts.

These are pure unit tests — no DB, no network. They verify that
build_system_prompt composes correctly with and without KG content.
"""

from spire.agent.prompts import SYSTEM_PROMPT_BASE, build_system_prompt


def test_build_system_prompt_without_kg():
    """When kg_context is None, only the base prompt is returned."""
    result = build_system_prompt(None)
    assert result == SYSTEM_PROMPT_BASE


def test_build_system_prompt_with_empty_string():
    """Empty string is treated the same as None — no KG section appended."""
    result = build_system_prompt("")
    assert result == SYSTEM_PROMPT_BASE


def test_build_system_prompt_with_whitespace_only():
    """Whitespace-only context is also treated as no KG."""
    result = build_system_prompt("   \n  \n  ")
    assert result == SYSTEM_PROMPT_BASE


def test_build_system_prompt_with_kg_content():
    """When kg_context has content, it's appended with a separator."""
    kg = "# KG\n\nSome KG content."
    result = build_system_prompt(kg)
    assert result.startswith(SYSTEM_PROMPT_BASE)
    assert "# KG" in result
    assert "Some KG content." in result
    # A markdown separator must appear between base and KG.
    assert "---" in result


def test_build_system_prompt_base_mentions_kg_pointer():
    """The base prompt itself must mention the KG so the LLM knows to attend
    to it when present. This is the 'lightly revised' decision documented in
    the agent/KG integration design."""
    assert "Knowledge Graph" in SYSTEM_PROMPT_BASE


def test_build_system_prompt_ends_with_newline_when_kg_present():
    """Ensure the composed prompt ends cleanly with a newline."""
    result = build_system_prompt("# KG section")
    assert result.endswith("\n")
