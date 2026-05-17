# Feature Research

**Domain:** CLI-based agentic platform with distributed skill discovery (dynamic tool marketplace)
**Researched:** 2026-05-16
**Confidence:** MEDIUM — primary source is the project's own PRD + PROJECT.md (HIGH confidence for what's intended), supplemented by training knowledge of Google ADK, Anthropic Tool Schema, and Deno sandboxing patterns (MEDIUM confidence, web verification unavailable)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that define the platform's contract. Missing any of these = the core loop is broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Natural-language intent routing** | User types a prompt; agent must map it to a skill without user knowing skill names | MEDIUM | Confidence threshold (0.72) gates when to trust local knowledge vs trigger CatalogExplorer. This is the entry point to everything. |
| **Catalog fetch and tag-based pre-filter** | Agent must know what skills exist without downloading all `skill.json` files | LOW | `catalog.yaml` is already the lightweight index. Pre-filter by tag intersection in memory before any lazy load. Already implemented in CatalogExplorer. |
| **Lazy-load skill definition (skill.json)** | Only load the full contract of skills that matched the pre-filter, saving tokens and latency | LOW | GitHub raw content fetch per matching skill. Already implemented. |
| **Dynamic tool injection** | Discovered skill must become a callable tool in the agent's active context for the current request | MEDIUM | ADK supports dynamic tool registration. This is the bridge between CatalogExplorer output and Coordinating Agent execution. The missing piece per PROJECT.md. |
| **JSON Schema parameter validation (pre-execution)** | LLM-generated payloads must be validated against `input_schema` before any execution channel fires | MEDIUM | Hard block on missing required fields. REQ-08 in PRD. Without this, the sandbox may receive malformed input or — worse — execute on bad data. jsonschema Python library handles this. |
| **Deno sandbox execution** | TypeScript skills must run in an isolated, time-bounded process | MEDIUM | subprocess with `--allow-net=<domain>`, 5000ms timeout, no file I/O. Already decided. Without this, skills could do arbitrary damage. |
| **Execution timeout enforcement** | Infinite loops or slow API calls must not hang the agent indefinitely | LOW | 5000ms hard kill on Deno subprocess. TC-03 acceptance criterion. Python's `subprocess.run(timeout=5)` handles this. |
| **Structured error propagation** | Execution failures (timeout, missing param, sandbox crash) must return controlled error state, not stack traces | MEDIUM | Agent must distinguish: validation error (ask user for missing param) vs execution error (log and report) vs timeout (kill and report). Each has a different recovery path. |
| **CLI entry point** | Single command to run the agent (`python main.py` or `uv run agent`) | LOW | v1 interface. Without this, the loop can't be validated at all. |
| **End-to-end happy path (one skill)** | At least one full discovery → inject → validate → execute → return cycle must work | MEDIUM | This is the v1 acceptance criterion. `evaluar-test-case` or `especificar_user_story` are the target skills. |

### Differentiators (Competitive Advantage)

