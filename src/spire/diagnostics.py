"""Diagnostic output control for Spire.

The contract this module exists to enforce, in one line:

    stdout carries the answer.  stderr carries everything else.

Redirect or pipe stdout and you get the answer alone, with nothing to
strip out. That is what UX-05 protects and what the REST interface in
API-01 will need; every rule below follows from it.

Diagnostics travel over the standard-library ``logging`` hierarchy, one
logger per pipeline component under the ``spire.`` root. Six flags
(OBS-01) switch six loggers between DEBUG and WARNING. Since these
loggers only ever emit at DEBUG, WARNING means silence.

Two loggers are never gated. ``spire.progress`` and ``spire.summary``
sit at INFO permanently: a ~16 second run needs progress feedback, and
the counts footer is always wanted. Both are on stderr, so stdout still
carries the answer alone.

Usage from an entry script::

    import argparse
    from spire.diagnostics import (
        add_diagnostic_arguments, flags_from_args, setup_diagnostics,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    add_diagnostic_arguments(parser)
    args = parser.parse_args()

    setup_diagnostics(flags_from_args(args))

Usage from library code::

    from spire.diagnostics import get_logger

    log = get_logger("planner")
    log.debug("selected tool %s", tool_name)

This module never calls ``logging.basicConfig()`` and never touches the
root logger. See ``setup_diagnostics`` for why that matters.
"""

from __future__ import annotations

import argparse
import logging
import sys

from pydantic import BaseModel, ConfigDict


# ─────────────────────────────────────────────────────────────────────
# Logger names
# ─────────────────────────────────────────────────────────────────────

ROOT_LOGGER = "spire"

# The six OBS-01 flags and the logger each one controls.
#
# `tokens` and `timings` are cross-cutting rather than component-owned:
# any part of the pipeline emits them, so they get their own logger
# instead of being special-cased inside a component's. One mechanism,
# no exceptions.
#
# The `[llm] provider=... model=...` line from config.build_llm() rides
# on `spire.tokens`: when you switch token reporting on, which model
# produced those numbers is exactly the context you want beside them.
FLAG_TO_LOGGER: dict[str, str] = {
    "show_parser": "spire.parser",
    "show_planner": "spire.planner",
    "show_raw_output": "spire.executor",
    "show_synthesizer": "spire.synthesizer",
    "show_tokens": "spire.tokens",
    "show_timings": "spire.timings",
}

# Never gated, on at INFO for every run. Deliberately loggers rather
# than bare print() calls even though no flag touches them: it costs
# nothing now and lets API-01 silence them later by detaching a
# handler, without editing a single call site.
ALWAYS_ON_LOGGERS: tuple[str, ...] = (
    "spire.progress",
    "spire.summary",
)

# Marks the handler this module installs, so repeated setup_diagnostics()
# calls reconfigure it instead of stacking duplicates on top of it.
_HANDLER_TAG = "_spire_diagnostics_handler"


# ─────────────────────────────────────────────────────────────────────
# Flags
# ─────────────────────────────────────────────────────────────────────


class DiagnosticFlags(BaseModel):
    """The six OBS-01 verbosity flags. Every one defaults to off.

    These defaults are UX-05: an invocation that sets nothing prints the
    answer on stdout, progress and summary on stderr, and no component
    diagnostics at all.

    ``extra="forbid"`` makes an unknown key raise rather than vanish
    silently — OBS-02's third acceptance criterion. It matters most in
    branch 2, when these values start arriving from a TOML file where a
    typo is easy and invisible.
    """

    model_config = ConfigDict(extra="forbid")

    show_parser: bool = False
    show_planner: bool = False
    show_raw_output: bool = False
    show_synthesizer: bool = False
    show_tokens: bool = False
    show_timings: bool = False


# Help text, kept beside the flags rather than inline in the argparse
# loop so the two can't drift apart.
_FLAG_HELP: dict[str, str] = {
    "show_parser": "parsed intent, KG menu size, refusal detail",
    "show_planner": "selected plan, tool, arguments, filters",
    "show_raw_output": "executor output per step",
    "show_synthesizer": "response object prior to rendering",
    "show_tokens": "per-call and end-of-run token counts",
    "show_timings": "per-stage latency",
}


# ─────────────────────────────────────────────────────────────────────
# Logger setup
# ─────────────────────────────────────────────────────────────────────


