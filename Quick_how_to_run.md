# Spire — Quick Reference Guide

## Setup

```bash
source ~/venv/spire/bin/activate
pip install -r requirements.txt
pip install -e .
cp personas.example.yaml personas.yaml
```

```bash
docker pull container-registry.oracle.com/database/free:latest
mkdir -p ~/oracle_oradata
docker run -d \
  --name oracle26ai_db_spire_iks \
  --restart unless-stopped \
  -p 1521:1521 \
  -e ORACLE_PWD='Abcd1234' \
  -v ~/oracle_oradata:/opt/oracle/oradata \
  container-registry.oracle.com/database/free:latest
```

```bash
docker exec -i oracle26ai_db_spire_iks sqlplus sys/Abcd1234@localhost:1521/FREEPDB1 as sysdba <<'EOF'
CREATE USER spire IDENTIFIED BY "jnjnuh";
GRANT CONNECT, RESOURCE, CREATE VIEW, UNLIMITED TABLESPACE TO spire;
GRANT DB_DEVELOPER_ROLE TO spire;
EXIT;
EOF
```

```bash
export GEMINI_API_KEY="..."
```

## Start Stack

```bash
./spire-host.sh --start dev
./spire-host.sh --status
./spire-host.sh --stop dev
./spire-host.sh --restart dev
```

```bash
./spire-docker.sh --start dev
./spire-docker.sh --status
./spire-docker.sh --stop dev
./spire-docker.sh --restart dev
./spire-docker.sh --build
./spire-docker.sh --logs api
```

## Build Knowledge Graph

```bash
python scripts/rebuild_kg.py
python scripts/print_kg.py
python scripts/print_kg.py --counts-only
```

## Run Prompts (CLI)

```bash
python scripts/promptkit.py --run --prompt "List all suppliers in India"
python scripts/promptkit.py --run --prompt "Count of suppliers"
python scripts/promptkit.py --run --prompt "Suppliers with their addresses"
python scripts/promptkit.py --run --prompt "Show PO 2144 and its lines"
python scripts/promptkit.py --run --prompt "Show me invoices for supplier 1252"
python scripts/promptkit.py --run --prompt "invoices for supplier 1252 over 10000"
python scripts/promptkit.py --run --prompt "Get the AR invoice with CustomerTransactionId 300000248096352"
python scripts/promptkit.py --run --prompt "Show me AR invoices for customer ABC Corporation Americas"
python scripts/promptkit.py --run --prompt "Top 5 suppliers by spend this year"
python scripts/promptkit.py --run --prompt "Which suppliers have open purchase orders?"
python scripts/promptkit.py --run --prompt "show me contract renewals due next quarter"
```

## Run Prompts (Batch)

```bash
python scripts/promptkit.py --run --prompt-file prompts/supplier/supplier_smoke.txt
python scripts/promptkit.py --run --prompt-file prompts/dipstick/dipstick_smoke.txt prompts/supplier/supplier_smoke.txt
python scripts/promptkit.py --run --manifest scripts/manifests/promptkit_sets.yaml
python scripts/promptkit.py --run --manifest scripts/manifests/promptkit_sets.yaml --outdir results/tonight
python scripts/promptkit_overnight.py --skip-run
nohup python scripts/promptkit_overnight.py > promptkit_overnight_$(date +%Y%m%d).log 2>&1 &
```

## Diagnostic Flags

```bash
python scripts/promptkit.py --run --prompt "..." --show-all
python scripts/promptkit.py --run --prompt "..." --show-parser
python scripts/promptkit.py --run --prompt "..." --show-planner
python scripts/promptkit.py --run --prompt "..." --show-raw-output
python scripts/promptkit.py --run --prompt "..." --show-synthesizer
python scripts/promptkit.py --run --prompt "..." --show-tokens
python scripts/promptkit.py --run --prompt "..." --show-timings
python scripts/promptkit.py --run --prompt "..." --show-all --no-show-tokens
python scripts/promptkit.py --run --prompt "..." 2>/dev/null
```

## API / UI

```bash
curl -s http://127.0.0.1:4002/status
curl -s http://127.0.0.1:5001/status
curl -s http://127.0.0.1:5001/status | jq .persona
curl -s http://127.0.0.1:5001/status | jq .pipeline_ready
```

```bash
curl -s -X POST http://localhost:4002/prompt \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"List active suppliers"}'
```

## Tests

```bash
python -m pytest -q
python -m pytest -q -m integration
```

## Credentials & Restart

```bash
cp .env.example .env
scp .env user@cloud-vm:~/spire/.env
scp personas.yaml user@cloud-vm:~/spire/personas.yaml
./spire-docker.sh --restart
python scripts/rebuild_kg.py
```