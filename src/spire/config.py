"""Persona configuration loader.

Reads personas.yaml from the repo root and returns the requested persona
as a validated Pydantic model.

A persona groups together all credentials a single environment needs.
For Spire that currently means:
- Fusion REST API credentials (required)
- Oracle Database credentials (optional during transition; required
  once Dynamic Orchestration phases 03+ start needing the KG)

Usage:
    from spire.config import load_persona
    persona = load_persona("default_dev")
    print(persona.fusion.base_url)
    if persona.oracle:
        print(persona.oracle.dsn)
"""

from pathlib import Path

import yaml
from pydantic import BaseModel

from spire.diagnostics import get_logger


PERSONAS_FILE = Path(__file__).resolve().parents[2] / "personas.yaml"


# LLM provider and per-call token counts both ride on `spire.tokens`,
# gated by --show-tokens. They belong together: when you switch token
# reporting on, which model produced those numbers is exactly the
# context you want beside them. Silent unless the flag is set.
_log = get_logger("tokens")


# ─────────────────────────────────────────────────────────────────────
# LLM configuration (single source of truth)
#
# The model name and temperature used by the Design 3 LLM components
# (the nl_parser interpreter and the synthesizer). Centralized here so
# there is exactly one place to change the model. Both components import
# GEMINI_MODEL / GEMINI_TEMPERATURE from this module.
# ─────────────────────────────────────────────────────────────────────

GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_TEMPERATURE = 0.0

# Cap output tokens on every provider. Structured-output parses and
# synthesizer responses are small (a DraftIntent is ~300 tokens); without
# a cap, a model that fails to converge can generate to its default
# ceiling (65520 on gemini-flash), turning a bad parse into a ~4-minute
# hang. Capping converts that into a ~2s fast failure the parser handles
# as a refusal. Raise only if a legitimate response is ever truncated.
LLM_MAX_OUTPUT_TOKENS = 8000

# Provider seam. Today only "gemini" is wired; the factory is structured
# so Claude/OpenAI become two more branches plus their deps, without
# touching the parser, synthesizer, or graph. Override via env:
#   SPIRE_LLM_PROVIDER = gemini | anthropic | openai
#   SPIRE_LLM_MODEL    = optional model-name override
import os as _os

LLM_PROVIDER = _os.environ.get("SPIRE_LLM_PROVIDER", "gemini")
LLM_MODEL = _os.environ.get("SPIRE_LLM_MODEL", "")

# Default model per provider (overridable via SPIRE_LLM_MODEL).
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-5"

# ─────────────────────────────────────────────────────────────────────
# MCP server URL (single source of truth)
#
# The port number lives in ONE place: SPIRE-PORTS.env. The shell
# functions spired() (dev) / spirep() (production) source that file and
# export SPIRE_MCP_URL; that is the intended path and it is checked
# first.
#
# When the env var is unset — a fresh clone without the shell functions
# installed — this module reads SPIRE-PORTS.env directly and assembles
# the URL from the same source the shell would have used. The port
# number is still in ONE place; no constant, no duplicate.
#
# SPIRE_MCP_MODE picks which set of ports to use: 'dev' (default, the
# 4001 set) or 'production' (the 5000 set). The shell functions imply
# the mode; this fallback needs it named explicitly. Any other value
# raises — a typo should not silently pick the wrong port set.
#
# The other two Python locations that once held a hardcoded 3333
# (rendering/formatters.py, agent/runner.py) now call this function.
# ─────────────────────────────────────────────────────────────────────

_PORTS_FILE = Path(__file__).resolve().parents[2] / "SPIRE-PORTS.env"


