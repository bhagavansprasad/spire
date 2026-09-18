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
# Started services run in the BACKGROUND: this script spawns them under
# nohup, writes their PIDs to logs/spire.pid, and exits. Use
# ./spire.sh --stop to stop them. --stop sweeps only the current mode's
# three ports, so stopping dev can never touch runtime and vice versa.
#
# Ports live in ONE place: SPIRE-PORTS.env at the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ── Ports ──────────────────────────────────────────────────────────────
# shellcheck disable=SC1091
source "$REPO_ROOT/SPIRE-PORTS.env"

LOG_DIR="${LOG_DIR:-logs}"
PIDFILE="$LOG_DIR/spire.pid"
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
PIDFILE_MCP=""
PIDFILE_API=""
PIDFILE_UI=""
read_pidfile() {
  PIDFILE_MODE=""; PIDFILE_MCP=""; PIDFILE_API=""; PIDFILE_UI=""
  [ -f "$PIDFILE" ] || return 0
  local line key value
  while IFS= read -r line; do
    key="${line%%=*}"; value="${line#*=}"
    case "$key" in
      MODE) PIDFILE_MODE="$value" ;;
      MCP)  PIDFILE_MCP="$value" ;;
      API)  PIDFILE_API="$value" ;;
      UI)   PIDFILE_UI="$value" ;;
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

# No arguments at all -> show help and exit.
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

# ── --stop ─────────────────────────────────────────────────────────────

stop_mode() {
  local target_mode="$1"
  local stopped=0

  if [ -f "$PIDFILE" ]; then
    read_pidfile
    if [ -n "$PIDFILE_MODE" ] && [ "$PIDFILE_MODE" != "$target_mode" ]; then
      echo "spire.sh: pidfile is for mode '$PIDFILE_MODE'; not touching it."
    else
      local pid
      for pid in "$PIDFILE_MCP" "$PIDFILE_API" "$PIDFILE_UI"; do
        if pid_alive "$pid"; then
          echo "spire.sh: stopping PID $pid"
          kill -TERM "$pid" 2>/dev/null || true
          stopped=1
        fi
      done
      rm -f "$PIDFILE"
    fi
  fi

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

  read_pidfile

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
      if [ -n "$recorded" ] \
        && [ "$pid" = "$recorded" ] \
        && [ "$PIDFILE_MODE" = "$filter_mode" ]; then
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
  echo "Owner:  us       = matches the PID we started for this mode"
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
    echo "spire.sh: a pidfile exists for mode '$PIDFILE_MODE'." >&2
    echo "          that is the OTHER mode — leaving it alone." >&2
    exit 1
  fi
  any_alive=0
  for pid in "$PIDFILE_MCP" "$PIDFILE_API" "$PIDFILE_UI"; do
    pid_alive "$pid" && any_alive=1
  done
  if [ "$any_alive" = "1" ]; then
    echo "spire.sh: already running for mode $MODE." >&2
    echo "          use './spire.sh --stop' first." >&2
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

if [ "$TAIL_UI" -eq 1 ]; then
  tail -f "$LOG_DIR/ui.log" || true
fi