def setup_diagnostics(flags: DiagnosticFlags | None = None) -> None:
    """Wire the ``spire.*`` loggers to stderr according to ``flags``.

    Safe to call more than once: the handler is reused and levels are
    reapplied, so a later call with different flags takes effect without
    duplicating output.

    Two rules this function will not break, both load-bearing:

    **It never calls ``logging.basicConfig()`` and never sets a level on
    the root logger.** ``langchain``, ``httpx``, ``oracledb`` and
    ``fastmcp`` all log at DEBUG. Flipping root to DEBUG to see the
    planner would bury the answer under third-party chatter and break
    OBS-01's requirement that enabling one flag produces output from
    that component only.

    **The formatter is bare ``%(message)s``.** ``_format_plan`` and its
    siblings return pre-aligned multi-line tables; a level-and-timestamp
    prefix would mangle every line after the first.
    """
    flags = flags or DiagnosticFlags()

    root = logging.getLogger(ROOT_LOGGER)
    root.setLevel(logging.DEBUG)

    # Diagnostics stop here. Letting them propagate would hand them to
    # whatever the host application configured on the root logger —
    # possibly stdout, which would defeat the entire module.
    root.propagate = False

    handler = _find_handler(root)
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        setattr(handler, _HANDLER_TAG, True)
        root.addHandler(handler)
    handler.setLevel(logging.DEBUG)

    # Gated components: DEBUG when their flag is on, WARNING when it is
    # off. Set explicitly rather than left to inherit — an unset child
    # would inherit the root's DEBUG and print regardless of its flag.
    for flag_name, logger_name in FLAG_TO_LOGGER.items():
        enabled = getattr(flags, flag_name)
        logging.getLogger(logger_name).setLevel(
            logging.DEBUG if enabled else logging.WARNING
        )

    for logger_name in ALWAYS_ON_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.INFO)


def _find_handler(logger: logging.Logger) -> logging.Handler | None:
    """Return the handler this module previously installed, if any."""
    for handler in logger.handlers:
        if getattr(handler, _HANDLER_TAG, False):
            return handler
    return None


def get_logger(component: str) -> logging.Logger:
    """Return the ``spire.<component>`` logger.

    Accepts either the bare component name or the fully qualified one,
    so ``get_logger("planner")`` and ``get_logger("spire.planner")``
    are the same logger.
    """
    if component.startswith(ROOT_LOGGER + "."):
        return logging.getLogger(component)
    return logging.getLogger(f"{ROOT_LOGGER}.{component}")


def answer(text: str) -> None:
    """Write the answer to stdout.

    A one-line wrapper over ``print``, worth having for two reasons:
    it names the stdout half of this module's contract explicitly, and
    it makes every legitimate stdout write greppable — so a stray
    ``print()`` reappearing in the answer path is visible rather than
    camouflaged among the intended ones.
    """
    print(text, file=sys.stdout)


# ─────────────────────────────────────────────────────────────────────
# Command-line surface
# ─────────────────────────────────────────────────────────────────────


def add_diagnostic_arguments(parser: argparse.ArgumentParser) -> None:
    """Add ``--show-*`` / ``--no-show-*`` and ``--show-all`` to a parser.

    ``BooleanOptionalAction`` gives both directions from one definition,
    which OBS-02 needs: a flag set true in configuration has to be
    switchable off for a single run.

    **Every flag defaults to ``None``, not ``False``.** This is the trap
    in the whole precedence chain. With ``default=False``, a flag the
    user never mentioned looks identical to an explicit
    ``--no-show-planner``, so the command line would silently overwrite
    the configuration file with ``False`` on every single run — and
    OBS-02's first acceptance criterion could never be satisfied,
    because a configured ``true`` would never survive to runtime.
    ``None`` keeps "not specified" distinguishable from "explicitly
    off". Nothing in branch 1 depends on that distinction; branch 2
    depends on it entirely.
    """
    group = parser.add_argument_group(
        "diagnostics",
        "All off by default. Diagnostics are written to stderr; the "
        "answer is written to stdout.",
    )

    for flag_name in DiagnosticFlags.model_fields:
        group.add_argument(
            "--" + flag_name.replace("_", "-"),
            dest=flag_name,
            action=argparse.BooleanOptionalAction,
            default=None,
            help=_FLAG_HELP[flag_name],
        )

    # The convenience switch OBS-01 permits but forbids as the only
    # control. store_true rather than BooleanOptionalAction: it only
    # ever turns things on, so "--no-show-all" would mean nothing.
    group.add_argument(
        "--show-all",
        dest="show_all",
        action="store_true",
        default=False,
        help="enable every diagnostic flag above",
    )


def flags_from_args(args: argparse.Namespace) -> DiagnosticFlags:
    """Build flags from parsed command-line arguments.

    Flags left unspecified are omitted rather than passed as ``False``,
    so the model's own defaults apply. Branch 2 substitutes the
    configuration-file and environment layers underneath this same call
    without changing its signature.

    ``--show-all`` fills in only what was not named explicitly, which
    makes ``--show-all --no-show-planner`` behave the way it reads:
    everything on, except the planner.
    """
    values: dict[str, bool] = {}

    for flag_name in DiagnosticFlags.model_fields:
        value = getattr(args, flag_name, None)
        if value is not None:
            values[flag_name] = value

    if getattr(args, "show_all", False):
        for flag_name in DiagnosticFlags.model_fields:
            values.setdefault(flag_name, True)

    return DiagnosticFlags(**values)
