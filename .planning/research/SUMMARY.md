# Project Research Summary

**Project:** AIAgentsCrew - Distributed Skills Agentic Platform
**Domain:** CLI-based agentic platform with dynamic skill discovery, confidence-gated routing, and subprocess sandboxing
**Researched:** 2026-05-16
**Confidence:** MEDIUM-HIGH

## Executive Summary

AIAgentsCrew is a personal CLI tool that allows a Google ADK-powered Gemini agent to discover and execute TypeScript skills dynamically from a GitHub-hosted catalog, without redeploying the agent when new skills are added. The architecture is built around a two-pass routing pattern: on the first pass, the agent extracts semantic tags and evaluates confidence; if confidence falls below 0.72, a CatalogExplorer fetches the lightweight catalog.yaml index, filters by tags, lazy-loads the matching skill.json contracts, and injects them as live ADK FunctionTool instances; on the second pass, Gemini calls the injected tool, which validates parameters and delegates execution to a Deno subprocess sandbox. The critical missing piece identified in PROJECT.md is dynamic tool injection -- the bridge between the already-built CatalogExplorer and the ADK agent layer -- and it is the primary build target for v1.

The recommended stack is well-constrained: Python 3.11 with google-adk==1.33.0, google-genai>=1.72,<2 (hard-pinned below 2.x because ADK 1.33 requires it), Pydantic 2.12+, and Deno 2.x as the skill execution sandbox. All supporting libraries are transitive dependencies already present. The key version risk is the google-genai upper bound -- installing 2.x breaks ADK silently. The build order is architecturally mandated: DenoRunner first (no ADK dependency), then SkillInjector, then CatalogExplorer contract verification, then CoordinatingAgent, then CLI.

The top risks are structural. Two are correctness-breaking if not addressed from the first implementation: using proc.communicate() instead of proc.wait() to avoid pipe deadlock on large Deno output, and enforcing process group kill on timeout to prevent zombie Deno processes. Three more are architecture-level: tool schema bloat exhausting Gemini context window past ~15 injected skills (mitigated by tag pre-filtering), GitHub API rate limiting from no-cache catalog fetches (mitigated by TTL in-memory cache from day one), and confidence threshold drift after Gemini model updates (mitigated by pinning model version and externalizing the threshold to config). None require exotic solutions -- they are well-understood patterns that must be built correctly the first time.

## Key Findings

### Recommended Stack

The stack is tightly constrained by the ADK dependency graph. google-adk==1.33.0 is the latest stable release and ships LlmAgent, Runner, BaseToolset, FunctionTool, and InMemorySessionService in one package. It hard-pins google-genai>=1.72,<2, making google-genai 1.75.0 the correct pin. All supporting libraries (httpx, pyyaml, python-dotenv, jsonschema) are transitive dependencies already present. Deno 2.6.7 is confirmed installed in the environment. The BaseToolset.get_tools() pattern is the correct ADK API for dynamic tool injection -- called per invocation, not at agent construction, which is what makes runtime skill injection possible.

**Core technologies:**
- **Python 3.11**: Runtime -- stability sweet spot with full asyncio.TaskGroup support
- **google-adk 1.33.0**: Agent framework (LlmAgent, Runner, BaseToolset, FunctionTool) -- verified from wheel inspection
- **google-genai 1.75.0** (pinned <2): Gemini API client -- hard upper-bound from ADK METADATA; 2.x breaks ADK silently
- **Pydantic 2.12+**: Data validation for skill.json input_schema and catalog models -- required by ADK
- **Deno 2.x (2.6.7 confirmed)**: TypeScript skill execution sandbox -- deny-by-default permissions, V8 isolation
- **httpx AsyncClient**: Async GitHub catalog fetch -- transitive dependency of google-genai
- **jsonschema**: Pre-execution parameter validation against input_schema -- transitive ADK dependency

### Expected Features

The feature set is defined by the project PRD. The single most important v1 deliverable is one complete discovery -> inject -> validate -> execute -> return cycle.

**Must have (table stakes -- v1 launch blockers):**
- Natural-language intent routing with confidence-gated fallback -- entry point to the entire loop
- Catalog fetch + tag-based pre-filter (CatalogExplorer already implemented) -- verify compatibility
- Lazy-load skill.json per matched skill (already implemented)
- Dynamic tool injection via ADK BaseToolset -- THE missing piece; highest priority build target
- JSON Schema parameter validation before Deno execution -- hard block on malformed LLM output
- Deno subprocess execution with --allow-net=<domain>, 5000ms timeout, no file I/O
- Structured error propagation (timeout / validation failure / execution error each typed separately)
- CLI entry point (python main.py)
- End-to-end test with one real skill (evaluar-test-case or especificar_user_story)

