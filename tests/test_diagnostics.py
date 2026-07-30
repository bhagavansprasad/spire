"""Tests for spire.diagnostics.

Deterministic: no LLM, no pod, no MCP server. Everything here runs in
the default (non-integration) suite.

Three notes for anyone extending this file.

**Global state.** This module mutates the ``logging`` hierarchy, which
is process-global. The autouse fixture below snapshots and restores the
``spire.*`` tree around every test. Without it, a test that switches
``show_planner`` on leaks that setting into every test that runs after
it — including the other 607.

**Hermetic settings.** ``DiagnosticFlags`` reads the environment and
``pyproject.toml``, so an unguarded test would pass or fail depending on
whether the developer happens to have ``SPIRE_SHOW_PLANNER`` exported.
The autouse fixture clears every ``SPIRE_SHOW_*`` variable and points
``PYPROJECT_FILE`` at a path that does not exist. Tests that want a file
layer create one and repoint it themselves.

**``capsys``, not ``caplog``.** ``setup_diagnostics`` sets
``propagate = False`` on the ``spire`` logger, deliberately, so records
never reach the root logger. ``caplog`` attaches its handler at root and
therefore sees nothing. Assert on captured stderr instead. If you reach
for ``caplog`` and it comes back empty, this is why.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

import spire.diagnostics as diagnostics
from spire.diagnostics import (
    ALWAYS_ON_LOGGERS,
    FLAG_TO_LOGGER,
    ROOT_LOGGER,
    DiagnosticFlags,
    UnknownDiagnosticEnvVar,
    add_diagnostic_arguments,
    answer,
    flags_from_args,
    get_logger,
    load_flags,
    read_pyproject_diagnostics,
    setup_diagnostics,
    validate_env_flag_names,
)


# The six gated flags. `show_all` is a real field but drives no logger
# of its own, so most assertions are about these six rather than about
# `model_fields`.
GATED = set(FLAG_TO_LOGGER)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_logging():
    """Restore the ``spire.*`` logger tree after every test.

    Also removes handlers, which matters for more than tidiness: a
    handler created in an earlier test holds a reference to that test's
    ``capsys``-patched stderr. Reusing it in a later test would write
    output into a stream nobody is reading, and the assertion would fail
    for a reason that has nothing to do with the code under test.
    """
    names = [ROOT_LOGGER, *FLAG_TO_LOGGER.values(), *ALWAYS_ON_LOGGERS]
    saved = {
        name: (
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
            list(logging.getLogger(name).handlers),
        )
        for name in names
    }

    yield

    for name, (level, propagate, handlers) in saved.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = propagate
        logger.handlers = handlers


@pytest.fixture(autouse=True)
def _hermetic_settings(monkeypatch, tmp_path):
    """Cut every test off from the real environment and real file.

    Without this the suite reads the developer's shell and the repo's
    own ``pyproject.toml``, so a passing run would prove nothing about
    the code and everything about the machine it ran on.
    """
    for name in list(diagnostics.os.environ):
        if name.upper().startswith("SPIRE_SHOW"):
            monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr(
        diagnostics, "PYPROJECT_FILE", tmp_path / "absent-pyproject.toml"
    )


def _parse(argv: list[str]) -> argparse.Namespace:
    """Build a parser with the diagnostic arguments and parse ``argv``."""
    parser = argparse.ArgumentParser()
    add_diagnostic_arguments(parser)
    return parser.parse_args(argv)


def _write_pyproject(monkeypatch, tmp_path: Path, body: str) -> Path:
    """Point PYPROJECT_FILE at a temporary file with ``body`` in it."""
    path = tmp_path / "pyproject.toml"
    path.write_text(body)
    monkeypatch.setattr(diagnostics, "PYPROJECT_FILE", path)
    return path


DIAGNOSTICS_SECTION = "[tool.spire.diagnostics]\n"


# ─────────────────────────────────────────────────────────────────────
# Defaults — this is UX-05
# ─────────────────────────────────────────────────────────────────────


def test_every_flag_defaults_to_off():
    flags = DiagnosticFlags()
    for flag_name in DiagnosticFlags.model_fields:
        assert getattr(flags, flag_name) is False, flag_name


def test_the_six_obs01_flags_are_present_plus_show_all():
    """OBS-01 names six. Two more were proposed and rejected — progress
    and summary are always required, so neither is gated.

    ``show_all`` is the convenience switch OBS-01 permits. Guards
    against a seventh *gated* flag appearing without the decision in the
    status doc's register being revisited.
    """
    assert GATED == {
        "show_parser",
        "show_planner",
        "show_raw_output",
        "show_synthesizer",
        "show_tokens",
        "show_timings",
    }
    assert set(DiagnosticFlags.model_fields) == GATED | {"show_all"}


def test_every_gated_flag_maps_to_a_logger():
    assert GATED == set(DiagnosticFlags.model_fields) - {"show_all"}


def test_unknown_flag_is_rejected_not_ignored():
    """OBS-02 criterion 3: invalid names reported, never swallowed."""
    with pytest.raises(ValidationError) as exc:
        DiagnosticFlags(show_planer=True)  # typo, deliberate
    assert "show_planer" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────
# OBS-02 — the precedence chain
#
# defaults  <  pyproject.toml  <  environment  <  command line
# ─────────────────────────────────────────────────────────────────────


def test_file_layer_reaches_the_flags(monkeypatch, tmp_path):
    _write_pyproject(
        monkeypatch, tmp_path, DIAGNOSTICS_SECTION + "show_planner = true\n"
    )
    assert load_flags().show_planner is True


def test_env_beats_file(monkeypatch, tmp_path):
    _write_pyproject(
        monkeypatch, tmp_path, DIAGNOSTICS_SECTION + "show_planner = true\n"
    )
    monkeypatch.setenv("SPIRE_SHOW_PLANNER", "0")

    assert load_flags().show_planner is False


def test_cli_beats_env(monkeypatch):
    monkeypatch.setenv("SPIRE_SHOW_PLANNER", "1")
    assert flags_from_args(_parse(["--no-show-planner"])).show_planner is False


def test_cli_beats_file(monkeypatch, tmp_path):
    """OBS-02 criterion 1, stated almost verbatim: a flag set true in
    configuration can be disabled for a single run."""
    _write_pyproject(
        monkeypatch, tmp_path, DIAGNOSTICS_SECTION + "show_planner = true\n"
    )
    assert flags_from_args(_parse(["--no-show-planner"])).show_planner is False


def test_absent_cli_does_not_clobber_env(monkeypatch):
    """The subtlest thing in the whole chain.

    Every ``--show-*`` argument defaults to ``None`` rather than
    ``False`` precisely so that not mentioning a flag is distinguishable
    from switching it off. With ``default=False`` this test would fail
    and no configured value could ever survive to runtime.
    """
    monkeypatch.setenv("SPIRE_SHOW_PLANNER", "1")
    assert flags_from_args(_parse([])).show_planner is True


def test_absent_cli_does_not_clobber_file(monkeypatch, tmp_path):
    _write_pyproject(
        monkeypatch, tmp_path, DIAGNOSTICS_SECTION + "show_tokens = true\n"
    )
    assert flags_from_args(_parse([])).show_tokens is True


def test_an_unrelated_cli_flag_does_not_clobber_the_file(monkeypatch, tmp_path):
    """Naming one flag must not silently reset the others."""
    _write_pyproject(
        monkeypatch, tmp_path, DIAGNOSTICS_SECTION + "show_tokens = true\n"
    )
    flags = flags_from_args(_parse(["--show-parser"]))

    assert flags.show_parser is True
    assert flags.show_tokens is True


def test_all_three_layers_at_once(monkeypatch, tmp_path):
    """One flag from each layer, plus one the file sets and the command
    line overrides."""
    _write_pyproject(
        monkeypatch,
        tmp_path,
        DIAGNOSTICS_SECTION + "show_tokens = true\nshow_planner = true\n",
    )
    monkeypatch.setenv("SPIRE_SHOW_PARSER", "1")

    flags = flags_from_args(_parse(["--no-show-planner"]))

    assert flags.show_tokens is True       # from the file
    assert flags.show_parser is True       # from the environment
    assert flags.show_planner is False     # file overridden on the CLI
    assert flags.show_synthesizer is False  # nobody set it


# ─────────────────────────────────────────────────────────────────────
# OBS-02 — the file layer itself
# ─────────────────────────────────────────────────────────────────────


def test_missing_pyproject_is_not_an_error():
    """A deployed Spire has no pyproject.toml; it is not shipped when a
    package is pip-installed. Absent file means absent layer."""
    assert read_pyproject_diagnostics() == {}
    assert load_flags().show_planner is False


def test_absent_section_means_all_off(monkeypatch, tmp_path):
    """OBS-02 criterion 2."""
    _write_pyproject(monkeypatch, tmp_path, '[project]\nname = "spire"\n')

    assert read_pyproject_diagnostics() == {}
    for flag_name in GATED:
        assert getattr(load_flags(), flag_name) is False, flag_name


def test_section_is_read_from_the_nested_table(monkeypatch, tmp_path):
    """pydantic-settings' own TOML source expects the file's top level to
    be the settings. Ours is three deep, which is why the source is
    hand-written."""
    _write_pyproject(
        monkeypatch,
        tmp_path,
        '[project]\nname = "spire"\n\n'
        "[tool.pytest.ini_options]\nasyncio_mode = \"auto\"\n\n"
        + DIAGNOSTICS_SECTION
        + "show_synthesizer = true\n",
    )
    assert read_pyproject_diagnostics() == {"show_synthesizer": True}


def test_unknown_toml_key_is_reported(monkeypatch, tmp_path):
    """OBS-02 criterion 3, file layer.

    The settings source hands the raw table over without filtering, so
    ``extra="forbid"`` rejects the key by name. Filtering unknown keys
    inside the source would make this vanish silently.
    """
    _write_pyproject(
        monkeypatch, tmp_path, DIAGNOSTICS_SECTION + "show_planer = true\n"
    )
    with pytest.raises(ValidationError) as exc:
        load_flags()
    assert "show_planer" in str(exc.value)


def test_malformed_toml_is_not_swallowed(monkeypatch, tmp_path):
    """A pyproject.toml that will not parse is broken for the build too.
    Ignoring it here would hide that."""
    _write_pyproject(monkeypatch, tmp_path, "[tool.spire.diagnostics\n")
    with pytest.raises(Exception):
        read_pyproject_diagnostics()


# ─────────────────────────────────────────────────────────────────────
# OBS-02 — the environment layer
# ─────────────────────────────────────────────────────────────────────


def test_unknown_env_var_is_reported(monkeypatch):
    """OBS-02 criterion 3, environment layer.

    pydantic-settings silently ignores environment variables matching no
    field, so without this scan ``SPIRE_SHOW_PLANER=1`` would do nothing
    at all and leave the user wondering why.
    """
    monkeypatch.setenv("SPIRE_SHOW_PLANER", "1")
    with pytest.raises(UnknownDiagnosticEnvVar) as exc:
        load_flags()
    assert "SPIRE_SHOW_PLANER" in str(exc.value)


def test_the_error_lists_the_valid_names(monkeypatch):
    """A rejection that does not say what was expected is a worse
    experience than the silence it replaced."""
    monkeypatch.setenv("SPIRE_SHOW_PLANER", "1")
    with pytest.raises(UnknownDiagnosticEnvVar) as exc:
        load_flags()
    assert "SPIRE_SHOW_PLANNER" in str(exc.value)


def test_env_scan_ignores_other_spire_variables(monkeypatch):
    """Only the SPIRE_SHOW_ prefix belongs to this module.

    SPIRE_LLM_PROVIDER and SPIRE_LLM_MODEL are read in config.py and
    SPIRE_GRAPH_PNG in pipeline.py. Rejecting them here would break
    three unrelated features.
    """
    monkeypatch.setenv("SPIRE_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("SPIRE_LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("SPIRE_GRAPH_PNG", "1")

    validate_env_flag_names()  # must not raise


def test_env_scan_accepts_every_real_flag(monkeypatch):
    for flag_name in DiagnosticFlags.model_fields:
        monkeypatch.setenv(f"SPIRE_{flag_name.upper()}", "0")
    validate_env_flag_names()  # must not raise


def test_env_value_is_parsed_as_a_boolean(monkeypatch):
    monkeypatch.setenv("SPIRE_SHOW_TOKENS", "true")
    assert load_flags().show_tokens is True


# ─────────────────────────────────────────────────────────────────────
# show_all, across every layer
# ─────────────────────────────────────────────────────────────────────


def test_show_all_from_the_command_line():
    flags = flags_from_args(_parse(["--show-all"]))
    for flag_name in GATED:
        assert getattr(flags, flag_name) is True, flag_name


def test_show_all_from_the_environment(monkeypatch):
    monkeypatch.setenv("SPIRE_SHOW_ALL", "1")
    flags = load_flags()
    for flag_name in GATED:
        assert getattr(flags, flag_name) is True, flag_name


def test_show_all_from_the_file(monkeypatch, tmp_path):
    _write_pyproject(
        monkeypatch, tmp_path, DIAGNOSTICS_SECTION + "show_all = true\n"
    )
    flags = load_flags()
    for flag_name in GATED:
        assert getattr(flags, flag_name) is True, flag_name

def test_show_all_in_the_file_does_nothing_when_every_key_is_spelled_out(
    monkeypatch, tmp_path
):
    """A key written in the file counts as explicitly set.

    That is what makes ``--show-all --no-show-planner`` mean "everything
    except the planner" — so a file listing every key leaves show_all
    with nothing to fill in. Correct, but surprising enough that the
    committed pyproject.toml template was rewritten to comment its keys
    out rather than set them all to false.

    Pinned because the behaviour is deliberate and someone reading
    _expand_show_all in isolation would be tempted to "fix" it.
    """
    _write_pyproject(
        monkeypatch,
        tmp_path,
        DIAGNOSTICS_SECTION
        + "show_parser = false\n"
        + "show_planner = false\n"
        + "show_tokens = true\n"
        + "show_all = true\n",
    )
    flags = load_flags()

    assert flags.show_tokens is True
    assert flags.show_parser is False
    assert flags.show_planner is False


def test_show_all_fills_only_the_keys_the_file_omits(monkeypatch, tmp_path):
    _write_pyproject(
        monkeypatch,
        tmp_path,
        DIAGNOSTICS_SECTION + "show_planner = false\nshow_all = true\n",
    )
    flags = load_flags()

    assert flags.show_planner is False
    assert flags.show_parser is True
    assert flags.show_tokens is True

def test_show_all_respects_an_explicit_negative():
    """``--show-all --no-show-planner`` reads as "everything but the
    planner", and behaves that way."""
    flags = flags_from_args(_parse(["--show-all", "--no-show-planner"]))

    assert flags.show_planner is False
    assert flags.show_parser is True
    assert flags.show_tokens is True