def _read_ports_file() -> dict[str, str]:
    """Parse SPIRE-PORTS.env into a KEY -> value dict.

    Empty dict if the file is absent or unreadable. Comments (#) and
    blank lines are skipped; a line without '=' is ignored. Values may
    be quoted; quotes are stripped.

    Same file the shell functions source. Reading it here is not a
    duplicate — it is the same source, read a second way.
    """
    if not _PORTS_FILE.is_file():
        return {}
    try:
        raw = _PORTS_FILE.read_text(encoding="utf-8")
    except OSError:
        return {}
    ports: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        ports[key.strip()] = value.strip().strip('"').strip("'")
    return ports


def _mcp_mode() -> str:
    """The mode the file-read fallback should use.

    'dev' by default; SPIRE_MCP_MODE overrides. Accepts 'dev' or
    'production'; any other value raises — a typo should not silently
    pick the wrong port set.
    """
    mode = _os.environ.get("SPIRE_MCP_MODE", "dev").strip().lower()
    if mode not in ("dev", "production"):
        raise RuntimeError(
            f"SPIRE_MCP_MODE must be 'dev' or 'production'; got {mode!r}."
        )
    return mode


def mcp_server_url() -> str:
    """Return the MCP server URL.

    Three paths, one source of truth:

    1. ``SPIRE_MCP_URL`` env var, set by the shell functions after
       sourcing SPIRE-PORTS.env. The intended path; checked first.
    2. ``SPIRE-PORTS.env`` read directly from the repo root, for a
       fresh clone without the shell functions installed. The mode
       comes from ``SPIRE_MCP_MODE`` (default 'dev').
    3. Neither present — raise, naming both paths.

    A function rather than an import-time constant so that importing
    this module (e.g. during pytest collection) does not require the
    env var or the file to be present — only calling the function does.
    """
    url = _os.environ.get("SPIRE_MCP_URL")
    if url:
        return url

    ports = _read_ports_file()
    if ports:
        mode = _mcp_mode()
        key = f"SPIRE_{mode.upper()}_MCP_PORT"
        port = ports.get(key)
        if port:
            # Trailing slash matches what the shell functions export.
            return f"http://127.0.0.1:{port}/mcp/"
        raise RuntimeError(
            f"SPIRE-PORTS.env is present at {_PORTS_FILE} but has no "
            f"{key}. Add the key, or export SPIRE_MCP_URL directly."
        )

    raise RuntimeError(
        "SPIRE_MCP_URL is not set and SPIRE-PORTS.env was not found at "
        f"{_PORTS_FILE}. Run 'spired' (dev) or 'spirep' (production) to "
        "source the ports file, or copy SPIRE-PORTS.env into the repo "
        "root."
    )

def build_llm(temperature: float = GEMINI_TEMPERATURE):
    """Return a LangChain chat model for the configured provider.

    All branches return an object exposing the same
    ``with_structured_output(...).invoke(...)`` surface, so callers
    (parser, synthesizer, graph nodes) are provider-agnostic.

    Gemini, Anthropic (Claude), and OpenAI are all implemented.
    """
    provider = LLM_PROVIDER.lower()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = LLM_MODEL or GEMINI_MODEL
        _log.debug("[llm] provider=gemini model=%s", model)
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            max_output_tokens=LLM_MAX_OUTPUT_TOKENS,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        model = LLM_MODEL or ANTHROPIC_MODEL
        _log.debug("[llm] provider=anthropic model=%s", model)
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=LLM_MAX_OUTPUT_TOKENS,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model = LLM_MODEL or OPENAI_MODEL
        _log.debug("[llm] provider=openai model=%s", model)
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=LLM_MAX_OUTPUT_TOKENS,
        )

    raise ValueError(
        f"Unknown SPIRE_LLM_PROVIDER={LLM_PROVIDER!r}. "
        "Supported: gemini, anthropic, openai."
    )


