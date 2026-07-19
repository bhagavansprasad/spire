# Agent-KG Integration Design

**Phase:** Dynamic Orchestration 04 — KG Query Tools (design doc, lands first commit)
**Status:** Decision recorded; implementation in subsequent phase 04 commits
**Decision:** Option B-lite — KG content statically embedded in the system prompt at startup. No per-request planner; no KG MCP tools.

This document captures the architectural decision for how the agent talks to the KG, the alternatives considered, the failure-mode evidence that drove the choice, and how the decision was reached (including an honest revision).

Companion docs:
- `kg_schema_v1.md` — what the KG models
- `kg_evaluation_framework.md` — how the decision will be tested
- `../phase_a5_baseline_report.md` — Track A's failure evidence

---

## 1. The Question

Phase 03 built the KG as five flat tables in the SPIRE schema. The KG is queryable. But the central architectural question for Track B remains open:

**How does the agent talk to the KG?**

The three boxes don't change between options:

- **LLM (Gemini)** — does the reasoning
- **KG (Oracle tables, populated)** — holds structural knowledge
- **Agent loop (LangGraph)** — orchestrates between them

What changes is **the path the KG knowledge takes to reach the LLM**.

---

## 2. The Four-Context View

Five actors split across four contexts (deployment/process boundaries):

| Context | Actors | Where it runs |
|---|---|---|
| **User context** | User | Terminal / `ask.py` CLI invocation |
| **Backend context** | Agent loop (LangGraph) + LLM call site | The Python process that runs `ask.py`; LLM is called from here but lives at Google |
| **MCP server context** | MCP tools (Fusion + KG), FusionClient, OracleClient | Separate process on `127.0.0.1:3333` (FastMCP) |
| **External endpoints** | Fusion REST + Oracle 26ai + Gemini | Cloud (Fusion, Gemini), local Docker (Oracle) |

The architectural question reframes as: **which context owns the decision about what KG knowledge the LLM gets to see on a given run?**

---

## 3. The Four Options Considered

### Option A — KG queries as MCP tools the LLM can call

The KG is exposed as a set of MCP tools (`kg_get_entity`, `kg_get_edge`, `kg_get_pattern`, `kg_lookup_vocabulary`, etc.) alongside the existing Fusion tools. The LLM sees them in its tool list; it decides when to consult.

**Owner of the decision:** the LLM. Backend context just runs the loop.

**Strengths:**
- Cleanest ablation (remove KG tools from the tool list)
- Symmetric with how Fusion tools already work
- Smallest mental model — "more tools"

**Weaknesses:**
- The LLM may *ignore* the KG tools and pattern-match like Track A did
- Inherits Track A's failure mode rather than addressing it

### Option B (full) — Pre-LLM planner builds a KG context bundle per request

A new "planner" component runs **before** the LLM. It analyzes the user prompt, identifies which entities/edges/patterns/vocabulary are relevant, queries the KG, and packages a context bundle into the system prompt. The LLM then runs as in Track A, with Fusion tools and the bundle in its context.

**Owner of the decision:** backend context (the planner).

**Strengths:**
- Bypasses Track A's failure mode (LLM can't ignore knowledge it can't avoid)
- Per-prompt relevance: only the KG content this prompt needs is loaded

**Weaknesses:**
- The planner is non-trivial to build — how does it know what's relevant without already understanding the prompt?
- Likely needs an LLM-driven extraction step (turns into two LLM calls)
- Adds a new component with its own failure modes
- Ablation is messier (the planner does more than KG injection)

### Option B-lite — Static KG context, loaded once, embedded in the system prompt

A small loader queries the KG **once at agent startup**, formats the full v1 KG into a structured text section, and includes it in the system prompt for every conversation. No per-request planning, no per-request KG queries.

**Owner of the decision:** backend context. But the "decision" is trivial — always show the LLM the whole v1 KG.

