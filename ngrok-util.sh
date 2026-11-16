#!/usr/bin/env bash
# Control + status for the ngrok tunnels defined in the snap config.
# Location: ~/spire/ngrok-util.sh
#
# Usage:
#   ngrok-util.sh status      # print live tunnel URLs (default)
#   ngrok-util.sh start       # start all tunnels in the config
#   ngrok-util.sh stop        # stop the ngrok agent started by this script
#   ngrok-util.sh restart     # stop then start
#   ngrok-util.sh help        # show this help
#
# Config path used: ~/snap/ngrok/current/.config/ngrok/ngrok.yml (symlinked to common/).
set -euo pipefail

PIDFILE="$HOME/.ngrok-agent.pid"
LOGFILE="$HOME/ngrok-agent.log"
ADMIN_URL="http://127.0.0.1:4040/api/tunnels"
CONFIG="$HOME/snap/ngrok/current/.config/ngrok/ngrok.yml"
COMMON_CONFIG="$HOME/snap/ngrok/common/ngrok.yml"
SCRIPT_PATH="$HOME/spire/ngrok-util.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") {status|start|stop|restart|help}

Commands:
  status     Show whether the ngrok agent is running and print live
             tunnel URLs (name + public_url). This is the default if no
             command is given. Exits 1 if the agent is not running.
  start      Start all tunnels defined in the ngrok config in the
             background (nohup), record the PID, and wait for the admin
             API before printing the URLs. Idempotent: if already running,
             just prints the URLs.
  stop       Stop the ngrok agent started by this script (graceful, then
             SIGKILL after ~2s). Also cleans up any stragglers matching
             'ngrok start'. Prints "stopped" or "not running".
  restart    Equivalent to: stop; start
  help       Show this help. Also: -h, --help

Files:
  Script      $SCRIPT_PATH
  PID file    $PIDFILE
  Log file    $LOGFILE   (tail -f to follow)
  Config      $CONFIG
              -> symlink to $COMMON_CONFIG

Notes:
  - No systemd / no auto-start on boot. Add
        @reboot $SCRIPT_PATH start
    to 'crontab -e' if you want start-on-boot without systemd.
  - If a 'snap refresh ngrok' breaks the config symlink, re-create it:
        ln -sfn $COMMON_CONFIG $CONFIG

Recovery — if the config is missing:

  1) Create $COMMON_CONFIG with this structure (never commit a real token):

       version: "3"
       agent:
           authtoken: <PASTE_TOKEN_FROM_DASHBOARD>

       tunnels:
         spire-api:
           proto: http
           addr: 5001
         spire-ui:
           proto: http
           addr: 5002

  2) Paste the authtoken from https://dashboard.ngrok.com/get-started/your-authtoken
  3) chmod 600 $COMMON_CONFIG
  4) ln -sfn $COMMON_CONFIG $CONFIG
  5) ngrok config check
EOF
}

config_present() { [ -e "$CONFIG" ] && [ -r "$CONFIG" ]; }

config_missing_msg() {
  cat >&2 <<EOF
ERROR: ngrok config not found or unreadable:
       $CONFIG

Fix options:
  a) If you have a good copy elsewhere:
       mkdir -p \$HOME/snap/ngrok/common
       cp /path/to/ngrok.yml $COMMON_CONFIG
       chmod 600 $COMMON_CONFIG
       ln -sfn $COMMON_CONFIG $CONFIG

  b) To recreate from scratch, run:  $(basename "$0") help
     and follow the "Recovery" section.
EOF
}

config_is_detached() {
  # True if $CONFIG exists but is not the symlink to $COMMON_CONFIG.
  [ -e "$CONFIG" ] || return 1
  local resolved link
  resolved=$(readlink -f "$CONFIG" 2>/dev/null || true)
  link=$(readlink "$CONFIG" 2>/dev/null || true)
  # If it's a symlink pointing at COMMON, we're fine.
  if [ "$link" = "$COMMON_CONFIG" ]; then
    return 1
  fi
  return 0
}

preflight_start() {
  if ! config_present; then
    config_missing_msg
    return 1
  fi
  if config_is_detached; then
    echo "WARNING: $CONFIG is not linked to $COMMON_CONFIG" >&2
    echo "         It may be a revision-local config that a 'snap refresh'" >&2
    echo "         will overwrite. Re-link with:" >&2
    echo "           ln -sfn $COMMON_CONFIG $CONFIG" >&2
  fi
  if ! ngrok config check >/dev/null 2>&1; then
    echo "WARNING: 'ngrok config check' failed; ngrok may not start cleanly." >&2
    echo "         Run 'ngrok config check' for details." >&2
  fi
  return 0
}

print_urls() {
  local resp
  resp=$(curl -s -m 5 "$ADMIN_URL" || true)
  if [ -z "$resp" ]; then
    echo "ngrok admin API unreachable — agent may not be running" >&2
    return 1
  fi
  echo "$resp" | python3 -c '
import json, sys
d = json.load(sys.stdin)
tunnels = d.get("tunnels", [])
if not tunnels:
    print("  (no tunnels)")
for t in tunnels:
    print("  %-12s  %s" % (t["name"], t["public_url"]))
'
}

is_running() {
  if [ -f "$PIDFILE" ]; then
    local pid
    pid=$(cat "$PIDFILE" 2>/dev/null || true)
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  pgrep -f 'ngrok start' >/dev/null 2>&1
}

do_start() {
  preflight_start || return 1
  if is_running; then
    echo "ngrok agent already running:" >&2
    pgrep -af 'ngrok start' >&2 || true
    print_urls
    return 0
  fi
  echo "starting ngrok agent (all config tunnels)..."
  nohup ngrok start --all --log=stdout >"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"
  for _ in $(seq 1 20); do
    if curl -s -m 1 "$ADMIN_URL" >/dev/null 2>&1; then
      echo "started (pid $(cat "$PIDFILE"))"
      print_urls
      return 0
    fi
    sleep 0.5
  done
  echo "warning: agent started (pid $(cat "$PIDFILE")) but admin API not yet reachable; see $LOGFILE" >&2
  return 1
}

do_stop() {
  local stopped=0
  if [ -f "$PIDFILE" ]; then
    local pid
    pid=$(cat "$PIDFILE" 2>/dev/null || true)
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      for _ in $(seq 1 10); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.2
      done
      kill -9 "$pid" 2>/dev/null || true
      stopped=1
    fi
    rm -f "$PIDFILE"
  fi
  if pgrep -f 'ngrok start' >/dev/null 2>&1; then
    pkill -f 'ngrok start' || true
    stopped=1
  fi
  if [ "$stopped" -eq 1 ]; then
    echo "ngrok agent stopped"
  else
    echo "ngrok agent not running"
  fi
}

do_status() {
  if ! config_present; then
    echo "ngrok config: MISSING ($CONFIG)"
    echo "  run '$(basename "$0") help' for recovery steps" >&2
  elif config_is_detached; then
    echo "ngrok config: present but NOT linked to $COMMON_CONFIG"
    echo "  re-link: ln -sfn $COMMON_CONFIG $CONFIG"
  fi

  if is_running; then
    echo "ngrok agent: running"
    pgrep -af 'ngrok start' || true
    print_urls
  else
    echo "ngrok agent: not running"
    return 1
  fi
}

cmd="${1:-status}"
case "$cmd" in
  status)         do_status  ;;
  start)          do_start   ;;
  stop)           do_stop    ;;
  restart)        do_stop; do_start ;;
  help|-h|--help) usage      ;;
  *) echo "unknown command: $cmd" >&2; echo >&2; usage >&2; exit 2 ;;
esac