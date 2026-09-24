"""Corpus-consistency guard (CF-3).

The `--generate` path runs each prompt through the non-deterministic
classifier ONCE and freezes that run's module set as the corpus value.
If two runs of the same prompt pick different modules, the corpus holds
one of them and is silently wrong about the other.

This guard does not fix the non-determinism — Phase 3f's deterministic
classifier does that. It is a tripwire for the window between here and
there: structurally identical prompts must carry identical module sets
in the committed corpus.

Two layers:
  1. Byte-identical: prompts that match exactly, across any files.
  2. Case-normalized: prompts that differ only in whitespace or case.

Both must agree on module. Paraphrases are deliberately NOT checked —
"top 10 suppliers by spend" vs "top 5 suppliers by invoice spend" route
differently today and there is no defensible automatic rule for whether
that is drift or distinction.

Baseline 2026-09-18: 19 byte-identical groups, 2 case-normalized, zero
drift at both layers.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest


CORPUS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "prompts"


# The 13 .json corpora were deleted on 2026-09-24 (PR #167): their
# recorded module/tool metadata was stale by construction after the
# _TIER1 change. Until scripts/promptkit.py --generate produces a fresh
# set (separate task), there is nothing for this guard to check, and the
# two content tests below would pass vacuously on an empty entry list —
# the exact "guard looks like it ran but didn't" state this module exists
# to prevent. Skip the whole module so the reason is in the pytest output.
if not list(CORPUS_DIR.glob("*.json")):
    pytest.skip(
        "corpora deleted 2026-09-24 (PR #167); regenerate with "
        "scripts/promptkit.py --generate — nothing to check until then",
        allow_module_level=True,
    )


def _load_corpus_entries() -> list[tuple[str, str, tuple[str, ...]]]:
    entries: list[tuple[str, str, tuple[str, ...]]] = []
    for jf in sorted(CORPUS_DIR.glob("*.json")):
        data = json.loads(jf.read_text(encoding="utf-8"))
        for entry in data:
            prompt = entry.get("prompt", "")
            modules = tuple(entry.get("module") or [])
            entries.append((jf.name, prompt, modules))
    return entries


@pytest.fixture(scope="module")
def entries() -> list[tuple[str, str, tuple[str, ...]]]:
    return _load_corpus_entries()


# The directory-exists / not-empty guard that used to live here is now
# subsumed by the module-level skip above. If CORPUS_DIR moves and holds
# no .json files, the module still skips — same outcome the guard gave,
# with the reason named in the skip message rather than asserted in-test.


def test_byte_identical_prompts_agree_on_module(entries) -> None:
    """Two identical prompts in the corpus must carry the same module set.

    A --generate run that produced one value in one corpus and a different
    value in another is exactly what this catches.
    """
    groups: dict[str, list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
    for fname, prompt, modules in entries:
        groups[prompt].append((fname, modules))

    failures = []
    for prompt, members in groups.items():
        if len(members) < 2:
            continue
        module_sets = {m for _, m in members}
        if len(module_sets) > 1:
            files = ", ".join(f for f, _ in members)
            failures.append(
                f"  prompt {prompt!r}\n"
                f"    across: [{files}]\n"
                f"    module sets: {sorted(module_sets)}"
            )

    assert not failures, (
        "Byte-identical prompts disagree on module set in the corpus. "
        "A --generate run froze two different classifier outputs.\n"
        + "\n".join(failures)
    )


def test_case_normalized_prompts_agree_on_module(entries) -> None:
    """Prompts that differ only in case or surrounding whitespace must
    agree on module set. Same failure mode, narrower signature."""
    groups: dict[str, list[tuple[str, str, tuple[str, ...]]]] = defaultdict(list)
    for fname, prompt, modules in entries:
        groups[prompt.strip().lower()].append((fname, prompt, modules))

    failures = []
    for key, members in groups.items():
        distinct_strings = {p for _, p, _ in members}
        if len(distinct_strings) < 2:
            continue
        module_sets = {m for _, _, m in members}
        if len(module_sets) > 1:
            failures.append(
                f"  strings {sorted(distinct_strings)}\n"
                f"    module sets: {sorted(module_sets)}"
            )

    assert not failures, (
        "Prompts differing only in case/whitespace disagree on module "
        "set in the corpus.\n"
        + "\n".join(failures)
    )
