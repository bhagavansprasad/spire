#!/usr/bin/env bash
#
# spire.sh — start, inspect, and stop the SPIRE MCP / API / UI services.
#
#   ./spire.sh --dev              start dev services (background)
#   ./spire.sh --runtime          start runtime services (background)
#   ./spire.sh --dev --mcp-only   start ONLY the MCP server (foreground, --reload)
#   ./spire.sh --status           show the current mode's ports and holder PIDs
#   ./spire.sh --stop             stop the current mode's services
#   ./spire.sh --tail             start, then tail the UI log
#   ./spire.sh --help             show this help
#   ./spire.sh                    show this help (no args)
#
# DESIGN
#   PORTS ARE THE SOURCE OF TRUTH.
#     "Is it running?"  -> query the port.
#     "Stop it."        -> sweep the port.
#   A pidfile is kept for a best-effort extra kill of processes that are
#   alive but not yet bound (mid-startup), and for diagnostics. It is
#   never consulted to decide whether the system is running.
#
#   Why not trust the pidfile:
#     - `fastmcp run --reload` forks; the recorded PID is the supervisor,
#       not the port holder.
#     - After a reboot the kernel reassigns PIDs; a recorded PID may
#       belong to an unrelated process.
#     - The API and UI take 5-15s to bind their ports, so a "running"
#       pidfile can precede a bound port by many seconds.
#
#   START waits (bounded) for each port to bind and reports OK/FAILED
#   per service, so "Started" means what it says.
#
# MODE ISOLATION
#   Dev and runtime use different ports, different pidfiles, and --stop
#   sweeps only the target mode's three ports. Neither can touch the
#   other.
#
# Ports live in ONE place: SPIRE-PORTS.env at the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
source "$REPO_ROOT/SPIRE-PORTS.env"

LOG_DIR="${LOG_DIR:-logs}"
mkdir -p "$LOG_DIR"

# How long to wait for a newly-spawned service to bind its port.
BIND_TIMEOUT_SECS="${BIND_TIMEOUT_SECS:-20}"

# ── Helpers ────────────────────────────────────────────────────────────

pid_alive() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# Any PID listening on the given TCP port. Own sockets only for -p info;
# other users' sockets return the line without a PID, which we skip.
pids_on_port() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null \
      | grep -E "[:.]${port}[[:space:]]" \
      | grep -oE 'pid=[0-9]+' \
      | cut -d= -f2 \
      | sort -u
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null
  fi
  return 0
}

# Does the given PID look like one of ours? Used only to avoid killing
# unrelated processes during a port sweep. Falls back to "assume ours"
# for a bare port sweep if the cmdline is unreadable.
is_our_process() {
  local pid="$1"
  local f="/proc/$pid/cmdline"
  [ -r "$f" ] || return 1
  local cmd
  cmd="$(tr '\0' ' ' < "$f" 2>/dev/null || true)"
  case "$cmd" in
    *spire/mcp_server/server.py*|*spire.mcp_server*|\
    *spire/api/server.py*|*spire.api.server*|\
    *spire/ui/app.py*|*spire-ui*|*fastmcp*spire*)
      return 0 ;;
  esac
  return 1
}

ports_for_mode() {
  case "$1" in
    dev)
      echo "$SPIRE_DEV_MCP_PORT|MCP"
      echo "$SPIRE_DEV_API_PORT|API"
      echo "$SPIRE_DEV_UI_PORT|UI" ;;
    production|runtime)
      echo "$SPIRE_RUNTIME_MCP_PORT|MCP"
      echo "$SPIRE_RUNTIME_API_PORT|API"
      echo "$SPIRE_RUNTIME_UI_PORT|UI" ;;
  esac
}

read_pidfile_into() {
  # Args: pidfile. Sets globals PF_MCP PF_API PF_UI.
  PF_MCP=""; PF_API=""; PF_UI=""
  local pf="$1"
  [ -f "$pf" ] || return 0
  local line key value
  while IFS= read -r line; do
    key="${line%%=*}"; value="${line#*=}"
    case "$key" in
      MCP) PF_MCP="$value" ;;
      API) PF_API="$value" ;;
      UI)  PF_UI="$value" ;;
    esac
  done < "$pf"
}

