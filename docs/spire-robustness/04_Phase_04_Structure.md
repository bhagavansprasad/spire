# SPIRE — Phase 4 — Structure

**Session log and design for Phase 4** (Doc A §10).
**Index:** `00_Doc_B_Index.md` in this folder.
**Newest session at the top.** Append-only within the phase.

---

### S001 — 2026-09-15 — Phase 4d (UI + API), built early

**Phase:** Phase 4d — Structure — UI and API layer (Doc A §10.3.5)
**Branch:** `phase-4d-ui-api` (merged to `master`)
**Session goal:** Stand up a working Streamlit UI + FastAPI backend so a tester can drive SPIRE from a browser.
**Outcome:** completed — API, UI, tests, byte-equality evidence all verified; merged

**Deviation from Doc A ordering.** Phase 4d was built before Phases 1–3. Rationale: the API contract in §10.3.5 already anticipates Phase 2's `partial` kind (§8.3.7) and Phase 3g's `kg_version`. The contract is forward-compatible; the UI is a client of the contract, not of the pipeline internals. Building it now unblocks testing. **Recorded in Doc A §10.7.**

**Detailed design:** Doc B §5.1.

**Inputs received this session:**
- `graph_kg` context bundle — pipeline shape, executor contract, KG schema.
- `synthesizer` context bundle — response models, truncation narration, local-summary rules.

**Outputs:**
- §5.1 written.
- WI-S001-01 through WI-S001-07 all verified. Branch merged to `master`.
- Doc A §6 Phase Index updated (4d → Complete); §10.7 Status updated; §15 Session Log pointer added.

---

#### Work items

##### WI-S001-01 — Capture golden prompts (Step 0)

| Field | Value |
|---|---|
| Type | test |
| Test kind(s) | byte-equality |
| Doc A reference | §7.3.3 G, §10.5 |
| Bug ID | — |
| Investigation ID | — |
| State | verified |

**Objective.** Save the three golden outputs before any code changes, so §10.5's acceptance criterion has an anchor.

**Commands.**

~~~bash
mkdir -p docs/audit/golden

python scripts/promptkit.py --run --prompt "Count of suppliers" \
  > docs/audit/golden/count_suppliers.txt 2>&1

python scripts/promptkit.py --run --prompt "Show PO 2144 and its lines" \
  > docs/audit/golden/po_2144_and_lines.txt 2>&1

python scripts/promptkit.py --run --prompt "Which suppliers have open purchase orders?" \
  > docs/audit/golden/suppliers_with_open_pos.txt 2>&1
~~~

**Outputs.** Files at `docs/audit/golden/`. Key lines: `There are 431 suppliers.` (later observed as 433, 434 — pod drift, see WI-S001-04); PO 162352 / EIP Inc / 2 lines; "Showing 25 of 431 suppliers. These 25 suppliers have 67 open purchase orders between them."

**Verification.** Anchor for §10.5's byte-equality criterion. Files committed at Step 10.

**Observations.**

- **`stage=classify` appears twice per prompt in every file.** Different token counts on one file. Worth confirming in Phase 5 whether double LLM call or duplicated log line.
- **Parse cache HIT on every prompt.**
- **Token counters live only in the CLI footer.** Nothing in `GraphState` carries them; the API reports 0 for `llm_calls`/`tokens_in`/`tokens_out` until Phase 5.

**Files touched.**
- `docs/audit/golden/count_suppliers.txt`
- `docs/audit/golden/po_2144_and_lines.txt`
- `docs/audit/golden/suppliers_with_open_pos.txt`

**Cross-references.** Doc A §7.3.3 G, §10.5. Follow-up: WI-S001-02.

---

##### WI-S001-02 — Create branch (Step 1)

| Field | Value |
|---|---|
| Type | chore |
| Doc A reference | §6, §14.4 |
| State | verified |

**Command.**

~~~bash
git checkout master
git pull origin master
git checkout -b phase-4d-ui-api
mkdir -p src/spire/api src/spire/ui tests/integration/api tests/manual/ui
~~~

**Result.** Branch `phase-4d-ui-api` created off `master`.

**Cross-references.** Follow-up: WI-S001-03.

---

##### WI-S001-03 — API skeleton (Step 2)

| Field | Value |
|---|---|
| Type | feature |
| Doc A reference | §10.3.5 |
| State | verified |

**Files created.** `src/spire/api/{__init__,models,server}.py`.

