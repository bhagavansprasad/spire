#!/usr/bin/env bash
#
# spire.sh — start, inspect, and stop the SPIRE MCP / API / UI services.
#
#   ./spire.sh --dev              start dev services (background)
#   ./spire.sh --runtime          start runtime services (background)
#   ./spire.sh --dev --mcp-only   start ONLY the MCP server (foreground,
#                                 with --reload — for MCP development)
#   ./spire.sh --status           show the current mode's ports and PIDs
#   ./spire.sh --stop             stop the current mode's services
#   ./spire.sh --tail             start, then tail the UI log
#   ./spire.sh --help             show this help
#   ./spire.sh                    show this help (no args)
#
# The current mode comes from $SPIRE_MODE, set by spire() / spirer() in
# ~/.bashrc when you cd into a tree. If it is not set, pass --dev or
# --runtime explicitly.
#
# MODE ISOLATION. Dev and runtime never touch each other:
#   - different ports (from SPIRE-PORTS.env)
#   - different pidfiles (logs/spire-dev.pid vs logs/spire-runtime.pid)
#   - --stop and --preflight sweep ONLY the target mode's three ports
# Running `./spire.sh --dev` cannot affect a runtime process, and
# `./spire.sh --runtime --stop` cannot affect a dev process.
#
# Started services run in the BACKGROUND: this script spawns them under
# nohup, writes their PIDs to the mode's pidfile, and exits. Use
# ./spire.sh --stop to stop them.
#
# Ports live in ONE place: SPIRE-PORTS.env at the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ── Ports ──────────────────────────────────────────────────────────────
# shellcheck disable=SC1091
source "$REPO_ROOT/SPIRE-PORTS.env"

LOG_DIR="${LOG_DIR:-logs}"
mkdir -p "$LOG_DIR"

# PIDFILE is set after MODE is parsed — one pidfile per mode, so dev and
# runtime can never read or clobber each other's state.
PIDFILE=""

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

PIDFILE_MCP=""
PIDFILE_API=""
PIDFILE_UI=""
read_pidfile() {
  PIDFILE_MCP=""; PIDFILE_API=""; PIDFILE_UI=""
  [ -n "$PIDFILE" ] || return 0
  [ -f "$PIDFILE" ] || return 0
  local line key value
  while IFS= read -r line; do
    key="${line%%=*}"; value="${line#*=}"
    case "$key" in
      MCP) PIDFILE_MCP="$value" ;;
      API) PIDFILE_API="$value" ;;
      UI)  PIDFILE_UI="$value" ;;
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
Usage: ./spire.sh [--dev | --runtime] [--status | --stop | --tail | --mcp-only]

  (no args)     show this help
  (no action)   start the current mode's services in the background
  --status      show the current mode's ports, PIDs, and owner
  --stop        stop the current mode's services (only that mode)
  --tail        start, then tail the UI log
  --mcp-only    start ONLY the MCP server (foreground, --reload)

  --dev         override the current mode to dev
  --runtime     override the current mode to runtime
  --help, -h    show this help

The current mode is \$SPIRE_MODE, set by spire() / spirer() in ~/.bashrc.
If it is not set, run 'spire' or 'spirer' first, or pass --dev / --runtime.

Ports:
  dev      MCP ${SPIRE_DEV_MCP_PORT}  API ${SPIRE_DEV_API_PORT}  UI ${SPIRE_DEV_UI_PORT}
  runtime  MCP ${SPIRE_RUNTIME_MCP_PORT}  API ${SPIRE_RUNTIME_API_PORT}  UI ${SPIRE_RUNTIME_UI_PORT}
EOF
}

# ── Argument parsing ──────────────────────────────────────────────────

if [ "$#" -eq 0 ]; then
  usage
  exit 0
fi

MODE="${SPIRE_MODE:-}"
ACTION=""
TAIL_UI=0
MCP_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --dev)      MODE="dev" ;;
    --runtime)  MODE="runtime" ;;
    --status)   ACTION="status" ;;
    --stop)     ACTION="stop" ;;
    --tail)     TAIL_UI=1 ;;
    --mcp-only) MCP_ONLY=1 ;;
    --help|-h)  usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 2 ;;
  esac
done

if [ -z "$MODE" ]; then
  echo "spire.sh: \$SPIRE_MODE is not set and no --dev / --runtime was given." >&2
  echo "          Run 'spire' or 'spirer' first, or pass --dev / --runtime." >&2
  echo >&2
  usage
  exit 2
fi

if [ "$MODE" != "dev" ] && [ "$MODE" != "runtime" ]; then
  echo "spire.sh: \$SPIRE_MODE has invalid value '$MODE' (want 'dev' or 'runtime')." >&2
  exit 2
fi

# ── Mode-scoped pidfile ───────────────────────────────────────────────
# One pidfile per mode. Dev and runtime never read or write the same
# file, so neither can see the other's state or sweep the other's PIDs.
PIDFILE="$LOG_DIR/spire-$MODE.pid"

# ── --stop ─────────────────────────────────────────────────────────────