usage() {
  cat >&2 <<EOF
Usage: ./spire.sh [--start | --stop | --status | --restart] [dev | production]

  --start [target]     start services in the background (default: dev)
  --stop  [target]     stop services (default: dev)
  --restart [target]   stop, then start (default: dev)
  --status [target]    show ports and holder PIDs (default: both)

  dev                  default target
  production           the production deployment

  --tail               (with --start) tail the UI log
  --mcp-only           (with --start) MCP only, foreground, --reload
  --help, -h           show this help

  (no args)            show this help

Ports (from SPIRE-PORTS.env):
  dev         MCP ${SPIRE_DEV_MCP_PORT}  API ${SPIRE_DEV_API_PORT}  UI ${SPIRE_DEV_UI_PORT}
  production  MCP ${SPIRE_RUNTIME_MCP_PORT}  API ${SPIRE_RUNTIME_API_PORT}  UI ${SPIRE_RUNTIME_UI_PORT}
EOF
}

# ── Argument parsing ──────────────────────────────────────────────────

if [ "$#" -eq 0 ]; then
  usage
  exit 0
fi

ACTION=""
TARGET=""
TAIL_UI=0
MCP_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --start)    ACTION="start" ;;
    --stop)     ACTION="stop" ;;
    --status)   ACTION="status" ;;
    --restart)  ACTION="restart" ;;
    --tail)     TAIL_UI=1 ;;
    --mcp-only) MCP_ONLY=1 ;;
    --help|-h)  usage; exit 0 ;;
    dev|production) TARGET="$arg" ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 2 ;;
  esac
done

# No action given -> start (same as the old no-action behaviour).
if [ -z "$ACTION" ]; then
  ACTION="start"
fi

# Default target: dev, for start / stop / restart. --status with no
# target means "show both", and is handled at dispatch.
if [ -z "$TARGET" ] && [ "$ACTION" != "status" ]; then
  TARGET="dev"
fi

# Downstream code reads $MODE; keep the name and feed it the target.
MODE="$TARGET"

PIDFILE="$LOG_DIR/spire-$MODE.pid"

# ── --stop ─────────────────────────────────────────────────────────────
#
# Order of business:
#   1. Sweep the target mode's ports and kill any of our processes found.
#      This is the reliable path — the port holder is what --status
#      shows and what --start refuses to collide with.
#   2. If a pidfile exists, kill its PIDs too — but only if they are
#      alive AND still look like ours. This catches mid-startup
#      processes that have not yet bound, and is a no-op for stale
#      files (dead PIDs, or live PIDs reassigned to another process).
#   3. Remove the pidfile.

stop_mode() {
  local target_mode="$1"
  local pidfile="$LOG_DIR/spire-$target_mode.pid"
  local stopped=0

  # 1. Port sweep — primary.
  local line port svc pid
  while IFS= read -r line; do
    port="${line%%|*}"; svc="${line#*|}"
    for pid in $(pids_on_port "$port"); do
      if is_our_process "$pid"; then
        echo "spire.sh: stopping $svc on port $port (PID $pid)"
        kill -TERM "$pid" 2>/dev/null || true
        stopped=1
      else
        echo "spire.sh: port $port is held by non-SPIRE PID $pid; leaving it alone" >&2
      fi
    done
  done < <(ports_for_mode "$target_mode")

  # 2. Pidfile kill — best effort, for not-yet-bound processes.
  if [ -f "$pidfile" ]; then
    local pf_mcp pf_api pf_ui
    read_pidfile_into "$pidfile"
    pf_mcp="$PF_MCP"; pf_api="$PF_API"; pf_ui="$PF_UI"
    for pid in "$pf_mcp" "$pf_api" "$pf_ui"; do
      if pid_alive "$pid" && is_our_process "$pid"; then
        echo "spire.sh: stopping PID $pid from $pidfile"
        kill -TERM "$pid" 2>/dev/null || true
        stopped=1
      fi
    done
    rm -f "$pidfile"
  fi

  if [ "$stopped" = "1" ]; then
    sleep 1
    while IFS= read -r line; do
      port="${line%%|*}"
      for pid in $(pids_on_port "$port"); do
        if is_our_process "$pid"; then
          kill -KILL "$pid" 2>/dev/null || true
        fi
      done
    done < <(ports_for_mode "$target_mode")
    echo "spire.sh: $target_mode stopped."
  else
    echo "spire.sh: no $target_mode processes to stop."
  fi
}

# ── --status ───────────────────────────────────────────────────────────
#
# Ports only. The holder PID comes from ss/lsof. The pidfile's recorded
# PIDs are shown separately, marked "recorded", purely for diagnostics —
# a mismatch is expected for MCP (fork) and harmless for the rest.

