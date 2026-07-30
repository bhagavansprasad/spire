"""Synthesizer error types.

Moved out of synthesizer.py first, deliberately: this module depends on
nothing and is imported by most of the package, so it is the smallest
possible test of the re-export pattern. If `from spire.synthesizer.errors
import ...` works here and every existing import of these names from
spire.synthesizer.synthesizer keeps working, the pattern holds for the
larger moves that follow.

All three are loud by design. The synthesizer's job is to make a bad
answer impossible to mistake for a good one, so nothing here is caught
and softened on the way out.
"""

from __future__ import annotations


class HallucinationError(RuntimeError):
    """The LLM produced structured output containing IDs that don't
    appear in the executor's source data. The message names the
    offending IDs so the gap is actionable."""


class UnsupportedEntityError(RuntimeError):
    """The Intent's target_entity has no synthesizer schema. Loud by
    design — graceful user-facing messaging is feature 8's job."""


class DegenerateOutputError(RuntimeError):
    """The LLM produced degenerate output (runaway tokens, empty child
    arrays despite source data, etc.). Raw text is saved to traces/."""