**Dependency.** `fastapi` was not installed — `pip install fastapi` (`fastapi-0.141.1`).

**Verification.**

~~~bash
python -m spire.api.server
# INFO:     Uvicorn running on http://0.0.0.0:8000

curl -s http://localhost:8000/status | python -m json.tool
{
    "ok": true, "service": "spire-api", "version": "0.1.0",
    "started_at": "2026-09-15T05:25:37.541755+00:00", "uptime_s": 24,
    "kg_version": null, "pipeline_ready": true, "error": null
}
~~~

`pipeline_ready=true` confirmed the lifespan hook loaded the KG menu and opened the MCP session.

**Cross-references.** Follow-up: WI-S001-04.

---

##### WI-S001-04 — Wire `/prompt` to pipeline (Step 3)

| Field | Value |
|---|---|
| Type | feature |
| Doc A reference | §10.3.5 |
| State | verified |

**Files created.** `src/spire/api/translate.py`.
**Files modified.** `src/spire/api/server.py`.

**Investigation — the stage-timing path.**

First design used `GRAPH.ainvoke(state, config={"callbacks": [StageTracer()]})`. The callback received no events; `metadata.stages` came back empty every time.

Fix: switch to `GRAPH.astream_events(inputs, version="v2")`, filter `on_chain_start` / `on_chain_end` by node name. Final `GraphState` is the last `on_chain_end` whose output carries the input key `"prompt"`.

**Verification — three golden prompts through the API.**

```
=== Count of suppliers ===
kind: text
latency_ms: 12158
stages: [{'name': 'parse', 'ms': 6156}, {'name': 'plan', 'ms': 1540}, {'name': 'execute', 'ms': 4104}, {'name': 'synthesize', 'ms': 0}]
---
There are 433 suppliers.
=== Show PO 2144 and its lines ===
kind: table
latency_ms: 10108
stages: [{'name': 'parse', 'ms': 6404}, {'name': 'plan', 'ms': 301}, {'name': 'execute', 'ms': 3397}, {'name': 'synthesize', 'ms': 0}]
---
=== Which suppliers have open purchase orders? ===
kind: table
latency_ms: 53015
stages: [{'name': 'parse', 'ms': 6770}, {'name': 'plan', 'ms': 778}, {'name': 'execute', 'ms': 45462}, {'name': 'synthesize', 'ms': 1}]
---
Showing 25 of 433 suppliers. These 25 suppliers have 67 open purchase orders between them.
```

All three returned the correct `kind`. Stage timings fire. `synthesize` at 0–1ms confirms the local summary path.

**Observations.**

- **Pod drift.** "Count of suppliers" returned 433 via API vs 431 in the CLI golden files minutes earlier. "Suppliers with open POs" returned 67, then 44, then 67 on successive runs. Two hypotheses: (a) pod changing between runs, or (b) `search_suppliers` samples a non-deterministic page of 25, and the count depends on which 25 are on the page. **Neither is a Phase 4d defect.** Both belong in Phase 1's probabilistic-behaviour map (§7.3.3 H).
- **PO 2144 summary is empty.** `local_list_summary` returns `[]` for single-row results (documented in `synthesizer/local_summary.py`). Records are what the UI renders.
- **Double classify call.** Present in API path as well as CLI path.

**Cross-references.** Doc A §10.3.5, Doc B §5.1.3. Follow-up: WI-S001-05.

---

##### WI-S001-05 — Streamlit UI + console scripts (Steps 4–7)

| Field | Value |
|---|---|
| Type | feature |
| Doc A reference | §10.3.5 |
| State | verified |

**Files created.**
- `src/spire/ui/__init__.py`
- `src/spire/ui/app.py`
- `src/spire/ui/__main__.py`

**Files modified.** `pyproject.toml` — `[project.scripts]` added.

**Dependency.** `pip install streamlit httpx`.

**Investigation — three issues found and fixed.**

**1. Console script re-launched Streamlit inside Streamlit.** First version had `main()` in `app.py`, and `spire-ui = "spire.ui.app:main"`. Streamlit executed `app.py` as a script and re-ran `main()`, which tried to start a second runtime. Error: `RuntimeError: Runtime instance already exists!`.

Fix: split rendering (`app.py`) from launching (`__main__.py`). `app.py` checks `get_script_run_ctx()` — if a Streamlit context is set, it renders; otherwise it does nothing. `__main__.py` is the console entry. Console script changed to `spire-ui = "spire.ui.__main__:main"`.

