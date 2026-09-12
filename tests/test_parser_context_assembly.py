"""Standing invariant for parser context modularization (Phase 1).

The parser system prompt was split from one string literal
(``_SYSTEM_PROMPT_PREAMBLE`` in ``spire.nl_parser.parser``) into 48
``.sysprompt`` block files under ``nl_parser/context/``, grouped by Fusion
module, assembled at import via ``context/order.manifest``.

Phase 1's contract is *pure relocation*: the assembled preamble must be
byte-for-byte identical to the retained literal. The literal stays in
``parser.py`` solely as the oracle these tests check against; production sends
the assembled ``_ASSEMBLED_PREAMBLE``. If any ``.sysprompt`` file, or the
manifest, drifts from the literal, these tests fail.

See docs/features/parser_context_modularization.md §4.1.
"""

from __future__ import annotations

from pathlib import Path

from spire.nl_parser import context_assembly as assembly_mod
from spire.nl_parser.context_assembly import (
    _ASSEMBLED_PREAMBLE,
    _SYSTEM_PROMPT_PREAMBLE,
)

# Resolve the context dir the same way the module does, independently of any
# module-level constant, so this test exercises the files on disk directly.
_CONTEXT_DIR = Path(assembly_mod.__file__).resolve().parent / "context"
_MANIFEST = _CONTEXT_DIR / "order.manifest"

# The carve is fixed at 48 blocks for Phase 1 (design §4). A change to this
# number is a deliberate re-carve and must update this expectation too.
_EXPECTED_BLOCK_COUNT = 49

# Subdirectories of context/ that hold .sysprompt files which are NOT carve
# blocks and are deliberately absent from order.manifest. Phase 2's router adds
# context/routing/classifier_menu.sysprompt — generated grounding for the
# module classifier, assembled by the router, never joined into the parser
# preamble. The carve invariants below (no orphans, exactly 48 blocks) are
# about carve blocks only, so they exclude these subtrees. A NEW non-carve
# subtree must be added here consciously — that is the point.
_NON_CARVE_SUBTREES = ("routing",)


def _carve_blocks_on_disk() -> list[Path]:
    """All .sysprompt files that are carve blocks (i.e. outside the non-carve
    subtrees). These are the files order.manifest is expected to list."""
    return [
        p
        for p in _CONTEXT_DIR.rglob("*.sysprompt")
        if p.relative_to(_CONTEXT_DIR).parts[0] not in _NON_CARVE_SUBTREES
    ]


def _manifest_entries() -> list[str]:
    """The ordered, non-blank block paths listed in the manifest."""
    return [
        line.strip()
        for line in _MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _assemble_from_disk() -> str:
    """Re-read and join the blocks straight from disk, in manifest order.

    Deliberately does NOT use context_assembly._ASSEMBLED_PREAMBLE — this proves the
    files on disk assemble to the oracle, not merely that the module's cached
    import-time value does.
    """
    parts: list[str] = []
    for rel in _manifest_entries():
        parts.append((_CONTEXT_DIR / rel).read_text(encoding="utf-8"))
    return "".join(parts)


def test_module_constant_matches_literal_oracle() -> None:
    """The preamble production sends equals the retained literal, byte for byte."""
    assert _ASSEMBLED_PREAMBLE == _SYSTEM_PROMPT_PREAMBLE


def test_disk_assembly_matches_literal_oracle() -> None:
    """The .sysprompt files on disk, joined in manifest order, equal the oracle.

    Independent of the module's cached constant — guards against a stale import
    masking a drifted file.
    """
    assert _assemble_from_disk() == _SYSTEM_PROMPT_PREAMBLE


def test_manifest_entries_all_exist() -> None:
    """Every path listed in the manifest resolves to a real file."""
    missing = [
        rel for rel in _manifest_entries()
        if not (_CONTEXT_DIR / rel).is_file()
    ]
    assert not missing, f"manifest lists missing files: {missing}"


def test_no_orphan_sysprompt_files() -> None:
    """Every .sysprompt file on disk is listed in the manifest (no orphans)."""
    on_disk = {
        str(p.relative_to(_CONTEXT_DIR)).replace("\\", "/")
        for p in _carve_blocks_on_disk()
    }
    listed = set(_manifest_entries())
    orphans = on_disk - listed
    dangling = listed - on_disk
    assert not orphans, f".sysprompt files not in manifest: {sorted(orphans)}"
    assert not dangling, f"manifest entries with no file: {sorted(dangling)}"


def test_block_count_is_expected() -> None:
    """The carve is exactly the approved number of blocks."""
    entries = _manifest_entries()
    on_disk = _carve_blocks_on_disk()
    assert len(entries) == _EXPECTED_BLOCK_COUNT
    assert len(on_disk) == _EXPECTED_BLOCK_COUNT
