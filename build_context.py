#!/usr/bin/env python3
"""
build_context.py — Bundle Spire source files into shareable context files.

Usage:
    # List available bundles
    python build_context.py --list

    # Build a single bundle
    python build_context.py handoff

    # Build several bundles
    python build_context.py core planner executor

    # Build everything
    python build_context.py --all

    # Ad-hoc: bundle a custom list of files into one output
    python build_context.py --files src/spire/planner/planner.py docs/spire_poc_log.md --name adhoc

Outputs go to ./context_out/ as Markdown files. Each file in a bundle is
rendered as:

    ## relative/path/to/file.py
    ```python
    <contents>
    ```

Bundle definitions live in `context_bundles.yaml` at the repo root. If that
file is missing, the script falls back to built-in defaults (and writes
the YAML out for you on first run, so you can edit it).
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML not installed. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Patterns excluded everywhere. fnmatch-style, matched against any path
# component AND the full relative path.
DEFAULT_EXCLUDES = [
    "traces",
    "traces/*",
    "personas.yaml",
    "*.pyc",
    "__pycache__",
    "__pycache__/*",
    "*.egg-info",
    "*.egg-info/*",
    ".git",
    ".git/*",
    "*Zone.Identifier",
    "*.svg",
    "*.pdf",
    "*.puml",
    "context_out",
    "context_out/*",
    "build_context.py",  # don't bundle ourselves
    "context_bundles.yaml",  # or our config
]

# Language hints for code fences. Extension → fence language.
FENCE_LANG = {
    ".py": "python",
    ".sh": "bash",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".sql": "sql",
    ".txt": "",
    "": "",
}

# Default bundles. Each value is a list of include patterns (fnmatch-style,
# relative to repo root). Directories expand to all files under them
# (recursive). Specific files can be listed by path.
DEFAULT_BUNDLES = {
    # The most common case: starting a fresh session. Hand off doc + the
    # README + the roadmap.
    "handoff": [
        "docs/spire_handoff_*.md",
        "README.md",
        "docs/designs/design3_v1_to_production_roadmap.md",
    ],
    # Core architecture: planner, executor, synthesizer, plus the entry
    # scripts. Use when you want Claude to reason about the pipeline.
    "core": [
        "src/spire/planner/planner.py",
        "src/spire/executor/executor.py",
        "src/spire/synthesizer/synthesizer.py",
        "scripts/run_plan.py",
        "scripts/ask.py",
    ],
    # Per-component bundles: source + tests + the most-relevant doc.
    "planner": [
        "src/spire/planner/planner.py",
        "tests/test_planner.py",
        "docs/designs/phase_2_planner_design.md",
    ],
    "executor": [
        "src/spire/executor/executor.py",
        "tests/test_executor.py",
    ],
    "synthesizer": [
        "src/spire/synthesizer/synthesizer.py",
        "tests/test_synthesizer.py",
    ],
    # MCP server + tools.
    "mcp": [
        "src/spire/mcp_server/server.py",
        "src/spire/mcp_server/tools",
        "tests/test_buyer_tool.py",
        "tests/test_suppliers_tool.py",
        "tests/test_suppliers_by_country_tool.py",
        "tests/test_purchase_orders_tool.py",
        "tests/test_invoices_tool.py",
    ],
    # KG-related.
    "kg": [
        "src/spire/kg",
        "tests/test_kg_loader.py",
        "tests/test_kg_metadata.py",
        "scripts/rebuild_kg.sh",
        "docs/designs/kg_schema_v1.md",
        "docs/designs/kg_evaluation_framework.md",
    ],
    # Demo prep: handoff + run scripts + how-to-run + measurement report.
    "demo": [
        "docs/spire_handoff_*.md",
        "scripts/run_plan.py",
        "scripts/ask.py",
        "how-to-run-02.md",
        "docs/design3_measurement_report.md",
        "docs/design3_gap_analysis.md",
    ],
    # All docs, no source.
    "docs": [
        "docs",
        "README.md",
        "how-to-run-02.md",
    ],
    # All source, no tests, no docs.
    "src": [
        "src",
        "scripts",
    ],
    # All tests.
    "tests": [
        "tests",
    ],
    # Everything (respects excludes).
    "everything": [
        ".",
    ],
}


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


@dataclass
class BundleResult:
    name: str
    output_path: Path
    file_count: int
    char_count: int

    @property
    def est_tokens(self) -> int:
        # chars / 4 is the standard rough heuristic for English-ish text.
        return self.char_count // 4


def is_excluded(rel_path: Path, excludes: list[str]) -> bool:
    """Return True if rel_path matches any exclude pattern."""
    rel_str = str(rel_path)
    for pattern in excludes:
        if fnmatch.fnmatch(rel_str, pattern):
            return True
        # Also match against any single path component, so "traces" excludes
        # everything inside it even without the trailing /*.
        for part in rel_path.parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def expand_pattern(
    repo_root: Path, pattern: str, excludes: list[str]
) -> list[Path]:
    """
    Expand a single include pattern into a list of files (relative to
    repo_root).

    - If the pattern resolves to a directory: recurse into it.
    - If it resolves to a file: return it (if not excluded).
    - Otherwise: treat as a glob.
    """
    candidate = repo_root / pattern
    results: list[Path] = []

    if candidate.is_dir():
        for path in sorted(candidate.rglob("*")):
            if path.is_file():
                rel = path.relative_to(repo_root)
                if not is_excluded(rel, excludes):
                    results.append(rel)
    elif candidate.is_file():
        rel = candidate.relative_to(repo_root)
        if not is_excluded(rel, excludes):
            results.append(rel)
    else:
        # Treat as a glob (e.g., "docs/spire_handoff_*.md").
        matched = False
        for path in sorted(repo_root.glob(pattern)):
            if path.is_file():
                rel = path.relative_to(repo_root)
                if not is_excluded(rel, excludes):
                    results.append(rel)
                    matched = True
            elif path.is_dir():
                for sub in sorted(path.rglob("*")):
                    if sub.is_file():
                        rel = sub.relative_to(repo_root)
                        if not is_excluded(rel, excludes):
                            results.append(rel)
                            matched = True
        # An explicit path (no glob chars) that matched nothing is almost
        # certainly a stale or mistyped entry — warn loudly. A real glob
        # matching nothing is normal, so stay silent for those.
        if not matched and not any(c in pattern for c in "*?["):
            print(
                f"[warn] listed path not found: {pattern}",
                file=sys.stderr,
            )

    return results


def collect_files(
    repo_root: Path, patterns: list[str], excludes: list[str]
) -> list[Path]:
    """Expand all patterns and de-duplicate while preserving order."""
    seen: set[Path] = set()
    ordered: list[Path] = []
    for pat in patterns:
        for rel in expand_pattern(repo_root, pat, excludes):
            if rel not in seen:
                seen.add(rel)
                ordered.append(rel)
    return ordered


def render_file(repo_root: Path, rel: Path) -> str:
    """Render one file as a Markdown section."""
    abs_path = repo_root / rel
    ext = abs_path.suffix.lower()
    lang = FENCE_LANG.get(ext, "")

    try:
        content = abs_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return (
            f"## {rel}\n\n"
            f"*[binary or non-UTF-8 file, skipped]*\n\n"
        )
    except OSError as e:
        return f"## {rel}\n\n*[could not read: {e}]*\n\n"

    # Use a fence long enough to survive any internal triple-backticks.
    fence = "```"
    while fence in content:
        fence += "`"

    return f"## {rel}\n\n{fence}{lang}\n{content}\n{fence}\n\n"


def build_bundle(
    repo_root: Path,
    name: str,
    patterns: list[str],
    excludes: list[str],
    out_dir: Path,
) -> BundleResult:
    files = collect_files(repo_root, patterns, excludes)

    header = (
        f"# Context bundle: `{name}`\n\n"
        f"Generated from `{repo_root}`.\n"
        f"Files included: {len(files)}.\n\n"
        f"---\n\n"
    )

    parts = [header]
    for rel in files:
        parts.append(render_file(repo_root, rel))

    body = "".join(parts)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"context_{name}.md"
    out_path.write_text(body, encoding="utf-8")

    return BundleResult(
        name=name,
        output_path=out_path,
        file_count=len(files),
        char_count=len(body),
    )


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_config(repo_root: Path) -> tuple[dict[str, list[str]], list[str]]:
    """
    Load bundles and excludes from context_bundles.yaml if it exists,
    else return defaults and write the defaults out for editing.
    """
    config_path = repo_root / "context_bundles.yaml"

    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        bundles = cfg.get("bundles", DEFAULT_BUNDLES)
        excludes = cfg.get("excludes", DEFAULT_EXCLUDES)
        return bundles, excludes

    # Write defaults out so the user can edit them.
    cfg = {"bundles": DEFAULT_BUNDLES, "excludes": DEFAULT_EXCLUDES}
    with config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)
    print(f"[info] Wrote default config to {config_path} — edit as needed.")

    return DEFAULT_BUNDLES, DEFAULT_EXCLUDES


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def format_size(chars: int) -> str:
    if chars < 1024:
        return f"{chars}B"
    if chars < 1024 * 1024:
        return f"{chars / 1024:.1f}KB"
    return f"{chars / (1024 * 1024):.1f}MB"


def print_summary(results: Iterable[BundleResult]) -> None:
    results = list(results)
    if not results:
        return

    print()
    print(f"{'Bundle':<20} {'Files':>6} {'Size':>10} {'~Tokens':>10}  Output")
    print("-" * 80)
    for r in results:
        print(
            f"{r.name:<20} {r.file_count:>6} "
            f"{format_size(r.char_count):>10} "
            f"{r.est_tokens:>10,}  {r.output_path}"
        )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bundle Spire source files into shareable context files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "bundles",
        nargs="*",
        help="Bundle names to build. Use --list to see available bundles.",
    )
    parser.add_argument(
        "--list", action="store_true", help="List available bundles and exit."
    )
    parser.add_argument(
        "--all", action="store_true", help="Build all defined bundles."
    )
    parser.add_argument(
        "--files",
        nargs="+",
        metavar="PATH",
        help="Ad-hoc mode: bundle exactly these paths (files or directories).",
    )
    parser.add_argument(
        "--name",
        default="adhoc",
        help="Name for the ad-hoc bundle (used in output filename).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (defaults to current directory).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (defaults to <repo-root>/context_out).",
    )

    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    out_dir = args.out_dir or (repo_root / "context_out")

    bundles, excludes = load_config(repo_root)

    if args.list:
        print("Available bundles:\n")
        for name, patterns in bundles.items():
            print(f"  {name}")
            for p in patterns:
                print(f"      {p}")
            print()
        return 0

    results: list[BundleResult] = []

    if args.files:
        result = build_bundle(
            repo_root, args.name, args.files, excludes, out_dir
        )
        results.append(result)

    targets = list(args.bundles)
    if args.all:
        targets = list(bundles.keys())

    unknown = [t for t in targets if t not in bundles]
    if unknown:
        print(
            f"ERROR: unknown bundle(s): {', '.join(unknown)}",
            file=sys.stderr,
        )
        print(
            f"Available: {', '.join(bundles.keys())}", file=sys.stderr
        )
        return 1

    for name in targets:
        result = build_bundle(
            repo_root, name, bundles[name], excludes, out_dir
        )
        results.append(result)

    if not results:
        parser.print_help()
        return 1

    print_summary(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