**Should have (add after v1 is stable):**
- SKILL.md cognitive guide injection alongside skill.json -- improves LLM accuracy on domain-specific params
- Confidence threshold calibration based on real usage logs
- TTL-based in-memory cache for catalog.yaml (5-min TTL) -- mitigates GitHub rate limiting
- GITHUB_TOKEN env var for authenticated catalog fetches (5000 req/hr vs 60)
- Routing decision logging (prompt hash, tags, confidence, decision) -- enables re-calibration

**Defer (v2+):**
- Multi-skill DAG chaining -- requires single-skill loop to be solid first
- WebAssembly/Extism execution channel -- Deno covers all current TypeScript skills
- MCP channel for Qdrant -- complex integration, not needed for personal use
- FastAPI / web UI -- orthogonal to validating core loop
- Vector cache (Qdrant, REQ-05) -- premature optimization before latency is measured

### Architecture Approach

The system is a four-layer pipeline: CLI Entry -> Orchestration (CoordinatingAgent wrapping ADK LlmAgent) -> Discovery (CatalogExplorer, already exists) -> Injection (SkillInjector, new) -> Execution (DenoRunner, new). GitHub is the remote config store with no local database in v1. All layer boundaries communicate via async method calls and Pydantic-validated data contracts. The models/skill.py module (already exists) is the shared contract across all layers and must not take ADK or Deno dependencies.

**Major components:**
1. main.py -- CLI entry point; asyncio.run(), minimal surface area
2. agent.py (CoordinatingAgent) -- owns two-pass routing logic, confidence threshold, wires all sub-components; new
3. catalog_explorer.py (CatalogExplorer) -- fetches catalog.yaml, filters by tags, lazy-loads skill.json; already exists
4. skill_injector.py (SkillInjector) -- converts SkillDefinition to ADK FunctionTool; validates params against JSON Schema; new
5. deno_runner.py (DenoRunner) -- asyncio.create_subprocess_exec wrapper with 5000ms timeout, --allow-net control, stdin/stdout JSON I/O; new
6. models/skill.py -- Pydantic models (CatalogManifest, CatalogSkill, SkillDefinition); already exists

### Critical Pitfalls

1. **Pipe deadlock on large Deno stdout** -- always use await proc.communicate(input=...) not await proc.wait(); communicate() concurrently drains both pipes; proc.wait() deadlocks when stdout fills the ~64KB OS pipe buffer. Correctness issue. Fix at first implementation.

2. **Zombie Deno processes on timeout** -- proc.kill() only kills the top-level PID; on POSIX use start_new_session=True + os.killpg to kill the process group; on Windows (this environment) use CREATE_NEW_PROCESS_GROUP + taskkill /F /T. Register an atexit handler. Build into the first working DenoRunner.

3. **Tool schema bloat exhausting Gemini context window** -- each injected skill.json costs 200-800 tokens; past ~15 skills, API returns 400 errors or model hallucinates parameter names. Tag pre-filter is the primary mitigation; add a hard cap (8-12 tools max) and pre-injection token count assertion.

4. **GitHub API rate limiting (60 req/hr unauthenticated)** -- a development session with multiple prompts exhausts the limit quickly. Use raw.githubusercontent.com (CDN-backed, no API rate limit). Add 5-minute TTL in-memory cache for catalog.yaml from day one. Support GITHUB_TOKEN env var.

5. **Confidence threshold drift after Gemini model updates** -- model weight updates shift confidence score distributions silently. Pin model version explicitly (gemini-2.0-flash-001 not gemini-2.0-flash) and externalize threshold to config from the first commit.

6. **Tag extraction open vocabulary mismatch** -- Gemini generates semantically plausible but lexically different tags unless constrained. Include the catalog actual tag list in the Pass 1 system prompt as a constrained vocabulary. Normalize both sides (lowercase, strip hyphens).

7. **allow_net flag injection via malformed skill.json** -- never interpolate raw skill.json values into Deno CLI flags; validate allow_net against a domain-format regex before constructing the subprocess command.

## Implications for Roadmap

Based on the architecture hard dependency chain and the pitfall phase mapping, five phases are recommended:

### Phase 1: Deno Execution Channel (DenoRunner)

**Rationale:** The terminal execution node has zero ADK dependency -- it is pure asyncio + subprocess. Discovering Deno cold-start times, pipe behavior, and platform differences (Windows proc.kill() semantics) is cheapest here. Every Deno pitfall must be resolved before ADK is wired on top.

**Delivers:** A fully tested, isolated DenoRunner module. Any TypeScript skill file can be invoked with correct permission flags, a hard 5000ms timeout, and clean process cleanup. JSON flows in via stdin and out via stdout. All error cases return typed exceptions.

**Addresses features:** Deno sandbox execution, execution timeout enforcement, structured error propagation (Deno-side)

**Avoids pitfalls:** Pipe deadlock (use communicate()), zombie processes (process group kill), allow_net flag injection (domain validation before flag construction), Deno cold start eating timeout budget (measure and set margin)

### Phase 2: Skill Injection Bridge (SkillInjector + CatalogExplorer Contract Verification)

**Rationale:** SkillInjector bridges three systems (Pydantic models, ADK FunctionTool API, DenoRunner) and has the highest coupling risk. Isolating it from live ADK during testing prevents opaque ADK introspection bugs. CatalogExplorer is already built -- this phase verifies the data contract between discovery output (SkillDefinition) and injection input.

**Delivers:** A SkillInjector that accepts a SkillDefinition and returns an async ADK FunctionTool with correct name, description, and _get_declaration() returning types.FunctionDeclaration from input_schema. JSON Schema validation (with additionalProperties: false enforced programmatically) rejects malformed LLM payloads before Deno is called.

**Addresses features:** Dynamic tool injection, JSON Schema parameter validation

**Avoids pitfalls:** Missing additionalProperties: false (injected programmatically if absent from schema), ADK tool registration as plain dict (use types.FunctionDeclaration)

### Phase 3: Coordinating Agent + Two-Pass Routing (CoordinatingAgent)

**Rationale:** Only after DenoRunner and SkillInjector are tested in isolation can the agent layer be built confidently. The confidence threshold must be in config from this phase first commit. The confidence score extraction mechanism must be explicitly designed -- ADK does not expose a built-in confidence score API.

**Delivers:** An agent.py wrapping ADK LlmAgent with two-pass routing. Pass 1 extracts tags and evaluates confidence via structured JSON output. Pass 2 re-runs with injected skill if confidence < threshold. Model version pinned. Routing decisions logged to JSONL. Tag extraction constrained to catalog vocabulary.

**Addresses features:** Natural-language intent routing, confidence-gated fallback routing, tag-based semantic pre-filtering

**Avoids pitfalls:** Confidence threshold drift (externalized to config, model version pinned), tag extraction open vocabulary (constrained vocabulary in system prompt), stateful agent across CLI invocations (tools list reconstructed per run() call)

### Phase 4: CatalogExplorer Integration + Caching

**Rationale:** CatalogExplorer is already built. This phase wires it into the agent and adds production-grade catalog caching -- a blocker for both developer productivity (rate limits during testing) and v1 reliability.

**Delivers:** End-to-end catalog fetch -> tag filter -> lazy-load -> skill injection working in a running agent session. catalog.yaml cached with 5-minute TTL. skill.json cached per session. GITHUB_TOKEN env var supported. raw.githubusercontent.com URLs confirmed.

**Addresses features:** Catalog fetch + tag-based pre-filter, lazy-load skill.json, GITHUB_TOKEN support

**Avoids pitfalls:** GitHub rate limiting (TTL cache + raw URL + auth token), tool schema bloat (tag filter caps candidate set), free-form tag extraction (catalog vocabulary passed to agent system prompt)

### Phase 5: CLI Entry Point + End-to-End Validation

**Rationale:** The CLI is a thin shell -- build it last so all complexity lives in testable layers. The acceptance criterion is one complete prompt-to-output cycle with a real skill. This phase closes the looks-done-but-is-not checklist from PITFALLS.md.

**Delivers:** python main.py works end-to-end. At least one skill executes correctly from a natural-language prompt. All structured error cases return user-readable messages. Progress indicator shown during Deno execution.

**Addresses features:** CLI entry point, end-to-end happy path (one skill), structured error propagation (user-facing)

**Avoids pitfalls:** Silent routing decisions (verbose mode prints tags + confidence), generic timeout error (structured error with skill_name + timeout_ms), catalog fetch failure degrading silently