**2. `use_container_width` deprecation.** Replaced three calls in `app.py` with `width='stretch'`.

**3. Nested dicts and lists rendered as `[object Object]`.** The synthesizer's records nest `buyers`, `lines`, `schedules`, `contacts`, `addresses` under each row. Streamlit's `st.dataframe` cannot render nested structures. Fix: `_flatten_cell` — pretty-prints lists of dicts by joining a name-like field (`display_name`, `contact_name`, `formatted_address`, `description`, `name`); pretty-prints a bare dict by the same lookup; falls back to compact JSON otherwise. `_flatten_records` runs each row through it before display.

**Verification.** Browser at `http://localhost:8888`:

- **"Count of suppliers"** — pill green; single line; metadata expander with four stage timings.
- **"Show PO 2144 and its lines"** — 1 PO row; `buyer` = `Gee, May`; `lines` = `Marketing Assistance, Marketing Assistance`.
- **"Which suppliers have open purchase orders?"** — yellow truncation banner; summary line; 25-row dataframe; `buyers` column shows names.

**Files touched.**
- `src/spire/ui/__init__.py` (new)
- `src/spire/ui/app.py` (new)
- `src/spire/ui/__main__.py` (new)
- `pyproject.toml`

**Cross-references.** Doc A §10.3.5, Doc B §5.1.6, §5.1.7. Follow-up: WI-S001-06.

---

##### WI-S001-06 — Smoke tests (Step 8)

| Field | Value |
|---|---|
| Type | test |
| Test kind(s) | unit, integration |
| Doc A reference | §10.3.5 |
| State | verified |

**Files created.**
- `tests/test_api_translate.py` — 12 unit tests. Pure: fabricate `GraphState`, assert `ResponseEnvelope`.
- `tests/test_api_endpoints.py` — 4 integration tests. `TestClient` + lifespan; `/status`, `/prompt`, `422`, PO-with-children.
- `tests/manual/ui/checklist.md` — manual checklist.

**Files modified.** `pyproject.toml` — confirmed `[tool.pytest.ini_options]` markers include `integration`.

**Verification.**

~~~bash
python -m pytest -q tests/test_api_translate.py
# 12 passed in 0.08s

python -m pytest -q -m integration tests/test_api_endpoints.py
# 4 passed, 1 warning in 17.85s

python -m pytest -q --collect-only | tail -1
# 1008/1030 tests collected (22 deselected) in 2.55s
~~~

Collection went from 1004/18 to 1008/22 — the 4 new integration tests, correctly deselected.

**Warning noted, not fixed.** `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` Starlette-side; no action.

**Cross-references.** Doc A §14.1. Follow-up: WI-S001-07.

---

##### WI-S001-07 — Byte-equality evidence (Step 9)

| Field | Value |
|---|---|
| Type | test |
| Test kind(s) | byte-equality |
| Doc A reference | §10.5 |
| Bug ID | — |
| Investigation ID | — |
| State | verified |

**Objective.** Confirm the three golden prompts produce the same summary text across CLI and API. The pod drifts, so equality is checked **within the same few minutes**, not against the frozen files forever.

**Commands.**

~~~bash
mkdir -p /tmp/byte_eq

# Prompt 1: Count of suppliers
python scripts/promptkit.py --run --prompt "Count of suppliers" 2>&1 \
  | sed -n '/^Answer:/,/^Summary:/p' | head -n -1 > /tmp/byte_eq/cli_1.txt
curl -s -X POST http://localhost:8000/prompt \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Count of suppliers"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['answer']['text'])" \
  > /tmp/byte_eq/api_1.txt
echo "=== P1 diff ==="; diff /tmp/byte_eq/cli_1.txt /tmp/byte_eq/api_1.txt

# Prompt 2, Prompt 3: same pattern
~~~

**Output.**

```
=== P1 diff ===
1d0
< Answer:

=== P2 diff ===
1d0
< Answer:
3,16d1
< Purchase Orders:
<   Order      : 162352
<   POHeaderId : 2144
...
<   PO 162352 — lines:
<     Line | Description          | Category          | Qty |  Amount
<     -----+----------------------+-------------------+-----+--------
<     1    | Marketing Assistance | Marketing General | 1.0 | 33000.0
<     2    | Marketing Assistance | Marketing General | 1.0 |  8250.0

=== P3 diff ===
1d0
< Answer:
3,38d1
< Suppliers:
<   Supplier                                   | SupplierId      ...
<   ... (25 rows)
< Truncation:
<   - suppliers: 434 total in source; 25 examined for filtering.
< ─── Tip ───
< Reading all 434 suppliers is slow. Narrow with a filter: ...
```

