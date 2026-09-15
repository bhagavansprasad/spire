#!/usr/bin/env bash
#
# run-all.sh — start MCP server, API server, and Streamlit UI together.
#
#   ./run-all.sh            start all three; Ctrl-C stops all three
#   ./run-all.sh --tail     same, then tail the UI log in the foreground
#   LOG_DIR=tmp/logs ./run-all.sh    log to a different directory
#
# Ports: reads from .spire-dev.env if that file exists in this
# directory; otherwise uses defaults 3333 / 8000 / 8888. The dev tree
# has .spire-dev.env (4444 / 9000 / 9999); the runtime tree does not,
# so the two instances never collide.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

if [ -f "$REPO_ROOT/.spire-dev.env" ]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.spire-dev.env"
fi

MCP_PORT="${SPIRE_MCP_PORT:-3333}"
API_PORT="${SPIRE_API_PORT:-8000}"
UI_PORT="${SPIRE_UI_PORT:-8888}"

LOG_DIR="${LOG_DIR:-logs}"
TAIL_UI=0
for arg in "$@"; do
  case "$arg" in
    --tail) TAIL_UI=1 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR"

PIDS=()
CLEANED=0

cleanup() {
  if [ "$CLEANED" -eq 1 ]; then
    return
  fi
  CLEANED=1

  echo ""
  echo "Stopping services..."
  for pid in "${PIDS[@]:-}"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  sleep 1
  for pid in "${PIDS[@]:-}"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
  echo "Stopped."
}
trap cleanup EXIT INT TERM

port_busy() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

preflight_warn() {
  local port="$1" name="$2"
  if port_busy "$port"; then
    echo "  [!] port $port is already in use; $name may fail to start."
  fi
}

echo "Log directory: $LOG_DIR"
echo "Ports:  MCP $MCP_PORT   API $API_PORT   UI $UI_PORT"
preflight_warn "$MCP_PORT" "MCP server"
preflight_warn "$API_PORT" "API server"
preflight_warn "$UI_PORT" "Streamlit UI"

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
echo "All three started. Open the UI at http://localhost:$UI_PORT"
echo ""
echo "Tail logs (any of):"
echo "  tail -f $LOG_DIR/mcp.log"
echo "  tail -f $LOG_DIR/api.log"
echo "  tail -f $LOG_DIR/ui.log"
echo ""
echo "Press Ctrl-C to stop all three."
echo ""

if [ "$TAIL_UI" -eq 1 ]; then
  tail -f "$LOG_DIR/ui.log" || true
else
  while :; do
    sleep 3600 &
    wait $! 2>/dev/null || true
  done
fi