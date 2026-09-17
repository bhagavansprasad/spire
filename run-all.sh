#!/usr/bin/env bash
#
# run-all.sh — start, inspect, and stop the MCP / API / UI services.
#
#   ./run-all.sh --dev        start dev  (foreground; Ctrl-C stops all)
#   ./run-all.sh --dev &      start dev  (background; shell returns)
#   ./run-all.sh --runtime    start runtime (same two forms)
#   ./run-all.sh --status     show which ports are up and which PIDs
#   ./run-all.sh --stop       stop everything started by run-all.sh
#
# THE MODE IS REQUIRED for start. There is no default.
#
# Ports live in ONE place: SPIRE-PORTS.env at the repo root. Change them
# there and nothing else needs to move.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ── Ports ──────────────────────────────────────────────────────────────
# shellcheck disable=SC1091
source "$REPO_ROOT/SPIRE-PORTS.env"

LOG_DIR="${LOG_DIR:-logs}"
PIDFILE="$LOG_DIR/run-all.pid"
mkdir -p "$LOG_DIR"

# ── Helpers ────────────────────────────────────────────────────────────

port_open() {
  local port="$1"
  (echo > "/dev/tcp/127.0.0.1/$port") 2>/dev/null
}

pid_alive() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

usage() {
  cat >&2 <<EOF
Usage: ./run-all.sh --dev | --runtime [--tail] [&]
       ./run-all.sh --status
       ./run-all.sh --stop

  --dev         local development  (MCP ${SPIRE_DEV_MCP_PORT}, API ${SPIRE_DEV_API_PORT}, UI ${SPIRE_DEV_UI_PORT})
  --runtime     tester runtime     (MCP ${SPIRE_RUNTIME_MCP_PORT}, API ${SPIRE_RUNTIME_API_PORT}, UI ${SPIRE_RUNTIME_UI_PORT})
  --tail        (with a start mode) tail the UI log after start
  --status      report which ports are listening and which PIDs
  --stop        stop the services started by this script
EOF
}

# ── --stop ─────────────────────────────────────────────────────────────

stop_all() {
  if [ ! -f "$PIDFILE" ]; then
    echo "run-all.sh: nothing to stop (no pidfile at $PIDFILE)"
    return 0
  fi
  local pid
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if ! pid_alive "$pid"; then
    echo "run-all.sh: stale pidfile (PID $pid not alive); removing"
    rm -f "$PIDFILE"
    return 0
  fi
  echo "run-all.sh: stopping PID $pid (children will follow)"
  kill -TERM "$pid" 2>/dev/null || true
  # Wait up to 5s for the trap to fire and the pidfile to be removed.
  local i=0
  while [ -f "$PIDFILE" ] && [ "$i" -lt 50 ]; do
    sleep 0.1
    i=$((i + 1))
  done
  if [ -f "$PIDFILE" ]; then
    echo "run-all.sh: graceful stop timed out; forcing"
    kill -KILL "$pid" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
  echo "run-all.sh: stopped."
}

# ── --status ───────────────────────────────────────────────────────────

show_status() {
  echo "run-all.sh status"
  echo "──────────────────"
  echo
  if [ -f "$PIDFILE" ]; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if pid_alive "$pid"; then
      echo "Supervisor:  running  (PID $pid)"
    else
      echo "Supervisor:  NOT running  (stale pidfile: $pid)"
    fi
  else
    echo "Supervisor:  NOT running  (no pidfile)"
  fi
  echo
  printf '%-10s %-7s %-8s %s\n' "Port" "Mode" "Service" "State"
  printf '%-10s %-7s %-8s %s\n' "----" "----" "-------" "-----"
  local entry port mode svc state
  for entry in \
    "$SPIRE_DEV_MCP_PORT|dev|MCP" \
    "$SPIRE_DEV_API_PORT|dev|API" \
    "$SPIRE_DEV_UI_PORT|dev|UI" \
    "$SPIRE_RUNTIME_MCP_PORT|runtime|MCP" \
    "$SPIRE_RUNTIME_API_PORT|runtime|API" \
    "$SPIRE_RUNTIME_UI_PORT|runtime|UI"
  do
    port="${entry%%|*}"; entry="${entry#*|}"
    mode="${entry%%|*}"; svc="${entry#*|}"
    if port_open "$port"; then state="up"; else state="down"; fi
    printf '%-10s %-7s %-8s %s\n' "$port" "$mode" "$svc" "$state"
  done
}

