#!/usr/bin/env bash
fastmcp run src/spire/mcp_server/server.py -t http --host 127.0.0.1 --port 3333 --reload --reload-dir src/spire
