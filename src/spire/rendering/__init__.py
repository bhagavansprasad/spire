"""Display rendering layer.

`formatters.py` lived at `scripts/display_formatters.py` until Phase 1
task 1.2. That location was historical, not architectural — the module
is imported by tests and by scripts, and it belongs inside the package
so an installable entry point can reach it without a sys.path trick.

Re-exports the public surface so `from spire.rendering import X` works
for the common names. Callers that need a helper by name still import
it from `spire.rendering.formatters`.
"""

from spire.rendering.formatters import (  # noqa: F401
    _format_intent,
    _format_plan,
    _format_outputs,
    _format_synthesized,
    _format_summary,
    _format_projected_table,
    _render_records,
    _with_truncation,
    _is_quantity,
    MCP_SERVER_URL,
)