**Analysis.**

The diffs are **formatting, not content.** The differences are:

1. The CLI's `Answer:` header line — CLI label, not summary text.
2. The CLI's inline ASCII render of records — the API returns them as structured `records` in the envelope. Same data, different channel.

The **summary text** in each case is byte-identical:

- **P1:** `There are 434 suppliers.` on both sides (API file is the whole file; CLI file minus its `Answer:` label).
- **P2:** both empty (single-row result → `local_list_summary` returns `[]`).
- **P3:** `Showing 25 of 434 suppliers. These 25 suppliers have 67 open purchase orders between them.` on both sides.

§10.5's acceptance criterion — byte-identical **summary text** — holds for all three prompts.

**No pod drift this run.** CLI and API both saw 434 suppliers and 67 open POs.

**Files.**
- `/tmp/byte_eq/cli_1.txt`, `api_1.txt`
- `/tmp/byte_eq/cli_2.txt`, `api_2.txt`
- `/tmp/byte_eq/cli_3.txt`, `api_3.txt`

**Cross-references.** Doc A §10.5. Follow-up: Step 10 merge.

---

#### Phase status update

- Phase Index row for Phase 4d: ✅ updated in Doc A §6 → Complete.
- Doc A §10.7 Status section: ✅ updated with the deviation note.

#### Blockers / open questions

- Q-001: API port — defaulting to `8000`. Confirm or override.
- Q-002: Tester's browser — same machine or same network? Defaulting to `0.0.0.0` bind.

#### Next session should

- Open S002 and begin Phase 1 (Audit & Baseline, Doc A §7).
- Task 1.1 (`personas.yaml` untrack) is on hold per user instruction — handle at the end.
- Start with task 1.2 (mechanical hygiene) and the audit sections (1.5–1.12).

#### Commits on branch

- `1b7733e` — phase 4d: FastAPI backend + Streamlit UI for SPIRE (branch `phase-4d-ui-api`)
- `14dce82` — Merge pull request #145 (into `master`)

---


---

### 5.1 Phase 4d — UI and API layer (built early)

**Reference:** Doc A §10.3.5.
**Session that opened this:** S001.
**Deviation:** Built before Phases 1–3. Rationale in S001's header. Recorded in Doc A §10.7.

#### 5.1.1 Purpose

A tester can open a browser, type a prompt, and see SPIRE's answer. Two packages — a FastAPI backend and a Streamlit frontend — with a frozen JSON envelope between them.

#### 5.1.2 The call path

```
browser  ─►  Streamlit (src/spire/ui/app.py)
              │  POST /prompt {prompt}
              ▼
         FastAPI (src/spire/api/server.py)
              │  build GraphState {prompt, menu, session}
              │  await GRAPH.astream_events(state, version="v2")
              ▼
         spire.graph.pipeline
              │  final GraphState + stage timings
              ▼
         translate(state) → envelope
              │  {request_id, kind, answer, metadata}
              ▼
         browser renders kind
```

The API owns two long-lived objects: the **KG menu** (loaded once at startup) and the **MCP session** (opened once at startup, closed at shutdown). Per request it builds a fresh `GraphState` and streams the compiled graph.

#### 5.1.3 Pipeline integration

The translation layer reads the final `GraphState` keys in this priority:

| Pipeline state | Envelope kind | Notes |
|---|---|---|
| `state["refusal"]` is set | `refusal` | Structured refusal from parser or `RefusalError`. Fields per §5.1.3.1. |
| `state["error"]` set AND `state["plan_refusal"] is True` | `refusal` | Planner declined. No structured fields. |
| `state["error"]` set AND `plan_refusal` falsy | `error` | Genuine failure. Stage parsed from the `"<node>: <msg>"` prefix. |
| `state["synth_failed"]` set, no `error` | `table` | Summary overran the cap; records valid. `text=""`, `truncation_note` names the cause. |
| `state["response"]` set | `text` or `table` | `table` if the response carries a non-empty record list; else `text`. |
| none of the above | `error` | Defensive. `stage="pipeline"`. |

##### 5.1.3.1 Refusal translation

Two sources mapped to the same `RefusalDetail`:

