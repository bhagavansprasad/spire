#!/usr/bin/env bash
#
# run-server.sh — start the SPIRE MCP server.
#
# The port comes from SPIRE_MCP_PORT, set by run-all.sh from SPIRE-PORTS.env.
# Refuses to start without it — no silent default. A forgotten env var fails
# loudly instead of quietly colliding on a stale port.

set -euo pipefail

if [ -z "${SPIRE_MCP_PORT:-}" ]; then
  echo "run-server.sh: SPIRE_MCP_PORT is not set." >&2
  echo "  Start via ./run-all.sh --dev  or  ./run-all.sh --runtime," >&2
  echo "  or export SPIRE_MCP_PORT yourself." >&2
  exit 2
fi

exec fastmcp run src/spire/mcp_server/server.py \
  -t http \
  --host 127.0.0.1 \
  --port "$SPIRE_MCP_PORT" \
  --reload \
  --reload-dir src/spire