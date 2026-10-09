"""Bundle manifest tripwire.

Two-way check between context_bundles.yaml and the tracked source tree:

  1. Every tracked file not covered by the yaml's excludes patterns, and
     not in a small allowlist, appears in at least one bundle.
  2. Every path named by a bundle exists in the working tree.

WHY THIS EXISTS
The bundle config is a hand-maintained registry of every other file.
Every window that creates a file has to remember to update it — which
means busy windows forget. Window 28 found F-058, F-059, the SQL POC
doc, and its test all missing from the config; each had been added by a
window that did not update it. Same drift class the phase-1 audit
documents for the KG: a parallel registry of the "what exists" fact,
alongside the source tree and the import graph.

Same shape as the KG row-count tripwires in test_kg_metadata.py — a
hand-maintained registry drifts silently unless something checks it.
"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / "context_bundles.yaml"


# Files that legitimately appear in no bundle. Kept tiny on purpose — the
# check exists to catch drift, and a large allowlist defeats it.
_ALLOWLIST = {
    "LICENSE",
}
# `__init__.py` package markers are empty by convention. Allowlisted by
# pattern so a new subpackage does not require touching this file.
_ALLOWLIST_PATTERNS = ("__init__.py",)


def _is_allowed(path: str) -> bool:
    if path in _ALLOWLIST:
        return True
    name = Path(path).name
    return any(fnmatch.fnmatch(name, pat) for pat in _ALLOWLIST_PATTERNS)


def _is_excluded(path: str, excludes: list[str]) -> bool:
    """Mirror build_context.py::is_excluded so the test agrees with the tool."""
    parts = Path(path).parts
    for pat in excludes:
        if fnmatch.fnmatch(path, pat):
            return True
        for part in parts:
            if fnmatch.fnmatch(part, pat):
                return True
    return False


def _load_config() -> tuple[dict, list[str]]:
    cfg = yaml.safe_load(CONFIG.read_text())
    return cfg.get("bundles", {}), cfg.get("excludes", [])


def _bundle_paths(bundles: dict) -> set[str]:
    """Every path mentioned by any bundle, deduplicated."""
    out: set[str] = set()
    for paths in bundles.values():
        out.update(paths)
    return out


def test_every_tracked_file_is_in_a_bundle():
    """Every tracked file not excluded (or allowlisted) is in some bundle."""
    bundles, excludes = _load_config()
    in_bundles = _bundle_paths(bundles)

    # git ls-files is authoritative for "tracked" — it excludes
    # gitignored scratch (trash/, context_out/) that a filesystem walk
    # would pick up and flag wrongly.
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [ln for ln in result.stdout.splitlines() if ln]

    missing = sorted(
        p for p in tracked
        if not _is_excluded(p, excludes)
        and not _is_allowed(p)
        and p not in in_bundles
    )

    assert not missing, (
        "Tracked files not in any bundle (and not excluded):\n  "
        + "\n  ".join(missing)
        + "\n\nAdd each to context_bundles.yaml, add it to the excludes "
        "list, or allowlist it in this test if it legitimately has no bundle."
    )


def test_no_bundle_entry_is_missing_from_the_tree():
    """Every path named by a bundle exists in the working tree."""
    bundles, _ = _load_config()
    in_bundles = _bundle_paths(bundles)

    missing = sorted(p for p in in_bundles if not (REPO_ROOT / p).exists())

    assert not missing, (
        "Bundle entries not present in the working tree:\n  "
        + "\n  ".join(missing)
        + "\n\nEither the file was deleted or the bundle is stale."
    )