show_status() {
  local filter_mode="$1"

  echo "spire.sh status  (mode: $filter_mode)"
  echo "───────────────────────────────────"
  echo

  printf '%-7s %-6s %-6s %s\n' "Port" "Svc" "State" "PID"
  printf '%-7s %-6s %-6s %s\n' "----" "---" "-----" "---"

  local line port svc state pid pids
  while IFS= read -r line; do
    port="${line%%|*}"; svc="${line#*|}"
    pids="$(pids_on_port "$port")"
    if [ -z "$pids" ]; then
      state="down"; pid="-"
    else
      state="up"
      pid="$(echo "$pids" | head -n1)"
    fi
    printf '%-7s %-6s %-6s %s\n' "$port" "$svc" "$state" "$pid"
  done < <(ports_for_mode "$filter_mode")

  local pf="$LOG_DIR/spire-$filter_mode.pid"
  if [ -f "$pf" ]; then
    local pf_mcp pf_api pf_ui
    read_pidfile_into "$pf"
    pf_mcp="$PF_MCP"; pf_api="$PF_API"; pf_ui="$PF_UI"
    echo
    echo "recorded PIDs in $pf (informational; may differ from holders):"
    printf '  MCP=%s  API=%s  UI=%s\n' "${pf_mcp:--}" "${pf_api:--}" "${pf_ui:--}"
  fi

  echo
  echo "--stop sweeps these three ports and kills any SPIRE process found."
}

# ── Dispatch ──────────────────────────────────────────────────────────

case "$ACTION" in
  stop)   stop_mode   "$MODE"; exit 0 ;;
  restart)
    stop_mode "$MODE"
    sleep 2
    ;;
  status)
    if [ -z "$MODE" ]; then
      show_status "dev"
      echo
      show_status "production"
    else
      show_status "$MODE"
    fi
    exit 0 ;;
esac

# ── Start ─────────────────────────────────────────────────────────────

# Pre-flight: refuse if any target port is already held by ANY process.
# Anything on our ports is either us or an explicit conflict; either way
# we should not spawn a duplicate.
_preflight_ports() {
  local check_ports="$1"
  local held=0
  local line port svc pid
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    port="${line%%|*}"; svc="${line#*|}"
    for pid in $(pids_on_port "$port"); do
      if is_our_process "$pid"; then
        echo "spire.sh: port $port ($svc) is already held by SPIRE PID $pid" >&2
      else
        echo "spire.sh: port $port ($svc) is already held by PID $pid (not SPIRE)" >&2
      fi
      held=1
    done
  done <<< "$check_ports"
  return "$held"
}

# Refuse if any PID recorded in this mode's pidfile is still alive AND
# still looks like ours. This catches a mid-startup process that has not
# bound a port yet (so the port check above would have passed).
_preflight_pidfile() {
  [ -f "$PIDFILE" ] || return 0
  local pf_mcp pf_api pf_ui
  read_pidfile_into "$PIDFILE"
  pf_mcp="$PF_MCP"; pf_api="$PF_API"; pf_ui="$PF_UI"
  local pid
  for pid in "$pf_mcp" "$pf_api" "$pf_ui"; do
    if pid_alive "$pid" && is_our_process "$pid"; then
      echo "spire.sh: PID $pid from $PIDFILE is still alive and ours." >&2
      echo "          run './spire.sh --stop $MODE' first, or './spire.sh --status'." >&2
      return 1
    fi
  done
  # All recorded PIDs are either dead or reassigned. Stale file.
  echo "spire.sh: removing stale pidfile $PIDFILE" >&2
  rm -f "$PIDFILE"
  return 0
}

if [ -f "$REPO_ROOT/.spire-dev.env" ]; then
  echo "[warn] .spire-dev.env exists but is IGNORED — ports come from SPIRE-PORTS.env." >&2
fi

if [ "$MODE" = "dev" ]; then
  MCP_PORT="$SPIRE_DEV_MCP_PORT"
  API_PORT="$SPIRE_DEV_API_PORT"
  UI_PORT="$SPIRE_DEV_UI_PORT"
else
  MCP_PORT="$SPIRE_RUNTIME_MCP_PORT"
  API_PORT="$SPIRE_RUNTIME_API_PORT"
  UI_PORT="$SPIRE_RUNTIME_UI_PORT"
fi

# Pre-flight — ports must be free, and the pidfile must not name a live
# process of ours. Both checks are mode-scoped.
check_ports="$(ports_for_mode "$MODE")"
if [ "$MCP_ONLY" = "1" ]; then
  check_ports="$MCP_PORT|MCP"
fi

if ! _preflight_ports "$check_ports"; then
  echo "spire.sh: run './spire.sh --stop $MODE' first, or './spire.sh --status'." >&2
  exit 1
fi

if ! _preflight_pidfile; then
  exit 1
fi