def test_show_all_in_the_file_is_overridable_on_the_command_line(
    monkeypatch, tmp_path
):
    _write_pyproject(
        monkeypatch, tmp_path, DIAGNOSTICS_SECTION + "show_all = true\n"
    )
    flags = flags_from_args(_parse(["--no-show-raw-output"]))

    assert flags.show_raw_output is False
    assert flags.show_parser is True


def test_show_all_is_order_independent():
    left = flags_from_args(_parse(["--no-show-planner", "--show-all"]))
    right = flags_from_args(_parse(["--show-all", "--no-show-planner"]))
    assert left == right


# ─────────────────────────────────────────────────────────────────────
# Logger levels
# ─────────────────────────────────────────────────────────────────────


def test_gated_loggers_are_silent_by_default():
    setup_diagnostics(DiagnosticFlags())
    for logger_name in FLAG_TO_LOGGER.values():
        assert logging.getLogger(logger_name).level == logging.WARNING


def test_enabling_a_flag_opens_only_its_own_logger():
    """OBS-01: one flag produces output from that component only."""
    setup_diagnostics(DiagnosticFlags(show_planner=True))

    assert logging.getLogger("spire.planner").level == logging.DEBUG
    for flag_name, logger_name in FLAG_TO_LOGGER.items():
        if flag_name == "show_planner":
            continue
        assert logging.getLogger(logger_name).level == logging.WARNING


