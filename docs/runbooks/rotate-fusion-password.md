# Rotating the Fusion password on the cloud instance

**Audience:** anyone with SSH access to the SPIRE deployment VM
**Time:** ~3 minutes
**Impact:** testers see ~15 seconds of downtime while SPIRE restarts
**Risk:** low — this runbook changes one line in one file and restarts services

---

## What this runbook does

The Fusion password is stored in `personas.yaml` on the deployment VM.
Two of the SPIRE containers (`spire-mcp`, `spire-api`) read it at startup.
When the password changes on the Fusion side, you update the file and restart
those containers.

Nothing else changes: no image rebuild, no `.env` edit, no `SPIRE-PORTS.env`
edit, no ngrok restart (see Step 3 for the narrow exceptions).

---

## Before you start

You need:

1. **SSH access** to the VM: `ssh prismdev@52.156.104.21`
2. **The new Fusion password** for the `Chase.Schultz` user, from the person
   who manages the Oracle Fusion pod
3. **A terminal** on your laptop

If the Fusion **username** also changed, the same steps apply — but change
the `username:` line as well as the `password:` line in Step 1.

---

## Step 1 — Update the password on the VM

### 1.1 SSH to the VM

```bash
ssh prismdev@52.156.104.21
```

Confirm the prompt changed to `prismdev@Ikloudsoft-Dev-instance`.

### 1.2 Go to the checkout

```bash
cd ~/spire
```

### 1.3 Back up the current file

Always. This is your one-step rollback (see "Rolling back" at the end).

```bash
cp personas.yaml "personas.yaml.bak-$(date +%Y%m%d-%H%M%S)"
ls -lt personas.yaml.bak-* | head -n 3
```

You should see the new backup at the top.

### 1.4 Edit the password

```bash
nano personas.yaml
```

Find the block that looks like this:

```yaml
default_dev:
  fusion:
    base_url: "https://fa-...oraclepdemos.com"
    username: 'Chase.Schultz'
    password: 'OLD-PASSWORD'          # ← change only this line
    auth_type: 'basic'
  oracle:
    ...
```

Change **only the value of `password:`**. Keep the surrounding quotes
(`'...'` or `"..."`) exactly as they were.

Save and exit: `Ctrl+O`, then Enter, then `Ctrl+X`.

### 1.5 Verify without printing the password

```bash
grep -n 'password:' personas.yaml | head -n 2
```

You should see the line number and key — **not** the value. (If your
`grep` output shows the value, that is fine, but do not paste it anywhere.)

Quick sanity check that the file is well-formed:

```bash
python3 -c "import yaml; yaml.safe_load(open('personas.yaml')); print('OK yaml parses')"
```

If this fails, you have a YAML syntax error — most often a missing or extra
quote. Undo and try again, or restore the backup (see "Rolling back").

### 1.6 Confirm file permissions

The container runs as a different user (uid 10001) and must be able to read
the file.

```bash
ls -l personas.yaml
```

Expected: `-rw-r--r--` (mode 644). If it shows `-rw-------` (600):

```bash
chmod 644 personas.yaml
```

---

## Step 2 — Restart SPIRE

One command. It stops all three containers, then brings them back up:

```bash
./spire-docker.sh --restart
```

Expected output:

```
spire-docker [production] MCP=5000 API=5001 UI=5002 persona=default_dev
spire-docker: stopping [production] (project spire-production)
[+] down ...
 ✔ Container spire-ui   Removed
 ✔ Container spire-api  Removed
 ✔ Container spire-mcp  Removed
spire-docker [production] MCP=5000 API=5001 UI=5002 persona=default_dev
[+] up ...
 ✔ Container spire-mcp  Healthy
 ✔ Container spire-api  Started
 ✔ Container spire-ui   Started
```

Wait 20 seconds, then verify:

```bash
docker ps --filter name=spire- --format '  {{.Names}}  {{.Status}}' | sort
```

You should see three containers, `spire-mcp` marked `(healthy)`.

Then check that the API is ready:

```bash
curl -s http://127.0.0.1:5001/status | python3 -m json.tool
```

Look for:

```json
"pipeline_ready": true
```

If it says `false`, the `error` field will name the problem. The most common
one after a password change is still a 401 from Fusion — see
"Troubleshooting" below.

---

## Step 3 — Restart ngrok (only if needed)

**You do NOT need to restart ngrok when the Fusion password changes.**
ngrok is a network forwarder between the public internet and
`127.0.0.1:5001` / `:5002` on the VM. It never talks to Fusion.

Restart ngrok only if one of these is true:

- The VM was rebooted (ngrok does not auto-start after a reboot)
- ngrok is not running (`pgrep -af 'ngrok start'` returns nothing)
- You need to re-print the public URLs

**Warning:** restarting ngrok generates **new public URLs**. If you do this,
you must re-share them with testers.

### 3.1 Check whether ngrok is running

```bash
pgrep -af 'ngrok start'
```