stop_mode() {
  local target_mode="$1"
  local pidfile="$LOG_DIR/spire-$target_mode.pid"
  local stopped=0

  if [ -f "$pidfile" ]; then
    local line key value
    local mcp_pid="" api_pid="" ui_pid=""
    while IFS= read -r line; do
      key="${line%%=*}"; value="${line#*=}"
      case "$key" in
        MCP) mcp_pid="$value" ;;
        API) api_pid="$value" ;;
        UI)  ui_pid="$value" ;;
      esac
    done < "$pidfile"

    local pid
    for pid in "$mcp_pid" "$api_pid" "$ui_pid"; do
      if pid_alive "$pid"; then
        echo "spire.sh: stopping PID $pid"
        kill -TERM "$pid" 2>/dev/null || true
        stopped=1
      fi
    done
    rm -f "$pidfile"
  fi

  # Sweep the target mode's ports. Because dev and runtime use different
  # ports, this can never touch the other mode's processes.
  local line port svc pid
  while IFS= read -r line; do
    port="${line%%|*}"; svc="${line#*|}"
    for pid in $(pids_on_port "$port"); do
      if is_our_process "$pid"; then
        echo "spire.sh: killing orphan $svc on port $port (PID $pid)"
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
    echo "spire.sh: $target_mode stopped."
  else
    echo "spire.sh: no $target_mode processes to stop."
  fi
}

# ── --status ───────────────────────────────────────────────────────────

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

  echo
  echo "--stop stops every SPIRE process on these ports; others are left alone."
}

# ── Dispatch ──────────────────────────────────────────────────────────

case "$ACTION" in
  stop)   stop_mode   "$MODE"; exit 0 ;;
  status) show_status "$MODE"; exit 0 ;;
esac

# ── Start ─────────────────────────────────────────────────────────────

# Pre-flight: refuse to start if the target mode's ports are already held
# by another SPIRE process. Without this, the child processes fail to
# bind and exit, but the script still prints "Started" — the pidfile
# records dead PIDs and the ports stay held by whatever was already there.
_preflight_ports() {
  local check_ports="$1"   # newline-separated "port|svc" entries
  local held=0
  local line port svc pid
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    port="${line%%|*}"; svc="${line#*|}"
    for pid in $(pids_on_port "$port"); do
      if is_our_process "$pid"; then
        echo "spire.sh: port $port ($svc) is already held by SPIRE PID $pid" >&2
        held=1
      fi
    done
  done <<< "$check_ports"
  return "$held"
}

# Check this mode's OWN pidfile. Other modes are invisible here — their
# pidfiles have a different name.
if [ -f "$PIDFILE" ]; then
  read_pidfile
  any_alive=0
  for pid in "$PIDFILE_MCP" "$PIDFILE_API" "$PIDFILE_UI"; do
    pid_alive "$pid" && any_alive=1
  done
  if [ "$any_alive" = "1" ]; then
    echo "spire.sh: already running for mode $MODE." >&2
    echo "          use './spire.sh $MODE --stop' first, or './spire.sh --status'." >&2
    exit 1
  fi
  rm -f "$PIDFILE"
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

# Pre-flight port check for THIS mode only.
if [ "$MCP_ONLY" = "1" ]; then
  if ! _preflight_ports "$MCP_PORT|MCP"; then
    echo "spire.sh: run './spire.sh $MODE --stop' first, or './spire.sh --status'." >&2
    exit 1
  fi
else
  if ! _preflight_ports "$(ports_for_mode "$MODE")"; then
    echo "spire.sh: run './spire.sh $MODE --stop' first, or './spire.sh --status'." >&2
    exit 1
  fi
fi

# ── --mcp-only: foreground, reload, blocking ──────────────────────────
# Preserves what run-server.sh used to be. For MCP development, where
# you want the reload loop's output on the terminal.
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
echo "MCP   pid=$MCP_PID   http://127.0.0.1:$MCP_PORT     log: $LOG_DIR/mcp.log"
sleep 2

SPIRE_API_PORT="$API_PORT" \
SPIRE_MCP_URL="http://127.0.0.1:$MCP_PORT/mcp" \
SPIRE_UI_ORIGIN="http://localhost:$UI_PORT" \
  nohup python -m spire.api.server \
    > "$LOG_DIR/api.log" 2>&1 &
API_PID=$!
echo "API   pid=$API_PID   http://localhost:$API_PORT     log: $LOG_DIR/api.log"
sleep 1

SPIRE_UI_PORT="$UI_PORT" \
SPIRE_API_URL="http://localhost:$API_PORT" \
  nohup spire-ui \
    > "$LOG_DIR/ui.log" 2>&1 &
UI_PID=$!
echo "UI    pid=$UI_PID   http://localhost:$UI_PORT     log: $LOG_DIR/ui.log"

{
  echo "MODE=$MODE"
  echo "MCP=$MCP_PID"
  echo "API=$API_PID"
  echo "UI=$UI_PID"
} > "$PIDFILE"

echo
echo "Started. PIDs written to $PIDFILE."
echo "  ./spire.sh --status   show ports and PIDs"
echo "  ./spire.sh --stop     stop these services only"

if [ "$TAIL_UI" = "1" ]; then
  tail -f "$LOG_DIR/ui.log" || true
fi