**From `state["refusal"]`** — the NL parser's `Refusal` object. Read `.reason`, `.solution`, `.example` defensively via `_attr_or_key` (attribute, then dict key, then None). Fallback to `str(refusal)` if none present.

**From `state["error"]` + `plan_refusal=True`** — the planner's text message becomes `reason`; solution and example stay None.

##### 5.1.3.2 Response → records

The synthesizer's response is a Pydantic model with `.summary` and one typed record list. `_RESPONSE_RECORDS_ATTR` maps class name → attribute name. `POLifecycleResponse` is special-cased: `.legs` and `.schedules` flatten into `records`, each row tagged `kind: "leg"` or `kind: "schedule"`.

##### 5.1.3.3 Metadata

| Field | Source |
|---|---|
| `latency_ms` | `time.perf_counter()` around the stream. |
| `llm_calls` / `tokens_in` / `tokens_out` | `0` until Phase 5. |
| `kg_version` | `None` until Phase 3g. |
| `stages` | From `astream_events` (§5.1.3.4). |

##### 5.1.3.4 Stage timings

From `GRAPH.astream_events(inputs, version="v2")`, filtered on the four pipeline node names. Final `GraphState` is the last `on_chain_end` whose output dict contains the input key `"prompt"`.

**Why not callbacks.** `ainvoke(config={"callbacks": [...]})` does not surface LangGraph node boundaries through `BaseCallbackHandler`. Confirmed by probe during WI-S001-04.

#### 5.1.4 The envelope — concrete Pydantic models

~~~python
class PromptRequest(BaseModel):
    prompt: str
    session_id: str | None = None

class StageTiming(BaseModel):
    name: Literal["parse", "plan", "execute", "synthesize"]
    ms: int

class Metadata(BaseModel):
    latency_ms: int
    llm_calls: int
    tokens_in: int
    tokens_out: int
    kg_version: str | None
    stages: list[StageTiming] = Field(default_factory=list)

class TextAnswer(BaseModel):
    text: str
    records: list[dict] = Field(default_factory=list)
    truncated: bool = False
    truncation_note: str | None = None

class RefusalDetail(BaseModel):
    reason: str
    solution: str | None = None
    example: str | None = None

class RefusalAnswer(BaseModel):
    text: None = None
    refusal: RefusalDetail

class PartialAnswer(BaseModel):          # unreachable today; Phase 2 §8.3.7
    text: str
    records: list[dict] = Field(default_factory=list)
    coverage: Literal["partial"] = "partial"
    failed_steps: list[dict] = Field(default_factory=list)

class ErrorDetail(BaseModel):
    stage: str
    message: str
    retryable: bool

class ErrorAnswer(BaseModel):
    text: str
    error: ErrorDetail

Answer = Union[TextAnswer, RefusalAnswer, PartialAnswer, ErrorAnswer]

class ResponseEnvelope(BaseModel):
    request_id: str
    kind: Literal["text", "table", "refusal", "partial", "error"]
    answer: Answer
    metadata: Metadata

class StatusResponse(BaseModel):
    ok: bool
    service: Literal["spire-api"] = "spire-api"
    version: str
    started_at: str
    uptime_s: int
    kg_version: str | None
    pipeline_ready: bool
    error: str | None = None
~~~

#### 5.1.5 Endpoints

**`GET /status`** — 200 with `StatusResponse` when ready; 503 when not.

**`POST /prompt`** — `PromptRequest` → `ResponseEnvelope`. HTTP codes: `200` for `kind ∈ {text, table, refusal, partial}`, `422` malformed, `500` for `kind="error"`, `503` when not ready.

Config via env:
- `SPIRE_API_HOST` — default `0.0.0.0`
- `SPIRE_API_PORT` — default `8000`
- `SPIRE_UI_ORIGIN` — default `http://localhost:8888`
- `SPIRE_MCP_URL` — default `http://127.0.0.1:3333/mcp`
- `SPIRE_UI_HOST` — default `0.0.0.0`
- `SPIRE_UI_PORT` — default `8888`
- `SPIRE_UI_TIMEOUT` — default `180`

#### 5.1.6 Frontend — Streamlit

`src/spire/ui/app.py`. One page. Three zones. Five `kind` renderers. Metadata in a collapsed expander. Raw JSON in a second expander.

**Nested record flattening.** `_flatten_cell` turns nested dicts/lists into readable strings, joining by a name-like field when present, falling back to compact JSON otherwise. This is what makes `buyers`, `lines`, `contacts`, `addresses` render as names instead of `[object Object]`.

