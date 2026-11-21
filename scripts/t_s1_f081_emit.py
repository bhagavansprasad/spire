"""Rebuild each plan from the run log and re-emit UNWRAPPED SQL.

Why: promptkit's SQL diagnostic block is hard-wrapped (and truncates) at
80 columns by the logger, so the SQL in t_f081_litmus_run.txt cannot be
executed verbatim. The Plan block, however, is short and intact. The
emitter is a pure function of (plan, overlay), so re-emitting from the
recovered plan reproduces the same SQL without another LLM run.
"""
import ast
import re
from pathlib import Path

from spire.rendering.sql_emitter import emit_sql
from spire.planner.models import Step

ROOT = Path("/home/bhagavan/aura/spire")
OUT = ROOT / "t_f081_sql"
OUT.mkdir(exist_ok=True)

log = (ROOT / "t_f081_litmus_run.txt").read_text(errors="replace")
blocks = re.split(r"^={60,}\n\[(\d+) of 40\]\n", log, flags=re.M)

rows = []
for i in range(1, len(blocks) - 1, 2):
    n = int(blocks[i])
    body = blocks[i + 1]
    if "SQL projection:" not in body:
        continue

    # steps:  "  Step 2: tool_name" followed by its tool_args line
    steps = []
    for m in re.finditer(
        r"^  Step (\d+): (\S+)\n    tool_args:[ \t]+([^\n]*)",
        body, flags=re.M,
    ):
        sid, tool, raw = int(m.group(1)), m.group(2), m.group(3).strip()
        try:
            args = ast.literal_eval(raw)
        except Exception:
            args = {}
        steps.append((sid, tool, args))

    if not steps:
        continue

    step_objs = [
        Step(step_id=sid, tool_name=tool, tool_args=args,
             iterate_over=None, client_filters=(),
             output_name=f"out{sid}", output_dedupe_by=None)
        for sid, tool, args in steps
    ]
    try:
        statements = emit_sql(step_objs)
    except Exception as exc:  # noqa: BLE001
        rows.append((n, steps, None, f"emit error: {exc}"))
        continue

    sql = "\n".join(statements)
    path = OUT / f"p{n:02d}.sql"
    path.write_text(sql + "\n")
    rows.append((n, steps, path, None))

print(f"{'#':>3} {'steps':<40} {'sql file':<16} note")
print("-" * 88)
for n, steps, path, err in rows:
    desc = ", ".join(f"{t}({','.join(a) or '-'})" for _, t, a in steps)
    print(f"{n:>3} {desc[:40]:<40} {str(path.name) if path else '-':<16} {err or ''}")

print()
print(f"SQL files written: {len([r for r in rows if r[2]])} -> {OUT}")