@pytest.mark.parametrize("flag_name", sorted(FLAG_TO_LOGGER))
def test_each_flag_independently_opens_its_logger(flag_name):
    setup_diagnostics(DiagnosticFlags(**{flag_name: True}))
    assert logging.getLogger(FLAG_TO_LOGGER[flag_name]).level == logging.DEBUG


def test_always_on_loggers_are_at_info_by_default():
    setup_diagnostics(DiagnosticFlags())
    for logger_name in ALWAYS_ON_LOGGERS:
        assert logging.getLogger(logger_name).level == logging.INFO


def test_always_on_loggers_are_unaffected_by_every_flag():
    all_on = DiagnosticFlags(**{f: True for f in DiagnosticFlags.model_fields})
    setup_diagnostics(all_on)
    for logger_name in ALWAYS_ON_LOGGERS:
        assert logging.getLogger(logger_name).level == logging.INFO


def test_setup_with_no_argument_is_all_off():
    setup_diagnostics()
    for logger_name in FLAG_TO_LOGGER.values():
        assert logging.getLogger(logger_name).level == logging.WARNING


def test_setup_with_no_argument_still_reads_the_environment(monkeypatch):
    """run_prompt_set.py calls setup_diagnostics() with no arguments. It
    should still honour a configured preference."""
    monkeypatch.setenv("SPIRE_SHOW_PLANNER", "1")
    setup_diagnostics()
    assert logging.getLogger("spire.planner").level == logging.DEBUG