Features that separate this from a static hardcoded tool list. These justify the architecture.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Zero-redeploy skill addition** | Adding a skill to GitHub catalog makes it available to the agent without touching agent code | LOW (catalog side) / MEDIUM (agent side) | The architectural bet of this entire system. New skills appear in the catalog; the agent discovers them on next request. No agent restart, no code change. |
| **Confidence-gated fallback routing** | Agent uses cached/local knowledge when confident (fast), falls back to live catalog only when uncertain | MEDIUM | The 0.72 threshold is the key design parameter. Too high = constant catalog fetches; too low = stale/wrong skill selection. Needs empirical tuning. |
| **Tag-based semantic pre-filtering (in-memory)** | Avoid LLM token cost of reviewing all skill descriptions; use programmatic tag intersection first | LOW | 1-3 tags extracted from prompt, intersected with catalog tags in Python code before any LLM call on skill descriptions. Already implemented. |
| **Two-level catalog structure** | Lightweight root index + full contract per skill = minimal token consumption at discovery time, full contract only when needed | LOW | catalog.yaml is ~100 bytes per skill; skill.json is loaded only for matched candidates. Scales to 100+ skills without token explosion. |
| **SKILL.md cognitive guide** | Human-readable governance doc per skill with business rules, few-shot examples, and constraints — injected alongside skill.json | MEDIUM | This is the prompt engineering layer per skill. Prevents LLM hallucination on domain-specific parameter semantics. Not all tool marketplaces have per-skill cognitive guidance. |
| **Execution channel routing by skill type** | Different skill types (compute, I/O, vector DB) route to appropriate sandbox automatically | HIGH | Deno for TypeScript I/O skills, WebAssembly/Extism for compute, MCP for vector DB. v1 only needs Deno channel; channel routing logic is the differentiator for v2. |
| **Immutable audit log (full lifecycle)** | Every agent cycle persisted: prompt → tag extraction → skill loaded → params validated → execution output | HIGH | REQ-07. ISO 27001 / BASC alignment. Not needed for v1 personal use, but the data structure should be designed to support it from day one. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem reasonable but undermine the architecture or waste v1 scope.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Web UI / FastAPI endpoint** | "Real" products have a UI | CLI is the fastest validation loop. A web layer adds auth, CORS, session management — all orthogonal to proving dynamic discovery works. Will obscure whether the core loop is broken. | Build it in v2 after CLI validates the discovery loop. FastAPI is already in requirements.txt for future use. |
| **Multi-skill DAG chaining (v1)** | REQ-06 is in the PRD; it seems like core functionality | Chaining requires the single-skill loop to be bulletproof first. DAG logic (output of skill A → input of skill B) introduces state management, partial failure handling, and rollback — 3x the complexity for v1. | Prove the single-skill loop end-to-end first. DAG is v2. |
| **Vector cache auto-curation (REQ-05, v1)** | Reducing latency on repeat skill lookups sounds essential | Requires Qdrant to be running, embedded vector embeddings, and async index writes. For a personal CLI tool used dozens of times per day, the catalog fetch (< 500ms) is fast enough. Optimizing before measuring is premature. | Tag-based in-memory pre-filtering is the fast path. Add vector cache only after measuring actual latency pain. |
| **WebAssembly/Extism channel (v1)** | Two execution channels seem more robust | Extism adds a Python native extension, WASM compilation toolchain, and a second sandbox model to maintain. Deno channel covers all current TypeScript skills. | Ship Deno channel. Validate it. Add Extism in v2 for compute-heavy skills (calculator). |
| **Multi-user / team support** | "What if others want to use it?" | The personal-use constraint is explicit. Multi-user introduces auth, per-user skill permissions, rate limiting, and billing — none of which help validate the discovery loop. | Design catalog schema to be multi-user-compatible (namespacing exists already: `comsatel.agente.core`), but don't implement access control in v1. |
| **Real-time streaming output** | LLM responses feel slow without streaming | Streaming adds async complexity (SSE or WebSocket) and is only valuable with a UI. CLI can show a spinner. Solving streaming before solving correctness is scope creep. | Use synchronous generation for v1. Add streaming when building the web UI in v2. |
| **Skill versioning and rollback** | Catalog updates might break existing workflows | Versioning adds `version` fields to `skill.json`, a version resolver, and compatibility checking. This is important at scale but unnecessary when one person controls the catalog. | Use git tags on the skills-catalog repo as your versioning mechanism. The agent always fetches `main`; pin to a tag only if you need stability. |
| **Automated skill publishing pipeline** | CI/CD for skills sounds professional | Each skill is a static YAML + JSON + Markdown. GitHub's default branch push is sufficient. A publishing pipeline adds complexity without value at personal scale. | Manual PR to skills-catalog repo is the publish mechanism for v1. |

---

## Feature Dependencies

```
[CLI entry point]
    └──requires──> [Natural-language intent routing]
                       └──requires──> [Catalog fetch + tag pre-filter]
                                          └──requires──> [Lazy-load skill.json]
                                                             └──requires──> [Dynamic tool injection]
                                                                                └──requires──> [JSON Schema param validation]
                                                                                                   └──requires──> [Deno sandbox execution]
                                                                                                                      └──requires──> [Execution timeout enforcement]
                                                                                                                      └──requires──> [Structured error propagation]

[SKILL.md cognitive guide] ──enhances──> [Dynamic tool injection]
    (injected into agent context alongside skill.json at the same moment)

[Confidence-gated fallback routing] ──enhances──> [Natural-language intent routing]
    (determines WHEN catalog fetch is triggered)

[Two-level catalog structure] ──enables──> [Tag-based pre-filtering]
    (catalog.yaml = index, skill.json = contract; structure makes lazy-load possible)

[Immutable audit log] ──requires──> [Structured error propagation]
    (can only log lifecycle if each stage has structured outputs)

[Multi-skill DAG chaining] ──requires──> [End-to-end single skill] + [Structured error propagation]
    (chaining is impossible if single skill loop is not solid)
```