### Phase Ordering Rationale

- Dependencies are strictly layered: DenoRunner -> SkillInjector -> CatalogExplorer (contract verify) -> CoordinatingAgent -> CLI. Each phase output is the input to the next.
- The two correctness-breaking pitfalls (pipe deadlock, zombie processes) both belong to Phase 1, where they are cheapest to fix.
- The three architecture-level pitfalls (tool bloat, rate limiting, threshold drift) are distributed across phases 3-4 where they are structurally addressed.
- Each phase is independently testable without live ADK or live GitHub. End-to-end tests are deferred to Phase 5.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (SkillInjector):** ADK FunctionTool dynamic callable construction -- how ADK introspects a closure name, docstring, and annotations is MEDIUM confidence. Plan for live ADK experimentation. Fallback: BaseTool subclass with explicit _get_declaration() (pattern verified from wheel inspection).
- **Phase 3 (CoordinatingAgent):** Confidence score extraction mechanism -- ADK does not provide a built-in confidence score API. The Pass 1 system prompt must instruct Gemini to output structured JSON; this design needs explicit implementation.

Phases with standard patterns (skip research-phase):
- **Phase 1 (DenoRunner):** Python asyncio subprocess, communicate(), asyncio.wait_for() -- standard library, HIGH confidence
- **Phase 4 (CatalogExplorer + Caching):** TTL in-memory caching, httpx async, GitHub raw URL -- established patterns
- **Phase 5 (CLI):** argparse + asyncio.run() -- no research needed

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified from PyPI METADATA and wheel inspection; Deno 2.6.7 confirmed live; google-genai<2 constraint verified from ADK wheel METADATA |
| Features | MEDIUM-HIGH | PRD and PROJECT.md are HIGH confidence primary sources; ADK dynamic tool injection patterns are MEDIUM confidence (training data, not live API verification) |
| Architecture | MEDIUM | Layer decomposition and data flow are clear; ADK FunctionTool introspection behavior is MEDIUM confidence and the highest implementation risk |
| Pitfalls | MEDIUM | asyncio subprocess, GitHub rate limits, JSON Schema additionalProperties are HIGH confidence; Deno redirect allow-net bypass is LOW confidence (verify against Deno 2.6.7 changelog) |

**Overall confidence:** MEDIUM-HIGH -- stack is locked with HIGH confidence; architecture is sound with MEDIUM confidence; primary uncertainty is ADK dynamic tool injection API behavior, which will resolve quickly during Phase 2 implementation.

### Gaps to Address

- **ADK FunctionTool dynamic construction:** Verify that ADK schema generator correctly reads a closure name and docstring during Phase 2. Fallback available: BaseTool subclass with explicit _get_declaration() (verified from wheel inspection).
- **Confidence score extraction from Pass 1:** ADK does not expose a raw confidence score. The system prompt must instruct Gemini to output structured JSON. Design this explicitly in Phase 3.
- **Deno redirect behavior with --allow-net:** PITFALLS research flags this as LOW confidence. Verify against Deno 2.6.7 changelog. Use fetch with redirect:error mode as the defensive default regardless.
- **Windows process group kill:** os.killpg is not available on Windows. Verify the taskkill /F /T /PID approach (or Windows Job Objects) in Phase 1 -- this environment is Windows 11.

## Sources

### Primary (HIGH confidence)
- google-adk 1.33.0 wheel METADATA -- Requires-Dist constraints confirming google-genai>=1.72,<2
- google-adk 1.33.0 wheel source -- __init__.py, llm_agent.py, base_toolset.py, base_tool.py, function_tool.py inspected directly
- Live environment: deno --version returns 2.6.7; asyncio.create_subprocess_exec confirmed working
- PRD.md and PROJECT.md -- all functional requirements, acceptance criteria, architectural decisions

### Secondary (MEDIUM confidence)
- Google ADK documentation (training-data knowledge) -- tool registration patterns, BaseToolset, confidence routing
- Deno official security model (training-data knowledge) -- --allow-net semantics, deny-by-default
- Anthropic Tool Definition Schema (training-data knowledge) -- skill.json structure

### Tertiary (LOW confidence)
- Deno redirect behavior with --allow-net -- verify against Deno 2.6.7 changelog; behavior may differ from documented patterns
- LangChain / OpenAI Assistants API competitor comparison -- rapidly evolving products; training data may be stale

---
*Research completed: 2026-05-16*
*Ready for roadmap: yes*