def test_setup_with_no_argument_still_reads_the_file(monkeypatch, tmp_path):
    _write_pyproject(
        monkeypatch, tmp_path, DIAGNOSTICS_SECTION + "show_tokens = true\n"
    )
    setup_diagnostics()
    assert logging.getLogger("spire.tokens").level == logging.DEBUG


def test_setup_returns_the_flags_it_applied(monkeypatch):
    monkeypatch.setenv("SPIRE_SHOW_PARSER", "1")
    flags = setup_diagnostics()
    assert flags.show_parser is True


# ─────────────────────────────────────────────────────────────────────
# The root-logger trap
# ─────────────────────────────────────────────────────────────────────


def test_root_logger_is_never_touched():
    """langchain, httpx, oracledb and fastmcp all log at DEBUG.

    Touching the root logger to reveal one Spire component would bury
    the answer under third-party output.
    """
    before = logging.getLogger().level

    setup_diagnostics(DiagnosticFlags(show_planner=True, show_tokens=True))

    assert logging.getLogger().level == before


def test_third_party_loggers_are_left_alone():
    """Assert we do not *change* them, not that they are unset.

    An earlier version of this test asserted NOTSET, and passed when
    this file ran alone but failed in a combined run: ``fastmcp``
    configures its own logger to INFO when imported, so whichever test
    file imported it first decided the value this test saw. The level a
    third-party library chooses for itself is its own business —
    snapshot and compare, and the assertion holds however the suite is
    ordered.
    """
    names = ("httpx", "langchain", "oracledb", "fastmcp")
    before = {name: logging.getLogger(name).level for name in names}

    setup_diagnostics(
        DiagnosticFlags(**{f: True for f in DiagnosticFlags.model_fields})
    )

    after = {name: logging.getLogger(name).level for name in names}
    assert after == before