### Dependency Notes

- **Dynamic tool injection requires Catalog fetch + Lazy-load:** CatalogExplorer produces the `skill.json` dict; ADK tool injection consumes it. The two are coupled by the data contract.
- **JSON Schema validation must precede Deno execution:** This is the "emergency brake" (REQ-08). If validation fires after subprocess launch, malformed data reaches the skill.
- **SKILL.md enhances but does not block:** Injecting SKILL.md content into the agent's system prompt alongside skill.json improves accuracy but the loop works without it. Build it after the basic injection works.
- **Confidence threshold (0.72) is a tunable parameter, not a feature:** It controls routing behavior. The feature is the fallback routing mechanism; 0.72 is the initial calibration value that will need empirical adjustment.
- **Immutable audit log can be retrofitted after v1:** The data flows through structured objects already. Adding persistence later is adding a side-effect sink, not redesigning the architecture — as long as each stage returns structured results, not raw strings.

---

## MVP Definition

### Launch With (v1)

Minimum viable product: one complete discovery → inject → validate → execute → return cycle working from CLI.

- [ ] **CLI entry point** — Single `uv run python main.py` (or equivalent) launches the agent loop
- [ ] **Coordinating Agent on Google ADK** — Receives user prompt, extracts tags, evaluates local confidence, triggers CatalogExplorer when needed
- [ ] **Catalog fetch + tag pre-filter** — CatalogExplorer fetches `catalog.yaml`, intersects tags, returns candidate skill names (already implemented in CatalogExplorer)
- [ ] **Lazy-load skill.json** — For each candidate, fetch `skill.json` from GitHub (already implemented)
- [ ] **Dynamic tool injection** — Inject fetched `skill.json` as an ADK tool into the Coordinating Agent's active context for the current request (THE missing piece)
- [ ] **JSON Schema parameter validation** — Before calling Deno, validate LLM-generated payload against `input_schema`; hard block on missing required fields
- [ ] **Deno sandbox execution** — Run the TypeScript skill as a subprocess with `--allow-net=<domain>`, 5000ms timeout, no file I/O
- [ ] **Structured error propagation** — Timeout, validation failure, and execution error each return a typed error result, not a crash
- [ ] **End-to-end test: one skill** — `evaluar-test-case` or `especificar_user_story` runs clean from prompt to output

### Add After Validation (v1.x)

Add once the core loop is proven working and latency is measured.

- [ ] **SKILL.md injection** — Inject per-skill cognitive guide into agent context alongside skill.json. Trigger: skill selection accuracy is measurably low.
- [ ] **Confidence threshold calibration** — Empirically tune the 0.72 threshold based on real usage. Trigger: too many unnecessary catalog fetches OR missed skill matches.
- [ ] **Vector cache for discovered skills (REQ-05)** — After successful execution, index skill metadata in local Qdrant for faster future routing. Trigger: catalog fetch latency is measured as a pain point (> 500ms regularly).
- [ ] **Immutable audit log** — Persist each agent lifecycle to structured log file or SQLite. Trigger: need to debug agent behavior or demonstrate governance.

### Future Consideration (v2+)

Defer until v1 is validated and personal use is established.

