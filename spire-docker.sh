#!/usr/bin/env bash
#
# spire-docker.sh — manage the SPIRE Docker stack. Mirrors spire-host.sh.
#
# ACTIONS (default target: production)
#   ./spire-docker.sh --start   [dev|production]        start (up -d)
#   ./spire-docker.sh --stop    [dev|production]        stop  (down)
#   ./spire-docker.sh --restart [dev|production]        down, then up -d
#   ./spire-docker.sh --status  [dev|production]        show state; no target = both
#   ./spire-docker.sh --logs    [dev|production] [svc]  tail -f
#   ./spire-docker.sh --build                           rebuild the shared image
#   ./spire-docker.sh --help
#
# PASSTHROUGH (raw docker compose args)
#   ./spire-docker.sh [dev|production] <args>    e.g. exec api bash
#   ./spire-docker.sh <args>                     production default
#
# NOTES
#   Container names (spire-mcp/api/ui) are shared between modes.
#   Run only one stack at a time.
#   --stop with no target stops production; use '--stop dev' for dev.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

usage() {
  cat <<'USAGE'
Usage: ./spire-docker.sh <action> [mode] [args]

Actions:
  --start    [dev|production]        start the stack (default: production)
  --stop     [dev|production]        stop the stack  (default: production)
  --restart  [dev|production]        down, then up -d
  --status   [dev|production]        show state (default: both)
  --logs     [dev|production] [svc]  tail logs (default: production)
  --build                            rebuild the shared image
  --help

Passthrough (raw docker compose args):
  ./spire-docker.sh [dev|production] <args>
  ./spire-docker.sh <args>                       production default

Modes:
  production  ports 5000/5001/5002, persona default_dev  (default)
  dev         ports 4001/4002/4003, persona default_dev

Note: container names spire-mcp/api/ui are shared.
      Run only one stack at a time.
USAGE
}

load_mode() {
  local mode="$1"
  # shellcheck disable=SC1091
  source ./SPIRE-PORTS.env
  case "$mode" in
    dev)
      export SPIRE_MCP_PORT="$SPIRE_DEV_MCP_PORT"
      export SPIRE_API_PORT="$SPIRE_DEV_API_PORT"
      export SPIRE_UI_PORT="$SPIRE_DEV_UI_PORT"
      export SPIRE_PERSONA="${SPIRE_PERSONA:-default_dev}"
      FILES=(-f docker-compose.yml -f docker-compose.dev.yml)
      ;;
    production)
      export SPIRE_MCP_PORT="$SPIRE_PRODUCTION_MCP_PORT"
      export SPIRE_API_PORT="$SPIRE_PRODUCTION_API_PORT"
      export SPIRE_UI_PORT="$SPIRE_PRODUCTION_UI_PORT"
      export SPIRE_PERSONA="${SPIRE_PERSONA:-default_dev}"
      FILES=(-f docker-compose.yml)
      ;;
    *)
      echo "spire-docker: unknown mode '$mode'" >&2
      exit 2
      ;;
  esac
  export SPIRE_MCP_MODE="$mode"
  PROJECT="spire-$mode"
}

dc() {
  local mode="$1"; shift
  load_mode "$mode"
  docker compose -p "$PROJECT" "${FILES[@]}" "$@"
}

action_start() {
  local mode="$1"
  load_mode "$mode"
  echo "spire-docker [$mode] MCP=$SPIRE_MCP_PORT API=$SPIRE_API_PORT UI=$SPIRE_UI_PORT persona=$SPIRE_PERSONA"
  docker compose -p "$PROJECT" "${FILES[@]}" up -d
}

action_stop() {
  local mode="$1"
  load_mode "$mode"
  echo "spire-docker: stopping [$mode] (project $PROJECT)"
  docker compose -p "$PROJECT" "${FILES[@]}" down
}

action_restart() {
  local mode="$1"
  action_stop "$mode"
  sleep 2
  action_start "$mode"
}

show_status_for() {
  local mode="$1"
  load_mode "$mode"
  echo "spire-docker status  (mode: $mode, project $PROJECT)"
  echo "───────────────────────────────────────────────"
  printf '%-10s %-9s %-9s %s\n' "Name" "State" "Health" "HostPorts"
  local svc name state health ports
  for svc in mcp api ui; do
    name="spire-$svc"
    state=$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo missing)
    health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' "$name" 2>/dev/null || echo -)
    ports=$(docker ps --filter "name=^${name}$" --format '{{.Ports}}' 2>/dev/null || true)
    [ -n "$ports" ] || ports="-"
    printf '%-10s %-9s %-9s %s\n' "$name" "$state" "$health" "$ports"
  done
  echo "  MCP=$SPIRE_MCP_PORT  API=$SPIRE_API_PORT  UI=$SPIRE_UI_PORT  persona=$SPIRE_PERSONA"
  echo
}

action_status() {
  local mode="${1:-}"
  if [ -z "$mode" ]; then
    show_status_for production
    show_status_for dev
  else
    show_status_for "$mode"
  fi
}

action_logs() {
  local mode="$1"; shift || true
  dc "$mode" logs -f "$@"
}

# ── dispatch ─────────────────────────────────────────────────────────

[ "$#" -ge 1 ] || { usage; exit 0; }

ACTION=""
MODE=""
ARGS=()

case "$1" in
  --start|--stop|--restart|--status|--logs)
    ACTION="$1"; shift
    if [ "${1:-}" = "dev" ] || [ "${1:-}" = "production" ]; then
      MODE="$1"; shift
    fi
    ARGS=("$@")
    ;;
  --build)
    ACTION="$1"; shift ;;
  --help|-h)
    usage; exit 0 ;;
  dev|production)
    MODE="$1"; shift
    ACTION="passthrough"; ARGS=("$@") ;;
  *)
    ACTION="passthrough"; ARGS=("$@") ;;
esac

case "$ACTION" in
  --start)   action_start   "${MODE:-production}" ;;
  --stop)    action_stop    "${MODE:-production}" ;;
  --restart) action_restart "${MODE:-production}" ;;
  --status)  action_status  "$MODE" ;;
  --logs)    action_logs    "${MODE:-production}" "${ARGS[@]}" ;;
  --build)
    load_mode production
    docker compose -p "$PROJECT" "${FILES[@]}" build ;;
  passthrough)
    dc "${MODE:-production}" "${ARGS[@]}" ;;
esac