def test_agent_trace_namespace_is_not_reused():
    """`agent/tracing.py` owns `spire.agent.*` and configures structlog
    there per run. A component logger under that name would collide."""
    for logger_name in (*FLAG_TO_LOGGER.values(), *ALWAYS_ON_LOGGERS):
        assert not logger_name.startswith("spire.agent")


def test_spire_logger_does_not_propagate():
    setup_diagnostics()
    assert logging.getLogger(ROOT_LOGGER).propagate is False


# ─────────────────────────────────────────────────────────────────────
# Handler behaviour
# ─────────────────────────────────────────────────────────────────────


def test_repeated_setup_does_not_stack_handlers():
    setup_diagnostics(DiagnosticFlags())
    setup_diagnostics(DiagnosticFlags(show_planner=True))
    setup_diagnostics(DiagnosticFlags(show_tokens=True))

    assert len(logging.getLogger(ROOT_LOGGER).handlers) == 1


def test_later_setup_overrides_the_earlier_one():
    setup_diagnostics(DiagnosticFlags(show_planner=True))
    setup_diagnostics(DiagnosticFlags(show_planner=False))

    assert logging.getLogger("spire.planner").level == logging.WARNING


def test_diagnostics_go_to_stderr_not_stdout(capsys):
    setup_diagnostics(DiagnosticFlags(show_planner=True))
    get_logger("planner").debug("plan detail")

    captured = capsys.readouterr()
    assert "plan detail" in captured.err
    assert captured.out == ""


