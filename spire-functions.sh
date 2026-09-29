#!/usr/bin/env bash
#
# spire-functions.sh -- shell entry points for SPIRE.
#
# Source this file from your shell rc (~/.bashrc, ~/.zshrc, etc.):
#
#     source /path/to/your/spire/clone/spire-functions.sh
#
# Then:
#
#     spired     activate the dev venv, cd into the dev clone,
#                export SPIRE_MCP_URL / SPIRE_API_URL, print ports.
#
#     spirep     same, but for the production clone.
#
# Paths are overridable. Export any of these before sourcing:
#
#     SPIRE_DEV_ROOT   dev clone root (default: $HOME/pocs/spire)
#     SPIRE_PROD_ROOT  prod clone root (default: $HOME/pocs/spire-runtime)
#     SPIRE_DEV_VENV   dev venv activate script
#                      (default: $HOME/venv/spire/bin/activate)
#     SPIRE_PROD_VENV  prod venv activate script
#                      (default: $HOME/venv/spire-runtime/bin/activate)
#
# The functions read SPIRE-PORTS.env from the tree they cd into, so
# ports come from that file (single source of truth) and never need
# duplicating here.

SPIRE_DEV_ROOT="${SPIRE_DEV_ROOT:-$HOME/pocs/spire}"
SPIRE_PROD_ROOT="${SPIRE_PROD_ROOT:-$HOME/pocs/spire-runtime}"
SPIRE_DEV_VENV="${SPIRE_DEV_VENV:-$HOME/venv/spire/bin/activate}"
SPIRE_PROD_VENV="${SPIRE_PROD_VENV:-$HOME/venv/spire-runtime/bin/activate}"

function spired(){
    source "$SPIRE_DEV_VENV" 2>/dev/null || true
    cd "$SPIRE_DEV_ROOT" || return
    source SPIRE-PORTS.env
    export SPIRE_MCP_URL="http://127.0.0.1:${SPIRE_DEV_MCP_PORT}/mcp/"
    export SPIRE_API_URL="http://127.0.0.1:${SPIRE_DEV_API_PORT}"
    echo "spire dev: MCP ${SPIRE_DEV_MCP_PORT}  API ${SPIRE_DEV_API_PORT}  UI ${SPIRE_DEV_UI_PORT}"
}

function spirep(){
    source "$SPIRE_PROD_VENV" 2>/dev/null || true
    cd "$SPIRE_PROD_ROOT" || return
    source SPIRE-PORTS.env
    export SPIRE_MCP_URL="http://127.0.0.1:${SPIRE_RUNTIME_MCP_PORT}/mcp/"
    export SPIRE_API_URL="http://127.0.0.1:${SPIRE_RUNTIME_API_PORT}"
    echo "spire prod: MCP ${SPIRE_RUNTIME_MCP_PORT}  API ${SPIRE_RUNTIME_API_PORT}  UI ${SPIRE_RUNTIME_UI_PORT}"
}