#### 5.1.7 Files

```
src/spire/api/__init__.py
src/spire/api/models.py
src/spire/api/translate.py
src/spire/api/server.py
src/spire/ui/__init__.py
src/spire/ui/app.py
src/spire/ui/__main__.py
tests/test_api_translate.py
tests/test_api_endpoints.py
tests/manual/ui/checklist.md
```

**Console scripts** in `pyproject.toml`:

~~~toml
[project.scripts]
spire-api = "spire.api.server:main"
spire-ui  = "spire.ui.__main__:main"
~~~

`app.py` is the renderer, not the entry point. `__main__.py` invokes Streamlit's CLI. This split is required — see WI-S001-05 investigation.

#### 5.1.8 Build steps

| # | Step | Status |
|---|---|---|
| 0 | Capture three golden prompts | ✅ WI-S001-01 |
| 1 | Create branch | ✅ WI-S001-02 |
| 2a–2c | API skeleton + verification | ✅ WI-S001-03 |
| 3a–3d | Wire `/prompt`, stage timings | ✅ WI-S001-04 |
| 4 | `[project.scripts] spire-api` | ✅ WI-S001-05 |
| 5–7 | Streamlit UI + console script | ✅ WI-S001-05 |
| 8 | Smoke tests | ✅ WI-S001-06 |
| 9 | Byte-equality evidence | ✅ WI-S001-07 |
| 10 | Merge to `master` | ✅ completed |

#### 5.1.9 Remaining unknowns

| Unknown | Impact | How resolved |
|---|---|---|
| Exact shape of `nl_parser.result.Refusal` | §5.1.3.1 | `_attr_or_key` handles attribute, dict key, and fallback. If a refusal prompt is available, probe to confirm; not blocking. |
| `fastmcp.Client` concurrency | Step 2b | Deferred: API serializes graph invocations via `asyncio.Lock`. Confirm in Phase 6e. |
| Double `classify` call | Phase 5 observability | Confirm in span work. Not a Phase 4d defect. |
| Pod drift on supplier counts | Phase 1 §7.3.3 H | Confirm and characterize in Phase 1's probabilistic-behaviour map. Not a Phase 4d defect. |

#### 5.1.10 Open questions

- **Q-001:** API port — defaulting to `8000`. Confirm or override.
- **Q-002:** Tester's browser — same machine or same network? Defaulting to `0.0.0.0` bind with no auth.

---

## 6. Dev / runtime separation

**Why this exists.** The tester runtime clone at `~/pocs/spire-runtime` must keep running undisturbed while development continues in `~/pocs/spire`. Two instances of SPIRE at once means two sets of ports.

**Topology.**

| Instance | Path | Branch | Ports (MCP/API/UI) | Tunnel |
|---|---|---|---|---|
| Runtime | `~/pocs/spire-runtime` | `hardening-master` | 3333 / 8000 / 8888 | ngrok → 8888 |
| Dev | `~/pocs/spire` | feature branches | 4444 / 9000 / 9999 | none |

**Mechanism.** `.spire-dev.env` (gitignored) exists only in the dev tree. `spire.sh` sources it if present; otherwise uses runtime defaults. No flag, no remembering.

**Runtime untouched.** The runtime clone never sees `.spire-dev.env` because the file is gitignored, so it always runs on the default ports. Testers are not affected by dev work.

**Runtime updates (deliberate, rare).** When a phase is proven and testers should see it:

~~~bash
cd ~/pocs/spire-runtime
git fetch origin hardening-master
git reset --hard origin/hardening-master
pip install -e .   # in the runtime venv
./spire.sh
~~~

No promotion script exists. Promotion is a manual, deliberate action.

---

## 7. Working-style decisions (informal index)

Cross-references to §2.3. Listed here so a fresh window sees the rules without hunting.

- **D-001** — `hardening-master` is the integration branch. All phase work spawns off it and merges back.
- **D-002** — Integration tests deferred during Phase 1.
- **PR-based merges always.** No local `git merge` into long-lived branches.
- **Branch-first for code, tooling, and non-README docs.** README and pure doc updates may go direct.
- **`personas.yaml` untrack (task 1.1) deferred** per user instruction.
- **One command at a time in interactive sessions.** The user prefers to run commands individually and confirm output before the next one.

---


*End of Phase 4 file.*