- [ ] **Multi-skill DAG chaining (REQ-06)** — Sequential skill orchestration from a single broad prompt. Requires single-skill loop to be solid.
- [ ] **WebAssembly/Extism channel** — Compute-heavy skills (calculator) run in WASM with microsecond startup. Defer until Deno channel is proven.
- [ ] **MCP channel (Qdrant)** — Vector DB skills via Model Context Protocol. Complex integration; v1 doesn't need it.
- [ ] **FastAPI / web UI** — HTTP interface for the agent. Adds auth, session management; orthogonal to core loop validation.
- [ ] **Docker execution channel** — Container-isolated skill execution for OS-level tools (SRE scripts). Enterprise concern.
- [ ] **Skill versioning** — Pin skills to specific catalog versions. Needed when multiple users depend on stability.
- [ ] **Multi-user / access control** — Per-user skill permissions. Out of scope until platform is open to other users.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| CLI entry point | HIGH | LOW | P1 |
| Coordinating Agent (ADK) with intent routing | HIGH | MEDIUM | P1 |
| Catalog fetch + tag pre-filter | HIGH | LOW (done) | P1 |
| Lazy-load skill.json | HIGH | LOW (done) | P1 |
| Dynamic tool injection | HIGH | MEDIUM | P1 |
| JSON Schema param validation | HIGH | LOW | P1 |
| Deno sandbox execution | HIGH | MEDIUM | P1 |
| Execution timeout enforcement | HIGH | LOW | P1 |
| Structured error propagation | HIGH | MEDIUM | P1 |
| SKILL.md cognitive guide injection | MEDIUM | LOW | P2 |
| Confidence threshold tuning | MEDIUM | LOW | P2 |
| Vector cache (REQ-05) | MEDIUM | HIGH | P2 |
| Immutable audit log | MEDIUM | MEDIUM | P2 |
| Multi-skill DAG chaining | HIGH | HIGH | P3 |
| WebAssembly/Extism channel | MEDIUM | HIGH | P3 |
| MCP channel | MEDIUM | HIGH | P3 |
| FastAPI / web UI | LOW (v1) | HIGH | P3 |
| Docker execution channel | LOW (v1) | HIGH | P3 |

**Priority key:**
- P1: Must have for v1 launch — platform is broken without it
- P2: Should have — add when P1 is stable
- P3: Future — defer to v2+

---

## Competitor Feature Analysis

Note: Direct competitors at this exact design point (ADK + GitHub catalog + Deno sandbox) are rare. Comparison is against analogous systems. Confidence: MEDIUM (training data only, web verification unavailable).

| Feature | LangChain Tools | OpenAI Assistants API | This Platform |
|---------|----------------|----------------------|---------------|
| Tool definition standard | Python class | OpenAI function schema | Anthropic Tool Definition Schema (skill.json) |
| Discovery mechanism | Static import at deploy time | Static config via API | Dynamic, from GitHub catalog at runtime |
| New tool addition | Code change + redeploy | API call to update assistant | Push to GitHub catalog — zero agent redeploy |
| Execution sandbox | Host process (no isolation) | OpenAI-managed (black box) | Deno subprocess (explicit permissions, 5s timeout) |
| Parameter validation | Pydantic models (optional) | JSON Schema (built-in) | JSON Schema pre-execution (hard block) |
| Observability | LangSmith (external product) | OpenAI dashboard (black box) | Structured lifecycle log per request (owned) |
| Skill governance docs | Docstrings only | None | SKILL.md per skill (business rules + few-shot) |
| Catalog structure | N/A | N/A | Two-level (lightweight index + lazy-loaded contract) |

---

## Sources

- **PRD.md** (project root) — PRIMARY source for all functional requirements, acceptance criteria, and architectural decisions. Author: Ilver Anache, dated 2026-05-16. HIGH confidence.
- **PROJECT.md** (`.planning/`) — Validated requirements, explicit out-of-scope items, key decisions. HIGH confidence.
- **Google AI ADK documentation** — Training knowledge of ADK tool-calling patterns, dynamic tool registration, agent orchestration. MEDIUM confidence (training cutoff August 2025; web verification unavailable).
- **Anthropic Tool Definition Schema** — Training knowledge of `name`, `description`, `input_schema` contract. MEDIUM confidence.
- **Deno security model** — Training knowledge of `--allow-net`, `--allow-read`, subprocess isolation, V8 sandbox. MEDIUM confidence.
- **LangChain / OpenAI Assistants API** — Training knowledge for competitor comparison table. LOW confidence for current feature parity (rapidly evolving products).

---
*Feature research for: CLI-based agentic platform with distributed skill discovery (AIAgentsCrew)*
*Researched: 2026-05-16*