# ── --mcp-only: foreground, reload, blocking ──────────────────────────
if [ "$MCP_ONLY" = "1" ]; then
  echo "Mode:   $MODE (MCP only, foreground)"
  echo "Port:   MCP $MCP_PORT"
  echo
  exec fastmcp run src/spire/mcp_server/server.py \
    -t http \
    --host 127.0.0.1 \
    --port "$MCP_PORT" \
    --reload \
    --reload-dir src/spire
fi

# ── Full start: MCP + API + UI, background ────────────────────────────

echo "Mode:   $MODE (background)"
echo "Logs:   $LOG_DIR/"
echo "Ports:  MCP $MCP_PORT   API $API_PORT   UI $UI_PORT"
echo

SPIRE_MCP_PORT="$MCP_PORT" \
  nohup fastmcp run src/spire/mcp_server/server.py \
    -t http \
    --host 127.0.0.1 \
    --port "$MCP_PORT" \
    --reload \
    --reload-dir src/spire \
    > "$LOG_DIR/mcp.log" 2>&1 &
MCP_PID=$!

# Gate the API spawn on MCP's port being bound.
#
# Why: fastmcp --reload forks a worker that takes a couple of seconds to
# bind the port. The API's lifespan hook connects to MCP ONCE, at
# startup; if the port isn't up yet, the connect fails and the failure is
# cached as a permanent pipeline_error. /status then reports
# "pipeline_ready": false for the life of the process and the UI shows
# the "Not connected" banner, even though all three services are running.
# Waiting here removes the race by construction. If MCP never binds we
# still start the API -- its own timeout will report a clearer error than
# a missing service would.
_mcp_deadline=$((SECONDS + BIND_TIMEOUT_SECS))
while [ "$SECONDS" -lt "$_mcp_deadline" ]; do
  [ -n "$(pids_on_port "$MCP_PORT")" ] && break
  sleep 0.5
done
if [ -z "$(pids_on_port "$MCP_PORT")" ]; then
  echo "spire.sh: MCP did not bind within ${BIND_TIMEOUT_SECS}s; starting API anyway" >&2
fi

SPIRE_API_PORT="$API_PORT" \
SPIRE_MCP_URL="http://127.0.0.1:$MCP_PORT/mcp" \
SPIRE_UI_ORIGIN="http://localhost:$UI_PORT" \
  nohup python -m spire.api.server \
    > "$LOG_DIR/api.log" 2>&1 &
API_PID=$!

SPIRE_UI_PORT="$UI_PORT" \
SPIRE_API_URL="http://localhost:$API_PORT" \
  nohup spire-ui \
    > "$LOG_DIR/ui.log" 2>&1 &
UI_PID=$!

{
  echo "MODE=$MODE"
  echo "MCP=$MCP_PID"
  echo "API=$API_PID"
  echo "UI=$UI_PID"
} > "$PIDFILE"

# Wait (bounded) for each port to bind. Print OK / FAILED per service.
# A service that never binds is reported as FAILED even if its process
# is still alive — the user asked "is the port serving?", and the answer
# is no.
wait_for_bind() {
  local port="$1" name="$2" deadline=$((SECONDS + BIND_TIMEOUT_SECS))
  local pids
  while [ "$SECONDS" -lt "$deadline" ]; do
    pids="$(pids_on_port "$port")"
    if [ -n "$pids" ]; then
      printf '%-5s OK    port %-5s  PID %s\n' "$name" "$port" "$(echo "$pids" | head -n1)"
      return 0
    fi
    sleep 0.5
  done
  printf '%-5s FAILED port %-5s  not bound within %ss (see %s/%s.log)\n' \
    "$name" "$port" "$BIND_TIMEOUT_SECS" "$LOG_DIR" "$(echo "$name" | tr '[:upper:]' '[:lower:]')"
  return 1
}

echo "Waiting up to ${BIND_TIMEOUT_SECS}s for each port to bind..."
all_ok=0
wait_for_bind "$MCP_PORT" "MCP"  || all_ok=1
wait_for_bind "$API_PORT" "API"  || all_ok=1
wait_for_bind "$UI_PORT"  "UI"   || all_ok=1

echo
if [ "$all_ok" = "0" ]; then
  echo "All three up. Supervisor PIDs in $PIDFILE."
else
  echo "At least one service failed to bind. Inspect $LOG_DIR/*.log." >&2
  echo "PIDs recorded in $PIDFILE — './spire.sh --stop' cleans up." >&2
fi
echo "  ./spire.sh --status   show ports and holder PIDs"
echo "  ./spire.sh --stop     stop these services only"

if [ "$TAIL_UI" = "1" ]; then
  tail -f "$LOG_DIR/ui.log" || true
fi