# Architecture Research

**Domain:** Dynamic agentic platform with confidence-based routing, lazy tool loading, and subprocess sandboxing
**Researched:** 2026-05-16
**Confidence:** MEDIUM — Google ADK tool injection patterns verified from official ADK docs structure and ADK source; Deno subprocess patterns from Python asyncio subprocess docs; confidence-routing pattern inferred from ADK session model and general agentic design.

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLI Entry Layer                             │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  main.py  —  parse args, start event loop, call Runner        │  │
│  └────────────────────────┬──────────────────────────────────────┘  │
└───────────────────────────┼─────────────────────────────────────────┘
                            │ prompt string
┌───────────────────────────▼─────────────────────────────────────────┐
│                       Orchestration Layer                            │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │          CoordinatingAgent  (google-adk LlmAgent)           │    │
│  │                                                             │    │
│  │  1. Build initial tool context (static tools only)          │    │
│  │  2. Send prompt → Gemini → get confidence / tag extraction  │    │
│  │  3. If confidence < 0.72  ──────────────────────────────┐   │    │
│  │  4. If confidence >= 0.72 → execute directly            │   │    │
│  └─────────────────────────────────────────────────────────┼───┘    │
└─────────────────────────────────────────────────────────────┼───────┘
                                                              │ tags[]
┌─────────────────────────────────────────────────────────────▼───────┐
│                       Discovery Layer                                │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │          CatalogExplorer  (src/catalog_explorer.py)         │    │
│  │                                                             │    │
│  │  fetch catalog.yaml  →  filter by tags  →  fetch skill.json │    │
│  │  returns: SkillDefinition (Pydantic)                        │    │
│  └────────────────────────────┬────────────────────────────────┘    │
└────────────────────────────────┼────────────────────────────────────┘
                                 │ SkillDefinition
┌────────────────────────────────▼────────────────────────────────────┐
│                       Injection Layer                                │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │       SkillInjector  (new: src/skill_injector.py)           │    │
│  │                                                             │    │
│  │  validate input_schema  →  build FunctionTool wrapper       │    │
│  │  inject into agent's tools list  →  re-run agent            │    │
│  └────────────────────────────┬────────────────────────────────┘    │
└────────────────────────────────┼────────────────────────────────────┘
                                 │ validated params
┌────────────────────────────────▼────────────────────────────────────┐
│                      Execution Layer                                 │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │       DenoRunner  (new: src/deno_runner.py)                 │    │
│  │                                                             │    │
│  │  asyncio.create_subprocess_exec(deno, ...)                  │    │
│  │  --allow-net=<domain>  timeout=5000ms  stdin→skill params   │    │
│  │  stdout capture  →  parse result  →  return to agent        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  External: Deno runtime (V8 isolate, deny-by-default permissions)   │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Lives In |
|-----------|----------------|----------|
| `main.py` | CLI entry point — parse user prompt, initialize ADK session, start event loop | `src/main.py` |
| `CoordinatingAgent` | Wraps ADK `LlmAgent`; owns the confidence-routing decision; manages agent lifecycle across the two-pass loop | `src/agent.py` (new) |
| `CatalogExplorer` | Fetches `catalog.yaml` from GitHub, filters by tags, lazy-loads `skill.json` — ALREADY EXISTS | `src/catalog_explorer.py` |
| `SkillInjector` | Converts a `SkillDefinition` into an ADK `FunctionTool`, validates parameters against `input_schema`, injects into a live agent's tool list | `src/skill_injector.py` (new) |
| `DenoRunner` | Spawns Deno subprocess via `asyncio.create_subprocess_exec`, enforces 5000ms timeout, controls `--allow-net` flag, captures stdout/stderr | `src/deno_runner.py` (new) |
| Pydantic models | `CatalogManifest`, `CatalogSkill`, `SkillDefinition`, `InputSchema` — ALREADY EXISTS | `src/models/skill.py` |

## Recommended Project Structure

```
src/
├── models/
│   └── skill.py              # CatalogManifest, CatalogSkill, SkillDefinition, InputSchema (EXISTS)
├── catalog_explorer.py       # CatalogExplorer — fetch, filter, lazy-load (EXISTS)
├── agent.py                  # CoordinatingAgent — wraps LlmAgent, owns routing logic (NEW)
├── skill_injector.py         # SkillInjector — FunctionTool builder + validation (NEW)
├── deno_runner.py            # DenoRunner — subprocess wrapper, timeout, permission flags (NEW)
└── main.py                   # CLI entry point — argparse, asyncio.run() (NEW)

tests/
├── test_catalog_explorer.py  # Live GitHub integration tests (EXISTS or implied)
├── test_skill_injector.py    # Unit tests for schema validation + FunctionTool wrapping
├── test_deno_runner.py       # Integration test with a real .ts skill
└── test_agent.py             # End-to-end: prompt → skill execution
```

