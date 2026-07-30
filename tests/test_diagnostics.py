"""Tests for spire.diagnostics.

Deterministic: no LLM, no pod, no MCP server. Everything here runs in
the default (non-integration) suite.

Two notes for anyone extending this file.

**Global state.** This is the only module in the test suite that
mutates the ``logging`` hierarchy, which is process-global. The autouse
fixture below snapshots and restores the ``spire.*`` tree around every
test. Without it, a test that switches ``show_planner`` on leaks that
setting into every test that runs after it — including the other 607.

**``capsys``, not ``caplog``.** ``setup_diagnostics`` sets
``propagate = False`` on the ``spire`` logger, deliberately, so records
never reach the root logger. ``caplog`` attaches its handler at root and
therefore sees nothing. Assert on captured stderr instead. If you reach
for ``caplog`` and it comes back empty, this is why.
"""

from __future__ import annotations

import argparse
import logging

import pytest
from pydantic import ValidationError

from spire.diagnostics import (
    ALWAYS_ON_LOGGERS,
    FLAG_TO_LOGGER,
    ROOT_LOGGER,
    DiagnosticFlags,
    add_diagnostic_arguments,
    answer,
    flags_from_args,
    get_logger,
    setup_diagnostics,
)


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


def _parse(argv: list[str]) -> argparse.Namespace:
    """Build a parser with the diagnostic arguments and parse ``argv``."""
    parser = argparse.ArgumentParser()
    add_diagnostic_arguments(parser)
    return parser.parse_args(argv)


# ─────────────────────────────────────────────────────────────────────
# Defaults — this is UX-05
# ─────────────────────────────────────────────────────────────────────


def test_every_flag_defaults_to_off():
    flags = DiagnosticFlags()
    for flag_name in DiagnosticFlags.model_fields:
        assert getattr(flags, flag_name) is False, flag_name


def test_the_six_obs01_flags_are_present_and_no_others():
    """OBS-01 names six. Two more were proposed and rejected.

    Guards against a seventh being added without the decision being
    revisited — the register in the status doc records this as closed.
    """
    assert set(DiagnosticFlags.model_fields) == {
        "show_parser",
        "show_planner",
        "show_raw_output",
        "show_synthesizer",
        "show_tokens",
        "show_timings",
    }


def test_every_flag_maps_to_a_logger():
    assert set(FLAG_TO_LOGGER) == set(DiagnosticFlags.model_fields)


def test_unknown_flag_is_rejected_not_ignored():
    """OBS-02 criterion 3: invalid names reported, never swallowed."""
    with pytest.raises(ValidationError) as exc:
        DiagnosticFlags(show_planer=True)  # typo, deliberate
    assert "show_planer" in str(exc.value)


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


# ─────────────────────────────────────────────────────────────────────
# The root-logger trap
# ─────────────────────────────────────────────────────────────────────


def test_root_logger_is_never_touched():
    """langchain, httpx, oracledb and fastmcp all log at DEBUG.

    Touching the root logger to reveal one Spire component would bury
    the answer under third-party output.
    """
    root = logging.getLogger()
    before = root.level

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
    """The distinction branch 2 depends on entirely.

    An unmentioned flag must arrive as None, not False, or the command
    line would silently overwrite the configuration file on every run.
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
    """OBS-02: a configured true must be switchable off for one run."""
    args = _parse(["--no-show-planner"])
    assert args.show_planner is False
    assert flags_from_args(args).show_planner is False


def test_underscores_become_hyphens_on_the_command_line():
    flags = flags_from_args(_parse(["--show-raw-output"]))
    assert flags.show_raw_output is True


def test_show_all_enables_everything():
    flags = flags_from_args(_parse(["--show-all"]))
    for flag_name in DiagnosticFlags.model_fields:
        assert getattr(flags, flag_name) is True, flag_name


def test_show_all_respects_an_explicit_negative():
    """``--show-all --no-show-planner`` reads as "everything but the
    planner", and behaves that way."""
    flags = flags_from_args(_parse(["--show-all", "--no-show-planner"]))

    assert flags.show_planner is False
    assert flags.show_parser is True
    assert flags.show_tokens is True


def test_show_all_is_order_independent():
    left = flags_from_args(_parse(["--no-show-planner", "--show-all"]))
    right = flags_from_args(_parse(["--show-all", "--no-show-planner"]))
    assert left == right


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
