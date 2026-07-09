# Spire V1.2 — After You Pull

For people who already have Spire set up. This covers only what to do
after pulling the latest code, and which prompts to run. (First-time
setup — venv, DB user, credentials, LLM keys — is in the full setup guide;
you don't need it again.)

---

## 1. Pull and refresh

```bash
git checkout master
git pull
pip install -e .            # only if dependencies changed; harmless otherwise
```

**Rebuild the knowledge graph** — the KG changed in V1.2, so rebuild it
from scratch and confirm the counts:

```bash
python scripts/rebuild_kg.py
python scripts/print_kg.py --counts-only
```

You should see all tables report `ok`.

---

## 2. Run

Two terminals. Set the Fusion credentials first (your own values):

```bash
export IKS_FUSION_BASE_URL="https://<your-pod>.oraclepdemos.com"
export IKS_FUSION_USERNAME="<fusion-user>"
export IKS_FUSION_PASSWORD="<fusion-pass>"
```

```bash
# Terminal 1 — MCP server (keep running)
python -m spire.mcp_server.server

# Terminal 2 — a single prompt
python scripts/run_graph.py --prompt "List active suppliers"
```

Exit codes: `0` ok · `2` node error · `4` refusal (out of scope).

---

## 3. Run the V1.2 review prompts

A ready set is in `scripts/spire_v1.2_review_prompts.txt`. Run them one at
a time, or as a batch:

```bash
# One at a time
python scripts/run_graph.py --prompt "Woman owned suppliers"

# Or the whole set through the batch runner
python scripts/run_prompt_set.py --prompt-file scripts/spire_v1.2_review_prompts.txt
```

For each prompt, please note (a) whether the result is correct and
(b) which columns you expect in the output.

---

## 4. What to try

**Suppliers by attribute**
```
List active suppliers
US suppliers
Suppliers in the UK
Prospective suppliers
Suppliers created between Jan and Mar 2025
```

**Suppliers by related record**
```
Suppliers with a site in the France business unit
Woman owned suppliers
Suppliers that are small business
Suppliers with open purchase orders
Suppliers with invoices over 10000
```

**Counts, ranking, invoices, addresses**
```
How many suppliers do we have
Top 10 suppliers by spend in 2022
Invoices for supplier 1252
Addresses for supplier 1252
```

**Specific output columns** (please confirm expected columns)
```
Show only supplier name and status for active suppliers
Supplier number and country for US suppliers
Invoice number, amount, and date for supplier 1252
```

**Try your own** — this list is just a starting point. Please also run
prompts the way you would actually ask them, including rephrasings and
combinations not shown here. Where a prompt doesn't work as expected, note
the wording you used and the columns you expected — those are the most
useful review comments.

---

## Troubleshooting (quick)

- **`ModuleNotFoundError: No module named 'spire'`** — run `pip install -e .`
- **`print_kg` shows a count mismatch** — re-run `python scripts/rebuild_kg.py`
- **MCP connection error** — the server isn't running in Terminal 1
- **`401` from the pod** — Fusion credentials wrong or the weekly password rotated
- **`429 RESOURCE_EXHAUSTED` (Gemini)** — model quota is zero; switch with `SPIRE_LLM_PROVIDER`
