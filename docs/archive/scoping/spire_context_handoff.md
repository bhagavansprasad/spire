# Spire — Context Handoff

**Purpose:** Paste this file into a new Claude conversation to resume work on Spire without re-explaining context. This file is the bridge between conversations.

**Owner:** Bhagavan
**Project:** Spire — AI-native workspace for Oracle Fusion Cloud
**Repo:** `git@github.com:bhagavansprasad/spire.git`
**Local path:** `/home/bhagavan/pocs/spire`
**Environment:** WSL Ubuntu 22.04

---

## How to Use This File

In a new Claude window, paste this entire file as your first message, with a short note like:

> *I'm continuing work on Spire. Read this context file first, then I'll tell you what we're tackling next.*

Then attach (or share the contents of) the two reference documents:

- `spire_poc_master_plan.md` — the full POC plan (architecture, phases, tech stack)
- `spire_design_alternatives.md` — the five designs considered and their trade-offs

These two documents are the source of truth. This file is the index and the working agreement.

---

## Where We Are Right Now

**Status:** Planning complete, implementation not started.

**What exists:**
- Git repo initialized at `github.com:bhagavansprasad/spire.git`
- Two planning documents in the repo root:
  - `spire_poc_master_plan.md`
  - `spire_design_alternatives.md`
- README, LICENSE, and some early sequence-flow PlantUML drafts (`01_sequence_flow.puml`, `02_sequence_flow.puml`)

**What's next:**
- Begin implementation of **Direct Tool Orchestration — Phase 1: Environment & Access Setup** (see master plan section 5)
- Specifically: secure an Oracle Fusion test pod and make one manual REST call work

**Blocking item:**
- Oracle Fusion test pod access. Until this is in place, no implementation work can begin. Options being explored: OPN partner membership, friendly customer sandbox, paid test instance.

---

## Quick Summary of the Product

Spire is an AI-native workspace for Oracle Fusion Cloud consultants. It orchestrates Fusion's REST APIs via specialized AI agents (SQL, BI Publisher, OIC, FBDI, ATP), grounded in a knowledge graph that encodes Fusion entities, relationships, query patterns, and per-tenant customizations. Positioning is *"AI product first, IDE second"* — reference mental models are ChatGPT Canvas, Claude with artifacts, and v0.dev rather than VS Code or SQLConnect.

**Key strategic points:**

- **No data replication.** Spire stores metadata, configuration, audit logs, and conversation history only — never customer transactional data.
- **Endpoints, not tables.** All Fusion access is via published REST endpoints (and BIP for SQL execution). No direct database connection to Fusion.
- **Oracle 26ai as the single storage layer.** Relational, graph (SQL Property Graph), and vector (VECTOR data type) all in one database running locally in Docker.

---

## The POC Architecture Track

Three architectures planned, in order:

1. **Direct Tool Orchestration** — LangGraph agent + MCP tools wrapping Fusion REST endpoints. No KG, no embeddings. Baseline.
2. **Graph-Guided Orchestration** — Same agent + tools, plus a Knowledge Graph in Oracle 26ai that informs the agent's planning.
3. **Dynamic Orchestration** — Adds embedding-based tool retrieval over a large endpoint catalog. Production target. NOT part of the POC unless Graph-Guided proves the KG investment pays off.

The POC's central question: *"Does the KG meaningfully outperform tool descriptions alone on a realistic prompt?"*

**Reference prompt for all comparisons:**
> *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*

---

## Tech Stack (Decided)

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Backend API | FastAPI |
| Agent orchestration | LangGraph |
| MCP server | FastMCP |
| LLM | Google Gemini (`gemini-2.5-pro` agent, `gemini-2.5-flash` subtasks) via `google-genai` SDK |
| HTTP client | `httpx` (async) |
| CLI | `typer` |
| Database (relational + graph + vector) | Oracle AI Database 26ai (local Docker) |
| Oracle Python driver | `python-oracledb` (thin mode) |
| Credentials | YAML file (`personas.yaml`, gitignored), `--persona <name>` CLI flag |
| Validation | Pydantic v2 |
| Testing | `pytest`, `pytest-asyncio` |
| Logging | `structlog` |
| Package manager | TBD (deferred) |

---

## Working Agreements (Important)

These are the agreements that shape how Claude should work with me in any conversation about Spire. Please follow them.

### Approval gates are mandatory

Do **not** generate code, detailed plans, file contents, or implementation specifics without my explicit approval first. The pattern is:

1. Claude proposes (an approach, a plan outline, phase details, etc.)
2. I review and respond with one of:
   - **Option 1:** Approve as-is, proceed
   - **Option 2:** Approve with modifications (I'll specify)
   - **Option 3:** Reject and rethink
3. Only on Option 1 or 2 does Claude proceed.

Even when I say "go ahead," prefer to confirm scope before generating large artifacts.

### Smaller steps are better

Bias toward breaking work into smaller chunks with checkpoints. If something can be done in two steps with my approval between them, prefer that over one big step.

### Honest framing

When I'm wrong, push back clearly. When you don't know something, say so. When a recommendation has trade-offs, name them. Don't oversell or pad responses with reassurance.

### Stay in scope

If I'm asking about implementation details and you notice scope creep, flag it rather than indulging it. "This is interesting but might be premature — should we stay focused on X?" is a useful intervention.

### Match my pacing

I prefer to drive the conversation forward question by question. Don't generate large multi-section responses unless I ask for them. When in doubt, ask before producing.

---

## Things I Tend to Push Back On

Documented so Claude doesn't have to re-discover them:

- **Unnecessary complexity.** I'll question every layer that doesn't earn its place. Tools, KG, embeddings — each needs a clear justification.
- **Pre-decided implementations.** I prefer to specify intent and constraints; I want the tool/AI to decide how, not just what.
- **Locked-in panel positions in UI work.** Recommendations are fine; rigid layouts in prompts are not.
- **Tech stack overcommitment.** I'll decide tech stack when I need to, not before.
- **Generic AI-tool defaults.** Stuff that makes Spire look like every other AI SaaS — generic purple accents, IDE-first layouts, "powered by AI" framing — gets pushed back.

---

## What to Do in the New Context Window

When you (Claude) pick up in a new window, here's the order of operations:

1. **Read this file** (this is what you're doing now).
2. **Read `spire_poc_master_plan.md`** if I've attached it. Understand which phase is current.
3. **Read `spire_design_alternatives.md`** if I've attached it. Understand which designs are in play.
4. **Acknowledge readiness** with a short message confirming you've read the context and noting which phase we're at.
5. **Wait for my next instruction.** Don't volunteer implementation work, don't propose changes to the plan, don't generate code. I'll tell you what we're doing.

A good acknowledgment message looks like:

> *Read the context. We're at Direct Tool Orchestration Phase 1 (Environment & Access Setup), blocked on Oracle Fusion test pod access. Tech stack and architecture decisions are locked. Ready for your next instruction.*

Not like:

> *Hi! Excited to help you build Spire. Here are some ideas for what we could do next...*

---

## Resumption Patterns

When I want to resume work, I'll typically open with one of these:

- *"Phase 1 is unblocked — we have a test pod. Let's start."* → You walk through Phase 1's setup, step by step, with approval gates.
- *"I want to revisit decision X."* → You re-open the relevant section, discuss honestly, and we update the docs together.
- *"I have a new question — [question]."* → Answer directly. Don't volunteer extra context unless asked.
- *"Let's start Phase N."* → Pull up that phase from the master plan; walk through what needs to happen first.

In all cases: **ask me to confirm before generating large artifacts.**

---

## Open Questions Carried Forward

Items deferred or unresolved at the time of this handoff:

- **Fusion pod access** — biggest schedule risk. No POC work possible until resolved.
- **Package manager choice** (`uv`, `poetry`, `pip-tools`, plain pip) — deferred until first implementation phase.
- **Authentication evolution** — Basic Auth for POC, OAuth 2.0 for production. Design persona system to accommodate both.
- **Whether to add Design 2 (SME's reference-library design) as a baseline** alongside Direct Tool Orchestration in the POC. Currently not in the plan; would lengthen POC but provide more evidence-based decision support. Decision deferred to SME conversation.

---

## Files in the Repo Right Now

```
spire/
├── 01_sequence_flow.puml        (early draft, may be superseded)
├── 02_sequence_flow.puml        (early draft, may be superseded)
├── LICENSE
├── PAAS-to-PAAS.docx            (related research notes)
├── README.md                    (currently minimal)
├── spire_design_alternatives.md
├── spire_poc_master_plan.md
└── spire_context_handoff.md     (this file)
```

---

## Document End

This file should be updated when significant new decisions are made, when a phase completes, or when new blocking items appear. Keep it short and current — its value is in being a one-shot brain dump, not a comprehensive history.

**Last updated:** Initial generation (see git history)
