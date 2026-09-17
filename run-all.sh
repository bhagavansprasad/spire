#!/usr/bin/env bash
#
# run-all.sh — start, inspect, and stop the SPIRE MCP / API / UI services.
#
#   ./run-all.sh                 start the current mode (from SPIRE_MODE)
#   ./run-all.sh &               same, in the background
#   ./run-all.sh --status        show the current mode's three ports
#   ./run-all.sh --stop          stop the current mode
#   ./run-all.sh --tail          start, then tail the UI log
#
#   --dev / --runtime            override the current mode for one command
#
# The current mode comes from $SPIRE_MODE, set by spire() / spirer() in
# ~/.bashrc when you cd into a tree. If it is not set, the script refuses
# to start/status/stop and tells you to run 'spire' or 'spirer' first.
#
# --stop sweeps only the current mode's three ports, so stopping dev can
# never touch runtime and vice versa — even when orphans are involved.
#
# Ports live in ONE place: SPIRE-PORTS.env at the repo root.

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

pid_alive() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

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
}

is_our_process() {
  local pid="$1"
  local f="/proc/$pid/cmdline"
  [ -r "$f" ] || return 1
  local cmd
  cmd="$(tr '\0' ' ' < "$f" 2>/dev/null || true)"
  case "$cmd" in
    *spire/mcp_server/server.py*|*spire.mcp_server*|\
    *spire/api/server.py*|*spire.api.server*|\
    *spire/ui/app.py*|*spire-ui*)
      return 0 ;;
  esac
  return 1
}

PIDFILE_MODE=""
PIDFILE_SUPERVISOR=""
PIDFILE_MCP=""
PIDFILE_API=""
PIDFILE_UI=""
read_pidfile() {
  PIDFILE_MODE=""; PIDFILE_SUPERVISOR=""
  PIDFILE_MCP="";  PIDFILE_API=""; PIDFILE_UI=""
  [ -f "$PIDFILE" ] || return 0
  local line key value
  while IFS= read -r line; do
    key="${line%%=*}"; value="${line#*=}"
    case "$key" in
      MODE)       PIDFILE_MODE="$value" ;;
      SUPERVISOR) PIDFILE_SUPERVISOR="$value" ;;
      MCP)        PIDFILE_MCP="$value" ;;
      API)        PIDFILE_API="$value" ;;
      UI)         PIDFILE_UI="$value" ;;
    esac
  done < "$PIDFILE"
}

ports_for_mode() {
  case "$1" in
    dev)
      echo "$SPIRE_DEV_MCP_PORT|MCP"
      echo "$SPIRE_DEV_API_PORT|API"
      echo "$SPIRE_DEV_UI_PORT|UI" ;;
    runtime)
      echo "$SPIRE_RUNTIME_MCP_PORT|MCP"
      echo "$SPIRE_RUNTIME_API_PORT|API"
      echo "$SPIRE_RUNTIME_UI_PORT|UI" ;;
  esac
}

usage() {
  cat >&2 <<EOF
Usage: ./run-all.sh [--dev | --runtime] [--status | --stop | --tail]

  (no flags)    start the current mode (from \$SPIRE_MODE)
  --status      show the current mode's ports, PIDs, and owner
  --stop        stop the current mode's services (only that mode)
  --tail        start, then tail the UI log

  --dev         override the current mode to dev
  --runtime     override the current mode to runtime

The current mode is \$SPIRE_MODE, set by spire() / spirer() in ~/.bashrc.
If it is not set, run 'spire' or 'spirer' first, or pass --dev / --runtime.

Ports:
  dev      MCP ${SPIRE_DEV_MCP_PORT}  API ${SPIRE_DEV_API_PORT}  UI ${SPIRE_DEV_UI_PORT}
  runtime  MCP ${SPIRE_RUNTIME_MCP_PORT}  API ${SPIRE_RUNTIME_API_PORT}  UI ${SPIRE_RUNTIME_UI_PORT}
EOF
}

# ── Argument parsing ──────────────────────────────────────────────────

# SPIRE_MODE is the default; explicit --dev / --runtime overrides.
MODE="${SPIRE_MODE:-}"
ACTION=""
TAIL_UI=0
for arg in "$@"; do
  case "$arg" in
    --dev)      MODE="dev" ;;
    --runtime)  MODE="runtime" ;;
    --status)   ACTION="status" ;;
    --stop)     ACTION="stop" ;;
    --tail)     TAIL_UI=1 ;;
    --help|-h)  usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 2 ;;
  esac
done

if [ -z "$MODE" ]; then
  echo "run-all.sh: \$SPIRE_MODE is not set and no --dev / --runtime was given." >&2
  echo "             Run 'spire' or 'spirer' first, or pass --dev / --runtime." >&2
  exit 2
fi

if [ "$MODE" != "dev" ] && [ "$MODE" != "runtime" ]; then
  echo "run-all.sh: \$SPIRE_MODE has invalid value '$MODE' (want 'dev' or 'runtime')." >&2
  exit 2
fi

# ── --stop ─────────────────────────────────────────────────────────────

