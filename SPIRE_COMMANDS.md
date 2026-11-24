# SPIRE COMMANDS

## 1. Environment

| Command | What it does |
|---|---|
| `spired` | Goes to SPIRE folder and activates SPIRE environment |

## 2. Start / Stop SPIRE

| Command | What it does |
|---|---|
| `./spire.sh --start dev` | Starts development services |
| `./spire.sh --status` | Checks SPIRE service status |
| `./spire.sh --stop dev` | Stops development services |
| `./spire.sh --restart dev` | Restarts development services |
| `./spire.sh --help` | Shows available commands |

## 3. Run SPIRE

| Command | What it does |
|---|---|
| `python scripts/promptkit.py --run --prompt "your question"` | Runs SPIRE with your question |

Example:

```bash
python scripts/promptkit.py --run --prompt "Show me all suppliers"
```

## 4. Knowledge Graph

| Command | What it does |
|---|---|
| `python scripts/print_kg.py --table kg_entity` | Displays KG entities |
| `python scripts/print_kg.py --table kg_relationship` | Displays KG relationships |

## 5. Oracle 26ai – Docker

| Command | What it does |
|---|---|
| `docker start oracle26ai_db` | Starts Oracle container |
| `docker stop oracle26ai_db` | Stops Oracle container |
| `docker restart oracle26ai_db` | Restarts Oracle container |
| `docker ps` | Shows running containers |
| `docker ps -a` | Shows all containers |
| `docker logs -f oracle26ai_db` | Shows live Oracle logs |
| `docker port oracle26ai_db` | Shows Oracle port mapping |

## 6. Oracle SQL*Plus

```bash
docker exec -it oracle26ai_db bash
sqlplus spire@//localhost:1521/FREEPDB1
```

| SQL command | What it does |
|---|---|
| `SELECT USER FROM DUAL;` | Shows connected user |
| `SELECT name FROM v$database;` | Shows database name |
| `SHOW CON_NAME;` | Shows current PDB |
| `SELECT table_name FROM user_tables;` | Lists user's tables |

## 7. Help

| Command | What it does |
|---|---|
| `./spire.sh --help` | SPIRE command help |
| `docker --help` | Docker command help |
| `python scripts/promptkit.py --help` | Prompt script help |
| `python scripts/print_kg.py --help` | KG script help |