"""Diagnostic output control for Spire.

The contract this module exists to enforce, in one line:

    stdout carries the answer.  stderr carries everything else.

Redirect or pipe stdout and you get the answer alone, with nothing to
strip out. That is what UX-05 protects and what the REST interface in
API-01 will need; every rule below follows from it.

Diagnostics travel over the standard-library ``logging`` hierarchy, one
logger per pipeline component under the ``spire.`` root. Seven flags
switch seven loggers between DEBUG and WARNING — six named by OBS-01,
plus ``show_sql`` added for the SQL Overlay POC. Since these loggers
only ever emit at DEBUG, WARNING means silence.

Two loggers are never gated. ``spire.progress`` and ``spire.summary``
sit at INFO permanently: a ~16 second run needs progress feedback, and
the counts footer is always wanted. Both are on stderr, so stdout still
carries the answer alone.

Flags can be set in three places (OBS-02). Later beats earlier::

    1. built-in defaults    every flag off — this is UX-05
    2. pyproject.toml       [tool.spire.diagnostics], committed
    3. environment          SPIRE_SHOW_PLANNER=1, your machine
    4. command line         --show-planner / --no-show-planner

So a flag switched on for the team in ``pyproject.toml`` can be turned
off for one run with ``--no-show-planner``, and an environment
preference overrides the file without dirtying git.

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

Usage from a script with no command line of its own::

    setup_diagnostics()        # still reads pyproject.toml and env

Usage from library code::

    from spire.diagnostics import get_logger

    log = get_logger("planner")
    log.debug("selected tool %s", tool_name)

This module never calls ``logging.basicConfig()`` and never touches the
root logger. See ``setup_diagnostics`` for why that matters.

Note the ``spire.agent.*`` namespace belongs to ``agent/tracing.py``,
which configures structlog per run with ``propagate = False``. Its trace
records do not reach the handler installed here, and nothing here
changes its behaviour. Do not add a component logger under that name.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


# ─────────────────────────────────────────────────────────────────────
# Logger names
# ─────────────────────────────────────────────────────────────────────

ROOT_LOGGER = "spire"

# The OBS-01 flags and the logger each one controls, plus `show_sql`.
#
# `tokens` and `timings` are cross-cutting rather than component-owned:
# any part of the pipeline emits them, so they get their own logger
# instead of being special-cased inside a component's. One mechanism,
# no exceptions.
#
# The `[llm] provider=... model=...` line from config.build_llm() rides
# on `spire.tokens`: when you switch token reporting on, which model
# produced those numbers is exactly the context you want beside them.
#
# `show_sql` is the SQL Overlay POC's projection of the Plan — one
# deterministic Fusion-DB SQL string per Plan step, print-only. It sits
# in this registry rather than as a bespoke flag so the standard
# precedence chain (file / env / CLI / --show-all) applies to it like
# every other diagnostic. See docs/design/SQL_OVERLAY_POC.md.
FLAG_TO_LOGGER: dict[str, str] = {
    "show_parser": "spire.parser",
    "show_planner": "spire.planner",
    "show_raw_output": "spire.executor",
    "show_synthesizer": "spire.synthesizer",
    "show_tokens": "spire.tokens",
    "show_timings": "spire.timings",
    "show_sql": "spire.sql",
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

# Repo root, by the same reckoning config.py uses for personas.yaml:
# src/spire/diagnostics.py -> spire -> src -> root.
PYPROJECT_FILE = Path(__file__).resolve().parents[2] / "pyproject.toml"

# Prefix every diagnostic environment variable shares. Used both by
# pydantic-settings to match them and by the typo check below to spot
# ones that match nothing.
ENV_PREFIX = "SPIRE_"


# ─────────────────────────────────────────────────────────────────────
# The pyproject.toml layer
# ─────────────────────────────────────────────────────────────────────


def read_pyproject_diagnostics(path: Path | None = None) -> dict[str, Any]:
    """Return the ``[tool.spire.diagnostics]`` table, or an empty dict.

    A missing file is not an error: the flags all default to off, so an
    absent section and an absent file mean the same thing. This matters
    beyond tidiness — ``pyproject.toml`` is not shipped when a package
    is pip-installed, so a deployed Spire simply has no file layer and
    takes its configuration from the environment instead.

    Malformed TOML *is* an error and is left to propagate. A
    ``pyproject.toml`` that will not parse is broken for the build too,
    and silently ignoring it would hide that.
    """
    path = path or PYPROJECT_FILE
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return {}
    return data.get("tool", {}).get("spire", {}).get("diagnostics", {})


class PyprojectSettingsSource(PydanticBaseSettingsSource):
    """Feed ``[tool.spire.diagnostics]`` into pydantic-settings.

    pydantic-settings ships a TOML source, but it expects the file's top
    level to *be* the settings. Ours is nested three deep under
    ``[tool.spire.diagnostics]``, so this reads the table itself and
    hands the raw dict over.

    Raw, deliberately: unknown keys are passed through rather than
    filtered, so ``extra="forbid"`` on the model rejects a typo'd key
    by name. Filtering here would make ``show_planer = true`` vanish
    silently — the exact failure OBS-02's third criterion forbids.
    """

    def __init__(
        self, settings_cls: type[BaseSettings], path: Path | None = None
    ) -> None:
        super().__init__(settings_cls)
        self._data = read_pyproject_diagnostics(path)

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return dict(self._data)


# ─────────────────────────────────────────────────────────────────────
# Flags
# ─────────────────────────────────────────────────────────────────────


class DiagnosticFlags(BaseSettings):
    """The diagnostic verbosity flags, plus the ``show_all`` convenience.

    Every one defaults to off. Those defaults are UX-05: an invocation
    that sets nothing prints the answer on stdout, progress and summary
    on stderr, and no component diagnostics at all.

    Values are collected from the command line, the environment, and
    ``pyproject.toml``, in that order of precedence — see
    ``settings_customise_sources``.

    ``extra="forbid"`` makes an unknown key raise rather than vanish
    silently, which is OBS-02's third acceptance criterion. It covers
    the file and command-line layers. The environment layer needs
    ``validate_env_flag_names`` as well; pydantic-settings ignores
    environment variables that match no field rather than complaining
    about them.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        extra="forbid",
        case_sensitive=False,
    )

    show_parser: bool = False
    show_planner: bool = False
    show_raw_output: bool = False
    show_synthesizer: bool = False
    show_tokens: bool = False
    show_timings: bool = False
    show_sql: bool = False

    # Turns every flag above on. Settable in every layer, like any other
    # flag: a switch that worked on the command line but not in the
    # file would be a surprise needing a footnote, and would need
    # special-casing in each layer to enforce.
    show_all: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Highest precedence first.

        ``init_settings`` carries the command line, because
        ``flags_from_args`` passes parsed arguments as constructor
        keywords. So the order below is exactly the OBS-02 chain:
        command line, then environment, then file, then the field
        defaults pydantic applies when no source supplies a value.
        """
        return (
            init_settings,
            env_settings,
            PyprojectSettingsSource(settings_cls),
        )


# The gated flags, without the convenience switch. Derived rather
# than written out again, so it cannot drift from FLAG_TO_LOGGER.
_GATED_FLAGS: tuple[str, ...] = tuple(FLAG_TO_LOGGER)

# Help text, kept beside the flags rather than inline in the argparse
# loop so the two can't drift apart.
_FLAG_HELP: dict[str, str] = {
    "show_parser": "parsed intent, KG menu size, refusal detail",
    "show_planner": "selected plan, tool, arguments, filters",
    "show_raw_output": "executor output per step",
    "show_synthesizer": "response object prior to rendering",
    "show_tokens": "per-call and end-of-run token counts",
    "show_timings": "per-stage latency",
    "show_sql": "deterministic Fusion-DB SQL projection of the plan",
}


class UnknownDiagnosticEnvVar(ValueError):
    """Raised for a ``SPIRE_SHOW_*`` variable that matches no flag."""


def validate_env_flag_names(environ: dict[str, str] | None = None) -> None:
    """Raise if any ``SPIRE_SHOW_*`` variable matches no flag.

    OBS-02's third acceptance criterion: invalid names are reported
    rather than ignored. ``extra="forbid"`` covers the file and the
    command line, but not this layer — pydantic-settings silently drops
    environment variables that match no field, so ``SPIRE_SHOW_PLANER=1``
    would do nothing at all and leave you wondering why.

    Only the ``SPIRE_SHOW_`` prefix is checked. ``SPIRE_LLM_PROVIDER``
    and friends are read elsewhere and are none of this module's
    business.
    """
    environ = os.environ if environ is None else environ

    known = {
        f"{ENV_PREFIX}{name}".upper() for name in DiagnosticFlags.model_fields
    }
    prefix = f"{ENV_PREFIX}SHOW_"

    unknown = sorted(
        name
        for name in environ
        if name.upper().startswith(prefix) and name.upper() not in known
    )
    if unknown:
        raise UnknownDiagnosticEnvVar(
            "unknown diagnostic environment variable(s): "
            + ", ".join(unknown)
            + ". Known: "
            + ", ".join(sorted(known))
        )


def _expand_show_all(flags: DiagnosticFlags) -> DiagnosticFlags:
    """Force every gated flag on when ``show_all`` is true.

    ``show_all`` is an OVERRIDE, not a default. If it is true, every
    gated flag becomes true regardless of any explicit value in the
    file, the environment, or the command line. An explicit
    ``show_parser = false`` alongside ``show_all = true`` is therefore
    ignored — the override wins.

    The cost of that model: ``--show-all --no-show-planner`` no longer
    means "everything except the planner"; it means "everything". Set
    ``show_all = false`` and name the flags you want if a subset is
    needed.
    """
    if not flags.show_all:
        return flags
    updates = {name: True for name in _GATED_FLAGS}
    return flags.model_copy(update=updates)


def load_flags(**overrides: bool) -> DiagnosticFlags:
    """Build flags from the full precedence chain.

    Keyword arguments are the command-line layer and win over
    everything. Pass none and you get environment over file over
    defaults, which is what a script with no flags of its own wants.
    """
    validate_env_flag_names()
    return _expand_show_all(DiagnosticFlags(**overrides))


# ─────────────────────────────────────────────────────────────────────
# Logger setup
# ─────────────────────────────────────────────────────────────────────


def setup_diagnostics(flags: DiagnosticFlags | None = None) -> DiagnosticFlags:
    """Wire the ``spire.*`` loggers to stderr according to ``flags``.

    Called with no argument, it loads flags from the environment and
    ``pyproject.toml`` itself — so a script with no command line of its
    own still honours both.

    Returns the flags actually applied, which is what a caller needs in
    order to report them.

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
    flags = load_flags() if flags is None else flags

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

    return flags


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

    A one-line wrapper over ``print``, worth having for three reasons.
    It names the stdout half of this module's contract explicitly. It
    makes every legitimate stdout write greppable, so a stray ``print()``
    reappearing in the answer path is visible rather than camouflaged
    among the intended ones. And it flushes.

    **The flush is not cosmetic.** Python block-buffers stdout when it is
    a pipe but leaves stderr unbuffered, so `run ... | tee` showed every
    diagnostic BEFORE the answer it belonged to — the counts footer for
    one prompt landing above that prompt's own output. Answers and
    diagnostics travel on different streams by design; without this they
    also arrive in the wrong order.
    """
    print(text, file=sys.stdout, flush=True)


# ─────────────────────────────────────────────────────────────────────
# Command-line surface
# ─────────────────────────────────────────────────────────────────────


def add_diagnostic_arguments(parser: argparse.ArgumentParser) -> None:
    """Add ``--show-*`` / ``--no-show-*`` and ``--show-all`` to a parser.

    ``BooleanOptionalAction`` gives both directions from one definition,
    which OBS-02 needs: a flag set true in ``pyproject.toml`` has to be
    switchable off for a single run.

    **Every flag defaults to ``None``, not ``False``.** This is the trap
    in the whole precedence chain. With ``default=False``, a flag the
    user never mentioned looks identical to an explicit
    ``--no-show-planner``, so the command line would silently overwrite
    the file and environment layers with ``False`` on every single run,
    and OBS-02's first acceptance criterion could never be satisfied.
    ``None`` keeps "not specified" distinguishable from "explicitly
    off", and ``flags_from_args`` drops the former before the value
    reaches the settings model.
    """
    group = parser.add_argument_group(
        "diagnostics",
        "All off by default. Set them here, in the environment "
        "(SPIRE_SHOW_PLANNER=1), or in pyproject.toml under "
        "[tool.spire.diagnostics]; this layer wins. Diagnostics are "
        "written to stderr; the answer is written to stdout.",
    )

    for flag_name in _GATED_FLAGS:
        group.add_argument(
            "--" + flag_name.replace("_", "-"),
            dest=flag_name,
            action=argparse.BooleanOptionalAction,
            default=None,
            help=_FLAG_HELP[flag_name],
        )

    # store_true rather than BooleanOptionalAction: it only ever turns
    # things on, so "--no-show-all" would mean nothing. default=None so
    # its absence does not override the file or environment layers.
    group.add_argument(
        "--show-all",
        dest="show_all",
        action="store_true",
        default=None,
        help="enable every diagnostic flag above",
    )


def flags_from_args(args: argparse.Namespace) -> DiagnosticFlags:
    """Build flags from parsed command-line arguments, plus every layer.

    Arguments left unspecified are dropped rather than passed as
    ``False``, so the environment and ``pyproject.toml`` layers can
    still supply them. Anything actually named on the command line wins
    over both.
    """
    overrides: dict[str, bool] = {}

    for flag_name in (*_GATED_FLAGS, "show_all"):
        value = getattr(args, flag_name, None)
        if value is not None:
            overrides[flag_name] = value

    return load_flags(**overrides)