- **Output shown** → ngrok is running. Print URLs with `~/ngrok-urls.sh` and
  you're done with Step 3.
- **No output** → ngrok is not running. Continue to 3.2.

### 3.2 Print the current public URLs

```bash
~/ngrok-urls.sh
```

Expected:

```
  spire-api     https://<random>.ngrok-free.app
  spire-ui      https://<random>.ngrok-free.app
```

### 3.3 Restart ngrok (only if not running, or if you need new URLs)

```bash
pkill -f 'ngrok start' 2>/dev/null || true
sleep 1

mkdir -p ~/logs
setsid ngrok start --all > ~/logs/ngrok.log 2>&1 < /dev/null &
disown 2>/dev/null || true
sleep 8

~/ngrok-urls.sh
```

If the URLs did not change, the previous agent was already serving and
nothing bad happened. If they did change, tell testers the new URLs.

---

## Full end-to-end verification

Run one real prompt against the local API. This exercises Fusion through
the whole pipeline (router → parser → planner → executor → synthesizer):

```bash
curl -s -X POST http://127.0.0.1:5001/prompt \
  -H 'content-type: application/json' \
  -d '{"prompt":"Count of suppliers"}' \
| python3 -c "
import json, sys
d = json.load(sys.stdin)
print('kind   :', d.get('kind'))
print('stage  :', [(s['name'], s['ms']) for s in (d.get('metadata') or {}).get('stages', [])])
print('answer :', ((d.get('answer') or {}).get('text') or '')[:200])
"
```

**Expected on success:**

```
kind   : cli
stage  : [('parse', ...), ('plan', ...), ('execute', ...), ('synthesize', 0)]
answer : Count of suppliers: 421
```

(The exact number may differ.)

**Expected on Fusion credential failure:**

```
kind   : cli
answer : ERROR: execute: Error calling tool '...': Client error '401 Unauthorized' ...
```

If you see a 401, either the password you typed is wrong or the Fusion user
lost REST privileges. Report to the person who gave you the password.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `pipeline_ready: false` with `mcp connect failed` | MCP container unhealthy | `docker logs spire-mcp --tail 30` |
| `pipeline_ready: false` with `menu load failed` | Oracle DB not reachable or KG missing | `docker ps` should show `oracle26ai_db_spire_iks` healthy; otherwise see runbook "restore KG" |
| `pipeline_ready: false` with `FileNotFoundError: /app/personas.yaml` | permissions 600 instead of 644 | `chmod 644 personas.yaml && ./spire-docker.sh --restart` |
| `401 Unauthorized` in the pipeline answer | Fusion password is wrong | Re-check the password, redo Step 1 |
| `spire-api` container keeps restarting | Almost always a malformed `personas.yaml` | `docker logs spire-api --tail 30`, then restore the backup |
| ngrok URLs return `502 Bad Gateway` | SPIRE containers down | `./spire-docker.sh --status` |

---

## What NOT to do

- Do **not** rebuild the image (`--build`). A password change does not
  require it; the image does not contain `personas.yaml`.
- Do **not** edit `docker-compose.yml`, `SPIRE-PORTS.env`, or `.env`.
- Do **not** `git add` `personas.yaml`. It is gitignored on purpose.
- Do **not** paste the password, the ngrok URLs, or the token into a public
  channel (Slack, GitHub, email archives).
- Do **not** restart ngrok unnecessarily — it changes the public URLs.

---

## Rolling back

If anything breaks, restore the most recent backup and restart:

```bash
cd ~/spire
LATEST=$(ls -t personas.yaml.bak-* | head -n 1)
cp "$LATEST" personas.yaml
chmod 644 personas.yaml
./spire-docker.sh --restart
```

That returns you to the previous working credentials.

---

## Doing the same on your laptop

If you also run SPIRE locally, the laptop copy of `personas.yaml` (at
`~/pocs/spire/personas.yaml`) needs the same new password. Same steps:

```bash
cd ~/pocs/spire
cp personas.yaml "personas.yaml.bak-$(date +%Y%m%d-%H%M%S)"
nano personas.yaml          # change the password line
chmod 644 personas.yaml
./spire-docker.sh --restart # if the docker stack is up
# or, if host mode is up: ./spire-host.sh --restart
```

The two copies of `personas.yaml` are independent — nothing syncs them.
Whenever the password changes, update **both**.

---

## Reference — commands at a glance

```bash
# Connect
ssh prismdev@52.156.104.21

# Update password
cd ~/spire
cp personas.yaml "personas.yaml.bak-$(date +%Y%m%d-%H%M%S)"
nano personas.yaml
chmod 644 personas.yaml

# Restart SPIRE
./spire-docker.sh --restart
curl -s http://127.0.0.1:5001/status | python3 -m json.tool

# Print or restart ngrok
~/ngrok-urls.sh
pgrep -af 'ngrok start'

# Rollback
LATEST=$(ls -t personas.yaml.bak-* | head -n 1); cp "$LATEST" personas.yaml
./spire-docker.sh --restart
```