stop_mode() {
  local target_mode="$1"
  local stopped=0

  if [ -f "$PIDFILE" ]; then
    read_pidfile
    if [ -n "$PIDFILE_MODE" ] && [ "$PIDFILE_MODE" != "$target_mode" ]; then
      echo "run-all.sh: pidfile is for mode '$PIDFILE_MODE'; not touching it."
    elif pid_alive "$PIDFILE_SUPERVISOR"; then
      echo "run-all.sh: stopping $target_mode supervisor PID $PIDFILE_SUPERVISOR"
      kill -TERM "$PIDFILE_SUPERVISOR" 2>/dev/null || true
      local i=0
      while [ -f "$PIDFILE" ] && [ "$i" -lt 50 ]; do
        sleep 0.1
        i=$((i + 1))
      done
      if [ -f "$PIDFILE" ]; then
        echo "run-all.sh: graceful stop timed out; forcing supervisor"
        kill -KILL "$PIDFILE_SUPERVISOR" 2>/dev/null || true
      fi
      stopped=1
      rm -f "$PIDFILE"
    else
      echo "run-all.sh: stale pidfile (supervisor $PIDFILE_SUPERVISOR not alive); removing"
      rm -f "$PIDFILE"
    fi
  fi

  local line port svc pid
  while IFS= read -r line; do
    port="${line%%|*}"; svc="${line#*|}"
    for pid in $(pids_on_port "$port"); do
      if is_our_process "$pid"; then
        echo "run-all.sh: killing orphan $svc on port $port (PID $pid)"
        kill -TERM "$pid" 2>/dev/null || true
        stopped=1
      fi
    done
  done < <(ports_for_mode "$target_mode")

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
    echo "run-all.sh: $target_mode stopped."
  else
    echo "run-all.sh: no $target_mode processes to stop."
  fi
}

# ── --status ───────────────────────────────────────────────────────────

show_status() {
  local filter_mode="$1"

  echo "run-all.sh status  (mode: $filter_mode)"
  echo "───────────────────────────────────"
  echo

  read_pidfile
  local sup_pid="$PIDFILE_SUPERVISOR"
  local sup_alive=0
  pid_alive "$sup_pid" && sup_alive=1

  if [ -n "$sup_pid" ] && [ "$sup_alive" = "1" ] && [ "$PIDFILE_MODE" = "$filter_mode" ]; then
    echo "Supervisor:  running  (PID $sup_pid, mode $PIDFILE_MODE)"
  elif [ -n "$sup_pid" ] && [ "$PIDFILE_MODE" = "$filter_mode" ]; then
    echo "Supervisor:  NOT running  (stale pidfile: $sup_pid)"
  else
    echo "Supervisor:  NOT running  (no pidfile for $filter_mode)"
  fi
  echo

  printf '%-7s %-6s %-6s %-8s %s\n' "Port" "Svc" "State" "PID" "Owner"
  printf '%-7s %-6s %-6s %-8s %s\n' "----" "---" "-----" "---" "-----"

  local line port svc state pid owner pids recorded
  while IFS= read -r line; do
    port="${line%%|*}"; svc="${line#*|}"
    case "$svc" in
      MCP) recorded="$PIDFILE_MCP" ;;
      API) recorded="$PIDFILE_API" ;;
      UI)  recorded="$PIDFILE_UI" ;;
    esac
    pids="$(pids_on_port "$port")"
    if [ -z "$pids" ]; then
      state="down"; pid="-"; owner="-"
    else
      state="up"
      pid="$(echo "$pids" | head -n1)"
      if [ "$sup_alive" = "1" ] && [ "$PIDFILE_MODE" = "$filter_mode" ]; then
        owner="us"
      elif is_our_process "$pid"; then
        owner="external"
      else
        owner="other"
      fi
    fi
    printf '%-7s %-6s %-6s %-8s %s\n' "$port" "$svc" "$state" "$pid" "$owner"
  done < <(ports_for_mode "$filter_mode")

  echo
  echo "Owner:  us       = started by this tree's supervisor"
  echo "        external = a SPIRE process on our port, not from this tree"
  echo "        other    = not a SPIRE process; --stop will NOT kill it"
}

# ── Dispatch ──────────────────────────────────────────────────────────

case "$ACTION" in
  stop)   stop_mode   "$MODE"; exit 0 ;;
  status) show_status "$MODE"; exit 0 ;;
esac

# ── Start ─────────────────────────────────────────────────────────────

if [ -f "$PIDFILE" ]; then
  read_pidfile
  if [ -n "$PIDFILE_MODE" ] && [ "$PIDFILE_MODE" != "$MODE" ]; then
    echo "run-all.sh: a pidfile exists for mode '$PIDFILE_MODE'." >&2
    echo "             that is the OTHER mode — leaving it alone." >&2
  elif pid_alive "$PIDFILE_SUPERVISOR"; then
    echo "run-all.sh: already running (PID $PIDFILE_SUPERVISOR, mode $MODE)." >&2
    echo "             use './run-all.sh --stop' first." >&2
    exit 1
  else
    rm -f "$PIDFILE"
  fi
fi

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
  local pid
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
  local line pid2
  while IFS= read -r line; do
    local p="${line%%|*}"
    for pid2 in $(pids_on_port "$p"); do
      if is_our_process "$pid2"; then
        kill -9 "$pid2" 2>/dev/null || true
      fi
    done
  done < <(ports_for_mode "$MODE")
  rm -f "$PIDFILE"
  echo "Stopped."
}
trap cleanup EXIT INT TERM HUP

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

{
  echo "MODE=$MODE"
  echo "SUPERVISOR=$$"
  echo "MCP=${PIDS[0]}"
  echo "API=${PIDS[1]}"
  echo "UI=${PIDS[2]}"
} > "$PIDFILE"

echo ""
echo "All three started. Supervisor PID $$ (pidfile: $PIDFILE)."
echo "  ./run-all.sh --status   show ports, PIDs, and owner"
echo "  ./run-all.sh --stop     stop these services only"
echo ""

if [ "$TAIL_UI" -eq 1 ]; then
  tail -f "$LOG_DIR/ui.log" || true
else
  wait
fi