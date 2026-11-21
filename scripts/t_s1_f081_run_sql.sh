#!/usr/bin/env bash
# Execute every re-emitted SQL statement (t_f081_sql/pNN.sql) via runsql.sh.
# Strips trailing "-- ASSUMPTION ..." comment blocks (documentation only;
# DBMS_XMLGEN chokes on trailing text). Captures exit code + row count.
set -uo pipefail
cd /home/bhagavan/aura/spire

printf '%-8s %-6s %-7s %s\n' "FILE" "EXIT" "ROWS" "NOTE"
printf '%s\n' "-------------------------------------------------------------"

for f in t_f081_sql/p*.sql; do
  base=$(basename "$f" .sql)
  clean="t_f081_sql/${base}.run.sql"

  # Keep everything up to the first trailing ASSUMPTION block.
  awk '/^-- ASSUMPTION/{exit} {print}' "$f" > "$clean"
  # Strip a trailing blank tail.
  sed -i -e :a -e '/^\s*$/{$d;N;ba' -e '}' "$clean" 2>/dev/null || true

  out="t_f081_sql/${base}.out"
  FORMAT=csv ./runsql.sh -f "$clean" > "$out" 2>&1
  rc=$?

  rows=$(grep -oE '^[0-9]+ row\(s\)' "$out" | head -1 | grep -oE '^[0-9]+')
  [ -z "${rows:-}" ] && rows="-"

  note=""
  if [ $rc -ne 0 ]; then
    note=$(grep -oE 'ORA-[0-9]+|DPY-[0-9]+' "$out" | head -1)
    if grep -q "unmapped tool_arg" "$clean"; then note="NO PREDICATE (unmapped) + ${note}"; fi
    if grep -q ":iteration_value" "$clean"; then note="UNBOUND BIND :iteration_value"; fi
  fi

  printf '%-8s %-6s %-7s %s\n' "$base" "$rc" "$rows" "$note"
done