**Strengths:**
- Bypasses Track A's failure mode same as B
- Tiny engineering surface — one loader, no planner
- Trivial ablation (swap system prompt to one without KG content)
- KG knowledge is **always in front of the LLM**, not optional

**Weaknesses:**
- System prompt is bigger (a few thousand tokens of KG content per request)
- Same content every prompt — no per-prompt tuning
- Doesn't scale to large KGs (but v1 is ~80 rows; not a v1 concern)
- The LLM might glaze over a dense system prompt (mitigation: format and tune the KG section for readability)

### Option C — Hybrid (static summary + drill-down tools)

KG summary in the system prompt (like B-lite) **and** KG MCP tools available for the LLM to call when it wants more detail (like A).

**Strengths:**
- Belt-and-suspenders for production
- LLM always sees basics; can drill down on demand

**Weaknesses:**
- Two integration points to design and test
- Hardest to ablate — disabling "the KG" means disabling both, and if scores move, attribution is muddy
- Largest engineering surface
- POC-inappropriate (production pattern, not measurement pattern)

---

## 4. Evidence That Drove the Decision

Track A's baseline measured 1/7 on the reference prompt across 5 runs. Failure breakdown:

| Failure mode | Runs affected | Root cause |
|---|---|---|
| Premature termination | 3 of 5 | LLM called one tool, didn't iterate, didn't ask for more |
| Parameter confusion across tools | 2 of 5 | LLM passed `supplier_number` to a tool expecting `supplier_id`; crashed |
| No error recovery | 2 of 5 (the crashes) | LangGraph propagated the tool exception; LLM never saw or recovered from it |

Common thread: **the LLM didn't recognize when it needed more information** — neither asked for help with disambiguation, nor iterated to find the next step, nor recovered from a tool error.

This is the recognition skill Option A relies on. If the LLM can't recognize "I need more information," it won't recognize "I should consult the KG" either. Option A asks the LLM to do exactly the kind of self-aware querying Track A showed it does poorly.

Options B and B-lite bypass this by making the knowledge **present in the LLM's context whether it asks or not.** The LLM doesn't have to recognize a need; the information is just there.

This evidence weights against A and toward B / B-lite.

---

## 5. The Decision: B-lite

Among B-lite, B (full), and C:

- **B-lite** has the smallest engineering surface and the cleanest ablation among the options that bypass Track A's failure mode. It addresses the right problem with the lightest tool.
- **B (full)** addresses the same problem but adds a per-request planner. The planner is its own engineering project. For v1, the static-bundle approach is sufficient because the KG fits in context comfortably.
- **C** is a production architecture, not a measurement architecture. Two integration points muddy the ablation.

**B-lite it is.**

### What B-lite looks like in code

| Layer | What changes |
|---|---|
| New loader | Loads all 5 KG tables at startup, formats them into a structured text section |
| `runner.py` | System prompt gains a `{{ kg_context }}` section, populated at agent build time |
| `src/spire/mcp_server/` | **No new MCP tools.** Existing Fusion tools unchanged. |
| Tests | New test verifies the loader produces a non-empty, well-formed context section |
| Configuration | Add a way to swap KG context in/out (for ablation in phase 08) |

The new code lives in **backend context** (the `ask.py` / `runner.py` process), not in the MCP server. The MCP server is unchanged. This is intentional: the KG content is part of *how the agent thinks*, not part of *what the agent does*.

### What B-lite explicitly does NOT do

- No new MCP tools. The agent's tool list is unchanged from Track A.
- No per-request KG queries. KG is loaded once at startup.
- No planner. No prompt analysis. No relevance scoring.
- No graph queries (`MATCH`). The loader uses plain SQL to fetch table rows.
- No embeddings. KG content is plain text. Phase 06 may add embeddings if Tier 1 evaluation suggests they'd help.

### How the evaluation framework ablation works under B-lite

`kg_evaluation_framework.md` §3 calls for an ablation run to isolate the KG's contribution. Under B-lite, ablation is:

1. Configure the agent to use a system prompt **without** the KG context section
2. Same Fusion tools, same model, same prompt, same rubric
3. Re-run the 5-run measurement

The delta between with-KG and without-KG is the KG's contribution. Other improvements (better system prompt framing, tool description refinements landed during Track B) are still present in both, so the ablation isolates the KG component cleanly.

---

## 6. Honest Revision Note

The first lean recorded for this decision was Option A, with the reasoning "cleanest to evaluate; ablation is trivial." That lean was sloppy: it optimized for measurability without weighing the failure-mode mismatch with Track A's evidence.

After working through the four options with sequence diagrams and the four-context framing, the revised read was that A inherits exactly the failure mode Track A demonstrated (LLM doesn't ask for help when it should). B-lite bypasses that mode while keeping ablation clean enough.

Recording this because the working agreement values honest framing over revisionist tidiness, and because future readers (including future-self) should see that the architecture wasn't obvious on first pass. Both leans were defensible; B-lite is better-supported by the evidence.

---

## 7. Implications for Subsequent Phases

| Phase | Implication |
|---|---|
| 04 (rest of this phase) | Build the KG context loader. Update `runner.py` to inject KG content into the system prompt. Add tests. No new MCP tools. |
| 05 (Agent integration) | Largely subsumed by phase 04 under B-lite — there's no separate "integrate the KG" step because the KG enters the agent at startup, not at runtime. Phase 05 becomes "verify end-to-end on a smaller variant of the reference prompt before phase 08." |
| 06 (Embeddings) | Open question. B-lite doesn't need embeddings for v1. If Tier 1 evaluation suggests the static bundle is too dense and LLM glaze is a real problem, phase 06 might introduce embedding-based selection of which KG content to include. Defer the decision. |
| 07 (Polish) | Mostly tracing improvements. Verify KG section is recorded in trace files for later inspection. |
| 08 (End-to-end test) | 5-run measurement with KG-on. |
| 09 (Comparative) | Ablation: 5-run measurement with KG-off (system prompt sans KG section). Tier 2 from `kg_evaluation_framework.md`. |

The phase 05 implication is the biggest: under B-lite, phase 05 shrinks because there's no agent loop change required. The integration *is* the system prompt change.

---

## 8. What This Decision Does Not Settle

A few questions deliberately deferred:

- **Format of the KG context section in the system prompt.** Markdown table? Structured JSON? Prose bullets? This is a tuning decision; phase 04's implementation will pick a default and we can iterate.
- **Should KG content include the full pattern `mechanics` text, or just pattern names + parameters?** Bigger means denser prompt; smaller means LLM may not have enough to act on. Tunable.
- **Should the KG context be in the system prompt or in a special first user/assistant turn?** Implementation detail; either works. System prompt is simpler.
- **How big is "too big" for the system prompt?** Empirically tunable. Gemini handles long context well; not a v1 risk.
- **What happens if the KG is empty or unreachable at startup?** Edge case. The loader should fail fast with a clear error rather than silently producing an empty bundle.
- **Whether `cross_pillar_lookup` survives as a pattern.** Phase 03 flagged this as the pattern least confident about. Phase 04 implementation may find it redundant with the `ASSIGNED_TO` edge content; if so, v1.1 schema update drops it.

These are tuning knobs, not architectural decisions. The architecture is settled; the tuning happens during phase 04's iteration.

---

## 9. Summary

- The question: how does the agent talk to the KG?
- Four options considered: A (tools), B (planner), B-lite (static bundle), C (hybrid)
- Track A's evidence: LLM doesn't recognize when it needs more information
- Decision: **B-lite** — bypasses the recognition problem with the smallest engineering surface
- Implementation lives in backend context; MCP server is unchanged
- Ablation cleanly isolates the KG's contribution by swapping the system prompt
- Phase 05 shrinks as a result; phase 04 absorbs most of the integration work
- Tuning decisions (bundle format, density, etc.) deferred to phase 04 implementation

The architecture is settled. The phase 04 work that follows is implementation against this design.