def log_usage(raw_message, stage: str) -> None:
    """Record token usage for one LLM call, and log it.

    ``raw_message`` is the LangChain ``AIMessage`` returned under the
    ``"raw"`` key when a structured LLM is built with
    ``with_structured_output(..., include_raw=True)``. Its
    ``usage_metadata`` is normalized by LangChain across the gemini,
    anthropic, and openai providers, so the same field works for all.

    Two jobs, and they are deliberately independent. **Recording** into
    ``_USAGE_LOG`` happens unconditionally — ``usage_report()`` must be
    complete at the end of a run whether or not anyone was watching the
    per-call lines. **Logging** goes to ``spire.tokens`` and is silent
    unless ``--show-tokens`` is set.

    Before Phase 1 these were one statement, so the only way to get the
    running total was to accept a line of stderr per LLM call. Keep them
    separate: a future caller may want the numbers without the noise.

    Safe to call with None or an object lacking usage_metadata: it just
    records and logs zeros.
    """
    um = getattr(raw_message, "usage_metadata", None) or {}
    inp = um.get("input_tokens", 0)
    out = um.get("output_tokens", 0)
    _USAGE_LOG.append({"stage": stage, "in": inp, "out": out})
    _log.debug(
        "[llm] stage=%s in=%s out=%s total=%s", stage, inp, out, inp + out
    )


# Per-run token accumulator. The entry script clears it with
# reset_usage() at the start of a run and logs usage_report() at the end.
_USAGE_LOG: list[dict] = []


def reset_usage() -> None:
    """Clear accumulated token usage. Call at the start of a run."""
    _USAGE_LOG.clear()


def usage_report() -> str:
    """Return a small end-of-run token report from accumulated usage.

    Pure: returns the text, prints nothing. The caller decides where it
    goes — which is why this function needed no change in Phase 1, and
    is the pattern the rest of the codebase is moving toward.
    """
    if not _USAGE_LOG:
        return "Token usage:\n  (no LLM calls recorded)"
    lines = ["Token usage:"]
    tot_in = tot_out = 0
    for e in _USAGE_LOG:
        tot_in += e["in"]
        tot_out += e["out"]
        lines.append(
            f"  {e['stage']:<12} in={e['in']:>7}  out={e['out']:>7}  "
            f"total={e['in'] + e['out']:>7}"
        )
    lines.append(
        f"  {'TOTAL':<12} in={tot_in:>7}  out={tot_out:>7}  "
        f"total={tot_in + tot_out:>7}"
    )
    return "\n".join(lines)


class FusionCredentials(BaseModel):
    base_url: str
    username: str
    password: str
    auth_type: str


class OracleCredentials(BaseModel):
    dsn: str
    username: str
    password: str


class Persona(BaseModel):
    fusion: FusionCredentials
    oracle: OracleCredentials | None = None


def load_persona(name: str) -> Persona:
    """Load a persona by name from personas.yaml.

    Raises:
        FileNotFoundError: if personas.yaml is missing.
        KeyError: if the persona name is not in the file.
        pydantic.ValidationError: if the persona entry is malformed.
    """
    with open(PERSONAS_FILE) as f:
        data = yaml.safe_load(f)

    if name not in data:
        raise KeyError(f"Persona '{name}' not found in {PERSONAS_FILE}")

    persona = Persona(**data[name])

    # Container override. Compose sets SPIRE_ORACLE_DSN so the same
    # personas.yaml works on the host (localhost) and inside a container
    # (host.docker.internal). SPIRE_ORACLE_USER / SPIRE_ORACLE_PASSWORD
    # are optional and exist for secret-injection setups that don't want
    # credentials on disk. Unset env vars fall back to the file.
    if persona.oracle is not None:
        dsn  = _os.environ.get("SPIRE_ORACLE_DSN")
        user = _os.environ.get("SPIRE_ORACLE_USER")
        pwd  = _os.environ.get("SPIRE_ORACLE_PASSWORD")
        if dsn or user or pwd:
            persona.oracle = OracleCredentials(
                dsn=dsn or persona.oracle.dsn,
                username=user or persona.oracle.username,
                password=pwd or persona.oracle.password,
            )

    return persona