# ── Dispatch ───────────────────────────────────────────────────────────

case "${1:-}" in
  --stop)   stop_all; exit 0 ;;
  --status) show_status; exit 0 ;;
  --help|-h) usage; exit 0 ;;
esac

MODE=""
TAIL_UI=0
for arg in "$@"; do
  case "$arg" in
    --dev)      MODE="dev" ;;
    --runtime)  MODE="runtime" ;;
    --tail)     TAIL_UI=1 ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 2 ;;
  esac
done

if [ -z "$MODE" ]; then
  usage
  exit 2
fi

# Refuse to start a second supervisor.
if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if pid_alive "$OLD"; then
    echo "run-all.sh: already running (PID $OLD)." >&2
    echo "             use './run-all.sh --stop' first, or './run-all.sh --status'." >&2
    exit 1
  fi
  rm -f "$PIDFILE"
fi

# Warn if the old file is still around.
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

PIDS=()
CLEANED=0

cleanup() {
  if [ "$CLEANED" -eq 1 ]; then return; fi
  CLEANED=1
  echo ""
  echo "Stopping services..."
  for pid in "${PIDS[@]:-}"; do
    if [ -n "$pid" ] && pid_alive "$pid"; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  sleep 1
  for pid in "${PIDS[@]:-}"; do
    if [ -n "$pid" ] && pid_alive "$pid"; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
  rm -f "$PIDFILE"
  echo "Stopped."
}
trap cleanup EXIT INT TERM HUP

echo "$$" > "$PIDFILE"

echo "Mode:   $MODE"
echo "Log directory: $LOG_DIR"
echo "Ports:  MCP $MCP_PORT   API $API_PORT   UI $UI_PORT"

SPIRE_MCP_PORT="$MCP_PORT" bash run-server.sh > "$LOG_DIR/mcp.log" 2>&1 &
PIDS+=("$!")
echo "MCP   pid=${PIDS[-1]}   http://127.0.0.1:$MCP_PORT     log: $LOG_DIR/mcp.log"
sleep 2

SPIRE_API_PORT="$API_PORT" \
SPIRE_MCP_URL="http://127.0.0.1:$MCP_PORT/mcp" \
SPIRE_UI_ORIGIN="http://localhost:$UI_PORT" \
  python -m spire.api.server > "$LOG_DIR/api.log" 2>&1 &
PIDS+=("$!")
echo "API   pid=${PIDS[-1]}   http://localhost:$API_PORT     log: $LOG_DIR/api.log"
sleep 1

SPIRE_UI_PORT="$UI_PORT" \
SPIRE_API_URL="http://localhost:$API_PORT" \
  spire-ui > "$LOG_DIR/ui.log" 2>&1 &
PIDS+=("$!")
echo "UI    pid=${PIDS[-1]}   http://localhost:$UI_PORT     log: $LOG_DIR/ui.log"

echo ""
echo "All three started. Supervisor PID $$ (pidfile: $PIDFILE)."
echo "  ./run-all.sh --status   show ports and state"
echo "  ./run-all.sh --stop     stop everything"
echo ""

if [ "$TAIL_UI" -eq 1 ]; then
  tail -f "$LOG_DIR/ui.log" || true
else
  while :; do
    sleep 3600 &
    wait $! 2>/dev/null || true
  done
fi