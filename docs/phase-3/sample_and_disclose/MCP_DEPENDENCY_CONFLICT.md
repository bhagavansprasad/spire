# MCP dependency conflict — separate from the sample-and-disclose feature

**Status:** finding only. No fix in this window. No `requirements.txt`
change, no `src/` change, no `test_agent_runner.py` change.

**Not part of PR #1.** The seven sample-and-disclose PRs are feature
work. This file records a cross-cutting environment finding
discovered during PR #1's V-walk so the next window does not
rediscover it. It should become a dedicated PR on its own branch when
scheduled.

---

## The finding

`pytest -q` on `master` at `a78c00b` reports one collection error:

    ERROR collecting tests/test_agent_runner.py
    ImportError while importing test module ...
    from langchain_mcp_adapters.tools import load_mcp_tools
    from mcp.server.fastmcp.tools import Tool as FastMCPTool
    ModuleNotFoundError: No module named 'mcp.server.fastmcp'.
    This is mcp 2.x, where FastMCP was renamed to MCPServer ...

Confirmed present on `master` and on the branch — **not introduced by
PR #1**. `pytest -q --continue-on-collection-errors` on `master`
produces `66 failed, 1240 passed, 1 skipped, 21 deselected, 1 error`.
The 66 failures are pre-existing pod-reachability and unrelated drift.

## The triangle

Three packages that the environment declares, and only two of which
can coexist:

| Package | Installed | Requires |
|---|---|---|
| `fastmcp` | 4.1.4 | `mcp 2.x` |
| `mcp` | 2.3.0 | (the SDK) |
| `langchain-mcp-adapters` | 0.3.1 | `mcp<2` (imports `mcp.server.fastmcp`, removed in mcp 2.x) |

`fastmcp 4` and `langchain-mcp-adapters` **cannot share one Python
environment**. This is upstream (PrefectHQ FastMCP #PR-...; cortex
project commit "adapters 0.2 needs langchain-core 1.x … and mcp 2.0
dropped `mcp.shared.context.RequestContext` which adapters 0.2
imports").

## What `spire` actually uses

`grep -rn 'from fastmcp\|import fastmcp' src/ --include='*.py'`:

    src/spire/mcp_server/server.py:31:  from fastmcp import Context, FastMCP
    src/spire/api/server.py:114:         from fastmcp import Client
    src/spire/executor/executor.py:39:   from fastmcp import Client

`grep -rn 'from mcp\.\|import mcp' src/ --include='*.py'`:

    src/spire/agent/runner.py:33:  from mcp.client.streamable_http import streamablehttp_client

**The rest of `spire` is on `fastmcp 4` + `mcp 2.x`.** Only `runner.py`
uses `langchain-mcp-adapters`, and it does so for one function:
`load_mcp_tools` (line 29). That adapter is the outlier, not the
mainstream of the codebase.

## Recommended permanent fix (separate PR)

Migrate `src/spire/agent/runner.py` off `langchain-mcp-adapters` to
`fastmcp.Client` (or `langchain[mcp]` with a `fastmcp.Client` target,
per LangChain MCP docs). The rest of the codebase keeps its current
stack. `langchain-mcp-adapters` is removed from `requirements.txt`.

The migration surface is one file (`runner.py`) and one test file
(`tests/test_agent_runner.py`). It is not a pin, not a skip, and not
`mcp<2` — the latter two would break the three `fastmcp 4` consumers.

## What PR #1 does about it

Nothing. PR #1's V6 is deferred with a pointer to this file. Its
V-walk records the branch's own tests as green (`10 passed` in
`tests/test_sample_and_disclose_po.py`). V6 will be re-run once this
file's recommended fix has landed as its own PR.

## Not checked

- Whether `langchain[mcp]` accepts a `fastmcp.Client` in the current
  installed `langchain-core` version — checked only via the
  LangChain MCP docs, not empirically.
- Whether the 66 pre-existing failures on `master` include anything
  other than pod-reachability and SQL emitter fixture drift.
- Whether any external deployment of `spire` currently has `mcp<2`
  installed and is therefore running the rest of `spire` against an
  unsupported SDK — deployment drift check is not in scope here.