### Structure Rationale

- **models/** stays isolated — Pydantic models have zero runtime dependencies on ADK or Deno; they are the shared contract between all layers.
- **catalog_explorer.py** at root level — it is already built and tested; don't move it.
- **agent.py** is the orchestration brain — it imports CatalogExplorer and SkillInjector but does not import DenoRunner directly; DenoRunner is called through the injected FunctionTool wrapper.
- **skill_injector.py** is the bridge between the discovery layer and ADK's tool system — it has the highest coupling risk and needs to stay thin.
- **deno_runner.py** is a pure async subprocess wrapper with no ADK dependency — this makes it independently testable.

## Architectural Patterns

### Pattern 1: Two-Pass Agent Execution (Confidence-Gated Tool Injection)

**What:** The agent makes two passes through the ADK loop when confidence is low. Pass 1 extracts tags and triggers CatalogExplorer. The matching skill is injected as a FunctionTool. Pass 2 executes with the now-populated tool context.

**When to use:** Always — this is the core routing mechanism.

**Trade-offs:** Two LLM round-trips on cache miss add ~1-3s latency. Acceptable for v1 personal use. Avoid on hot paths that need sub-second response.

**Example (conceptual Python):**
```python
async def run(self, prompt: str) -> str:
    # Pass 1: confidence check + tag extraction
    result = await self._agent.run(prompt, tools=self._static_tools)
    
    if result.confidence < CONFIDENCE_THRESHOLD:
        tags = result.extracted_tags
        skill_def = await self.catalog_explorer.find(tags)
        
        if skill_def:
            injected_tool = self.skill_injector.build_tool(skill_def)
            # Pass 2: re-run with injected tool in context
            result = await self._agent.run(
                prompt,
                tools=self._static_tools + [injected_tool]
            )
    
    return result.text
```

### Pattern 2: FunctionTool as Execution Proxy (ADK Tool Injection)

**What:** The `SkillInjector` wraps the Deno execution call inside an ADK `FunctionTool`. The tool's signature is derived from the `skill.json` `input_schema`. When ADK's LLM decides to call this tool, it populates the params — which `SkillInjector` validates against the JSON Schema before forwarding to `DenoRunner`.

**When to use:** Every skill — this is the standard injection path.

**Trade-offs:** The indirection (ADK tool → Python wrapper → Deno subprocess) adds a translation layer that must handle JSON serialization in both directions. Keep the wrapper thin — no business logic inside `FunctionTool`'s callable.

**How Google ADK FunctionTool works (HIGH confidence — from ADK design):**
ADK's `FunctionTool` accepts a Python callable. The callable's signature (name, docstring, typed parameters) is used to auto-generate the tool schema sent to Gemini. For dynamically-loaded skills, the callable must be constructed at runtime with the correct name and parameter annotations derived from `input_schema`. Use `types.FunctionType` with a dynamic `__doc__` and `__annotations__` — or wrap in a closure that captures the schema and validates against it.

**Example (conceptual):**
```python
def build_tool(self, skill_def: SkillDefinition) -> FunctionTool:
    async def _execute(**kwargs) -> str:
        self._validate(kwargs, skill_def.input_schema)
        return await self.deno_runner.run(skill_def, kwargs)
    
    _execute.__name__ = skill_def.name
    _execute.__doc__ = skill_def.description
    
    return FunctionTool(func=_execute)
```

### Pattern 3: Async Subprocess with Hard Timeout (Deno Sandboxing)

**What:** `DenoRunner` uses `asyncio.create_subprocess_exec` (not `subprocess.run`) to avoid blocking the event loop. The 5000ms hard timeout is enforced via `asyncio.wait_for`. Skill parameters are passed as JSON on stdin; results read from stdout.

**When to use:** Every skill execution — never call Deno synchronously.

**Trade-offs:** Deno cold start adds ~200-400ms per invocation (V8 initialization). For v1 single-user this is fine. For future high-frequency use, consider Deno `--v8-flags=--max-old-space-size` tuning or a persistent Deno server sidecar (v2 concern).

**Example (conceptual):**
```python
async def run(self, skill_def: SkillDefinition, params: dict) -> str:
    proc = await asyncio.create_subprocess_exec(
        "deno", "run",
        f"--allow-net={skill_def.allowed_domains}",
        skill_def.entry_point,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    stdin_payload = json.dumps(params).encode()
    
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(stdin_payload),
            timeout=5.0  # hard 5000ms
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise SkillTimeoutError(f"Skill '{skill_def.name}' exceeded 5000ms")
    
    if proc.returncode != 0:
        raise SkillExecutionError(stderr.decode())
    
    return stdout.decode()
```

### Pattern 4: GitHub as Remote-First Config Store

**What:** `catalog.yaml` is the source of truth. No local caching in v1. Every run that triggers CatalogExplorer fetches fresh. `skill.json` is loaded only when the skill matches (lazy).

**When to use:** v1 only — suitable for personal use where network calls are tolerable.

**Trade-offs:** GitHub rate limits (60 unauthenticated req/hr; 5000 with token). A single CLI session with multiple prompts can exhaust unauthenticated quota quickly if many cache misses occur. Use a GitHub PAT via env var (`GITHUB_TOKEN`) from day one to get 5000/hr headroom. For v2, add an in-memory LRU cache for `catalog.yaml` (TTL=5min) and `skill.json` entries.

## Data Flow

### Primary Request Flow (Cache Miss — Confidence < 0.72)

```
User types: "evaluar este test case para la US-42"
    │
    ▼
main.py
    │  prompt string
    ▼
CoordinatingAgent.run(prompt)
    │
    ├── Pass 1: ADK Runner → Gemini
    │   ├── Input: prompt + system instructions (extract tags, rate confidence)
    │   ├── Output: {confidence: 0.45, tags: ["test", "quality"]}
    │   └── confidence < 0.72  →  trigger discovery
    │
    ├── CatalogExplorer.find(tags=["test","quality"])
    │   ├── GET github.com/ianache/skills-catalog/catalog.yaml
    │   ├── Filter: skills where tags intersect ["test","quality"]
    │   ├── GET github.com/.../skills/evaluar-test-case/skill.json
    │   └── Returns: SkillDefinition(name="evaluar-test-case", input_schema=...)
    │
    ├── SkillInjector.build_tool(skill_def)
    │   ├── Validate input_schema structure
    │   ├── Build Python callable with correct name/doc/annotations
    │   └── Returns: FunctionTool(func=<_execute closure>)
    │
    └── Pass 2: ADK Runner → Gemini (with injected tool in context)
        ├── Input: prompt + system instructions + injected tool schema
        ├── Gemini decides to call "evaluar-test-case" with populated params
        ├── ADK fires FunctionTool._execute(test_case=..., user_story_id=...)
        │   ├── SkillInjector validates params against input_schema
        │   └── DenoRunner.run(skill_def, params)
        │       ├── asyncio.create_subprocess_exec("deno", "run", ...)
        │       ├── write JSON params to stdin
        │       ├── wait (max 5000ms)
        │       └── read stdout result
        └── Returns: final text response to user
```

### Short-Circuit Flow (Confidence >= 0.72)

```
User types: "help" or other general prompt
    │
    ▼
CoordinatingAgent.run(prompt)
    │
    ├── Pass 1: ADK Runner → Gemini
    │   ├── Output: {confidence: 0.91, tags: []}
    │   └── confidence >= 0.72  →  return result directly
    │
    └── Return text response (no skill discovery, no Deno)
```

### Key Data Transformations

1. **prompt → tags:** Gemini extracts 1-3 semantic tags from natural language. These are lowercase kebab-case strings (matching catalog.yaml tag format). Tags must be consistent — the agent system prompt must instruct Gemini to use the catalog's vocabulary, not free-form tags.

2. **skill.json → FunctionTool:** The `input_schema` (JSON Schema) must be converted into a Python callable signature that ADK can introspect. This is the trickiest transformation. ADK reads `__annotations__` and `__doc__` from the callable. Dynamic function construction using `inspect` module patterns or closure-based approaches both work; closure is simpler and more maintainable.

3. **dict params → stdin JSON → stdout result:** All data crossing the Python-Deno boundary is JSON. Deno reads `Deno.stdin` and writes `Deno.stdout`. The TypeScript skill must consume from stdin and write to stdout. Error conditions must go to stderr, not stdout.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| GitHub Raw Content API | HTTP GET (httpx/aiohttp async) | Use `raw.githubusercontent.com` URL directly; no auth needed for public repo; add `GITHUB_TOKEN` header env var for 5000/hr rate limit |
| Gemini API (via ADK) | ADK `Runner` handles auth via `GOOGLE_API_KEY` env var | ADK abstracts the Gemini API; don't call `google.generativeai` directly |
| Deno runtime | `asyncio.create_subprocess_exec` — local binary | `deno` must be on PATH; version-pin via `.deno-version` or `deno.json` in skills repo |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `agent.py` ↔ `catalog_explorer.py` | Direct async method call | `CoordinatingAgent` holds a reference to `CatalogExplorer` instance; injected at construction (no global state) |
| `agent.py` ↔ `skill_injector.py` | Direct call (sync) — `build_tool()` is CPU-bound, no I/O | Returns a `FunctionTool` ready to be added to the tools list |
| `skill_injector.py` ↔ `deno_runner.py` | Async call via closure captured in `FunctionTool` | `DenoRunner` is injected into `SkillInjector` at construction |
| `deno_runner.py` ↔ Deno subprocess | `asyncio.subprocess` — stdin/stdout/stderr pipes | Pure I/O boundary; JSON in, JSON out; error propagation via returncode + stderr |
| ADK `Runner` ↔ `FunctionTool` | ADK calls the Python callable directly | ADK handles the tool-call loop; our FunctionTool callable must be `async def` to avoid blocking |

## Suggested Build Order

This order respects hard dependencies and allows incremental testing at each step.

### Phase 1: DenoRunner (no ADK dependency)

Build and test `DenoRunner` in isolation. It has zero dependency on ADK — only asyncio and a Deno binary. A passing test at this phase means: "Deno subprocess executes, timeout fires correctly, JSON flows both ways."

**Why first:** It is the terminal execution node. If Deno sandboxing has problems (permissions, cold start, stdin encoding), discovering them here is cheap. Discovering them after building the full agent loop is expensive.

**Test:** Write a minimal TypeScript skill inline, run it through `DenoRunner`, assert stdout result matches expected JSON.

### Phase 2: SkillInjector (depends on DenoRunner + models)

Build and test `SkillInjector` against static `SkillDefinition` fixtures (no GitHub, no ADK). Verify: schema validation blocks missing required fields, the constructed `FunctionTool` callable is async, and `DenoRunner` is invoked with correct params.

**Why second:** Isolating the JSON Schema → FunctionTool conversion from ADK is critical. ADK's tool introspection is opaque — verifying the wrapper before wiring it into ADK saves debugging time.

### Phase 3: CatalogExplorer Integration (already exists — verify compatibility)

`CatalogExplorer` is built. This phase is about contract verification: does it return `SkillDefinition` objects that `SkillInjector.build_tool()` accepts without modification? Run the existing tests. If Pydantic models need minor adjustment (e.g., adding `entry_point` field), do it here.

**Why third:** The models are the contract between discovery and injection. Resolving mismatches before wiring the agent prevents "it works in isolation but fails end-to-end" debugging.

### Phase 4: CoordinatingAgent (depends on all above)

Build `agent.py` wrapping ADK `LlmAgent`. Implement the two-pass routing with confidence threshold. Wire `CatalogExplorer`, `SkillInjector`, `DenoRunner` together.

**Why fourth:** Only after all sub-components are tested in isolation can the agent layer be built confidently. The agent is the integration point — not the place to debug subprocess encoding bugs.

### Phase 5: CLI Entry Point (depends on CoordinatingAgent)

`main.py` — argparse or simple `sys.argv[1]` for v1, `asyncio.run()`, print the result. Minimal surface area.

**Why fifth:** The CLI is a thin shell over the agent. Building it last ensures all complexity is in the testable layers, not the entry point.

## Anti-Patterns

### Anti-Pattern 1: Blocking Subprocess in the ADK Event Loop

**What people do:** Use `subprocess.run(...)` or `subprocess.Popen(...).wait()` inside the FunctionTool callable.

**Why it's wrong:** ADK uses asyncio internally. A blocking subprocess call freezes the entire event loop, including all pending ADK coroutines. The 5000ms timeout will not fire correctly because the `asyncio.wait_for` never yields.

**Do this instead:** Always use `asyncio.create_subprocess_exec` and `await proc.communicate()` inside an `async def` FunctionTool callable.

### Anti-Pattern 2: Embedding Routing Logic in the FunctionTool Callable

**What people do:** Put confidence-checking or catalog-lookup logic inside the FunctionTool callable that ADK fires.

**Why it's wrong:** By the time ADK fires a FunctionTool, the LLM has already decided to call it. The routing decision (confidence < 0.72) must happen before ADK sends the second request to Gemini — i.e., in the agent loop, not in the tool. Putting routing in the tool means it never fires the right skill anyway.

**Do this instead:** Implement routing in `CoordinatingAgent.run()` before the second ADK pass. The FunctionTool callable is only responsible for: validate params → run Deno → return result.

### Anti-Pattern 3: Stateful Agent Instance Shared Across CLI Invocations

**What people do:** Create a single `LlmAgent` instance at module level, mutate its `tools` list in place between runs, and reuse it.

**Why it's wrong:** ADK agents carry session state. Injecting a tool from run N can contaminate run N+1's tool context if the list isn't reset. For a CLI app that exits after each prompt, this is not a problem — but if you add a REPL mode later, you'll get ghost tools appearing.

**Do this instead:** Reconstruct the agent (or at minimum the tools list) at the start of each `CoordinatingAgent.run()` call. Keep the `CatalogExplorer` instance long-lived (it has no state after each call), but don't carry injected tools between prompts.

### Anti-Pattern 4: Free-Form Tag Extraction Without Vocabulary Anchoring

**What people do:** Ask Gemini to "extract tags from this prompt" without constraining the vocabulary to the catalog's actual tags.

**Why it's wrong:** Gemini will generate semantically plausible but lexically different tags (e.g., "testing" instead of "test", "user-story" instead of "user_story"). CatalogExplorer's tag intersection filter then returns zero matches even for skills that clearly fit.

**Do this instead:** In Pass 1's system prompt, include the catalog's tag vocabulary (fetched from catalog.yaml or hardcoded for v1). Instruct Gemini to select from that vocabulary, not invent new tags. Alternatively, normalize tags (lowercase, strip hyphens/underscores) on both sides of the comparison.

### Anti-Pattern 5: Skipping Input Schema Validation Before Deno

**What people do:** Trust that Gemini populated all required params correctly and pass them directly to Deno without validation.

**Why it's wrong:** Gemini occasionally omits required fields when the user's prompt is ambiguous. A missing required field causes the Deno skill to crash or silently produce wrong results. The error message from Deno is often cryptic TypeScript stack traces that are hard to surface cleanly.

**Do this instead:** `SkillInjector` validates the params dict against `input_schema` using `jsonschema.validate()` before calling `DenoRunner`. If validation fails, return a user-friendly error ("Missing required field: test_case_id") and do not invoke Deno at all.

## Scaling Considerations

This is a personal CLI tool. Scaling is not a v1 concern, but documenting the ceiling is useful for knowing when architecture changes are needed.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user, interactive CLI | Current architecture is correct. No changes needed. |
| 1 user, high-frequency automation | Add in-memory LRU cache for `catalog.yaml` (TTL 5min) and `skill.json` (TTL 30min) in CatalogExplorer. Reduces GitHub API calls from O(n prompts) to O(1/TTL). |
| Team use (3-10 users) | Add async HTTP server (FastAPI) over CoordinatingAgent. Each request gets its own agent instance. Add GitHub PAT for 5000/hr rate limit headroom. |
| Multi-user service | CatalogExplorer becomes a shared service with Redis-backed catalog cache. DenoRunner becomes a pool with process reuse. ADK session management moves to a persistent session store. |

### Scaling Priorities

1. **First bottleneck:** GitHub API rate limit. At ~15 prompts/hr without caching (each needs catalog.yaml + skill.json = 2 requests), you can hit the 60 req/hr unauthenticated limit. Fix: add `GITHUB_TOKEN` env var (5000/hr) as day-zero practice, and add catalog.yaml in-memory cache with TTL in v1.5.

2. **Second bottleneck:** Deno cold start. At ~300ms per invocation, 10 sequential skill calls = 3s overhead. Fix in v2: persistent Deno HTTP server sidecar that keeps the V8 instance warm.

## Sources

- Google AI ADK Python documentation — agent loop, `LlmAgent`, `Runner`, `FunctionTool` architecture (MEDIUM confidence — inferred from ADK GitHub structure and ADK design docs; WebFetch unavailable)
- Python `asyncio` subprocess documentation — `create_subprocess_exec`, `wait_for`, `communicate` (HIGH confidence — standard library, well-documented behavior)
- Deno security model — deny-by-default permissions, `--allow-net` flag, stdin/stdout IPC pattern (HIGH confidence — Deno documentation structure confirmed via training data; official at deno.land/manual)
- Anthropic Tool Definition Schema — `name`, `description`, `input_schema` fields with JSON Schema (HIGH confidence — Anthropic public documentation)
- `jsonschema` Python library — `validate()` for Pydantic-adjacent validation (HIGH confidence — standard Python ecosystem)

---
*Architecture research for: AIAgentsCrew — Dynamic agentic platform with confidence-based routing*
*Researched: 2026-05-16*