def test_a_disabled_component_emits_nothing_at_all(capsys):
    setup_diagnostics(DiagnosticFlags(show_planner=False))
    get_logger("planner").debug("plan detail")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_multiline_blocks_pass_through_unmangled(capsys):
    """The formatter is bare ``%(message)s`` for this reason.

    ``_format_plan`` and its siblings return pre-aligned tables. A
    level-and-timestamp prefix would corrupt every line after the first.
    """
    block = "Plan:\n  step 1  search_suppliers\n  step 2  get_addresses"

    setup_diagnostics(DiagnosticFlags(show_planner=True))
    get_logger("planner").debug(block)

    assert capsys.readouterr().err == block + "\n"


def test_always_on_logger_emits_without_any_flag(capsys):
    setup_diagnostics(DiagnosticFlags())
    logging.getLogger("spire.progress").info("… progress 3/10")

    captured = capsys.readouterr()
    assert "progress 3/10" in captured.err
    assert captured.out == ""


# ─────────────────────────────────────────────────────────────────────
# get_logger / answer
# ─────────────────────────────────────────────────────────────────────


def test_get_logger_accepts_bare_and_qualified_names():
    assert get_logger("planner") is get_logger("spire.planner")


def test_get_logger_returns_a_child_of_the_spire_root():
    assert get_logger("planner").name == "spire.planner"


def test_answer_writes_to_stdout(capsys):
    answer("Supplier ABC has 3 open purchase orders.")

    captured = capsys.readouterr()
    assert captured.out == "Supplier ABC has 3 open purchase orders.\n"
    assert captured.err == ""


# ─────────────────────────────────────────────────────────────────────
# Command-line surface
# ─────────────────────────────────────────────────────────────────────


def test_no_arguments_leaves_every_flag_unspecified():
    """The distinction the precedence chain depends on entirely.

    An unmentioned flag must arrive as None, not False, or the command
    line would silently overwrite the file and environment layers on
    every run.
    """
    args = _parse([])
    for flag_name in DiagnosticFlags.model_fields:
        assert getattr(args, flag_name) is None, flag_name


def test_no_arguments_yields_all_flags_off():
    assert flags_from_args(_parse([])) == DiagnosticFlags()


def test_positive_flag_is_parsed():
    flags = flags_from_args(_parse(["--show-planner"]))
    assert flags.show_planner is True
    assert flags.show_parser is False


def test_negative_flag_is_parsed():
    args = _parse(["--no-show-planner"])
    assert args.show_planner is False
    assert flags_from_args(args).show_planner is False


def test_underscores_become_hyphens_on_the_command_line():
    flags = flags_from_args(_parse(["--show-raw-output"]))
    assert flags.show_raw_output is True


def test_several_flags_combine():
    flags = flags_from_args(_parse(["--show-parser", "--show-tokens"]))

    assert flags.show_parser is True
    assert flags.show_tokens is True
    assert flags.show_planner is False


def test_flags_from_args_tolerates_a_namespace_without_show_all():
    """Entry scripts that add flags by hand, or tests that fake a
    namespace, should not have to know about the convenience flag."""
    namespace = argparse.Namespace(show_planner=True)
    assert flags_from_args(namespace).show_planner is True


def test_command_line_drives_the_loggers_end_to_end(capsys):
    setup_diagnostics(flags_from_args(_parse(["--show-synthesizer"])))

    get_logger("synthesizer").debug("shape = POLifecycle")
    get_logger("planner").debug("should not appear")

    captured = capsys.readouterr()
    assert "shape = POLifecycle" in captured.err
    assert "should not appear" not in captured.err
    assert captured.out == ""
