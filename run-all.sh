#!/usr/bin/env bash
#
# run-all.sh — start MCP server, API server, and Streamlit UI together.
#
#   ./run-all.sh            start all three; Ctrl-C stops all three
#   ./run-all.sh --tail     same, then tail the UI log in the foreground
#   LOG_DIR=tmp/logs ./run-all.sh    log to a different directory
#
# Each service writes its own log under $LOG_DIR (default: logs/):
#   logs/mcp.log    MCP server       :3333
#   logs/api.log    FastAPI backend  :8000
#   logs/ui.log     Streamlit UI     :8888
#
# Startup order: MCP, API, UI. The API tolerates the MCP server being
# down (pipeline_ready=false), and the UI tolerates the API being down
# (red "Not connected" pill). Starting in order avoids spurious
# connection warnings on cold start.
#
# Ctrl-C triggers a clean shutdown of all three. If the script is
# killed with -9, orphan children remain; clean up with:
#   pkill -f spire.mcp_server.server
#   pkill -f spire.api.server
#   pkill -f spire-ui

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

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
  # Guard: the trap is installed on both INT/TERM and EXIT, so this
  # function can be reached twice. Run the work once.
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
preflight_warn 3333 "MCP server"
preflight_warn 8000 "API server"
preflight_warn 8888 "Streamlit UI"

bash run-server.sh > "$LOG_DIR/mcp.log" 2>&1 &
PIDS+=("$!")
echo "MCP   pid=${PIDS[-1]}   http://127.0.0.1:3333     log: $LOG_DIR/mcp.log"
sleep 2

python -m spire.api.server > "$LOG_DIR/api.log" 2>&1 &
PIDS+=("$!")
echo "API   pid=${PIDS[-1]}   http://localhost:8000     log: $LOG_DIR/api.log"
sleep 1

spire-ui > "$LOG_DIR/ui.log" 2>&1 &
PIDS+=("$!")
echo "UI    pid=${PIDS[-1]}   http://localhost:8888     log: $LOG_DIR/ui.log"

echo ""
echo "All three started. Open the UI at http://localhost:8888"
echo ""
echo "Tail logs (any of):"
echo "  tail -f $LOG_DIR/mcp.log"
echo "  tail -f $LOG_DIR/api.log"
echo "  tail -f $LOG_DIR/ui.log"
echo ""
echo "Press Ctrl-C to stop all three."
echo ""

if [ "$TAIL_UI" -eq 1 ]; then
  # tail -f keeps the shell alive until Ctrl-C; on exit the trap fires.
  tail -f "$LOG_DIR/ui.log" || true
else
  # Block until Ctrl-C. Ignore child deaths — a crashed service should
  # NOT tear down the other two. The user can check its log.
  # wait -n would exit as soon as any child dies, which we do not want.
  while :; do
    sleep 3600 &
    wait $! 2>/dev/null || true
  done
fi