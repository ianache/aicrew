# Roadmap: AIAgentsCrew — Distributed Skills Agentic Platform

## Overview

Build the missing agent layer on top of the already-existing CatalogExplorer. The delivery order is architecturally mandated: construct the execution sandbox first (no ADK dependency), then the injection bridge, then the agent routing logic, then wire in the catalog with caching, and finally close the end-to-end loop with a CLI entry point. Each phase produces an independently testable artifact; nothing is wired end-to-end until Phase 5.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Deno Execution Channel** - Isolated DenoRunner with timeout enforcement, process cleanup, and typed error results (completed 2026-05-17)
- [x] **Phase 2: Skill Injection Bridge** - SkillInjector converts SkillDefinition to live ADK FunctionTool with JSON Schema validation (completed 2026-05-17)
- [x] **Phase 3: Coordinating Agent + Two-Pass Routing** - CoordinatingAgent wires confidence-gated routing, tag extraction, and JSONL logging (completed 2026-05-17)
- [x] **Phase 4: CatalogExplorer Integration + Caching** - Wire existing catalog into agent with TTL cache, GITHUB_TOKEN, and rate-limit protection (completed 2026-05-17)
- [x] **Phase 5: CLI Entry Point + End-to-End Validation** - Thin CLI shell closes the full prompt-to-output loop with one real skill (completed 2026-05-17)
- [x] **Phase 6: Local Skill Cache — Git Clone Architecture** - Replace all per-file HTTP fetches with a managed local git clone of the skills catalog, enabling multi-file skills and eliminating URL fragility (completed 2026-05-17)

## Phase Details

### Phase 1: Deno Execution Channel
**Goal**: Any TypeScript skill file can be invoked with correct permission flags, a hard 5000ms timeout, clean process cleanup, and typed error results — with zero ADK dependency
**Depends on**: Nothing (first phase)
**Requirements**: EXEC-01, EXEC-02
**Success Criteria** (what must be TRUE):
  1. A TypeScript skill file executes via DenoRunner and returns its JSON stdout result
  2. A skill that runs longer than 5000ms is killed and returns a typed `timeout` error (not a Python exception)
  3. A skill with an invalid `--allow-net` domain value is rejected before the subprocess is created
  4. After timeout or crash, no zombie Deno processes remain in the process tree
  5. A skill that exits non-zero returns a typed `execution_error` result with the stderr content
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffold: Python packages, Pydantic result models, TypeScript test fixtures
- [x] 01-02-PLAN.md — DenoRunner TDD: asyncio subprocess, 5000ms timeout, Windows process kill, typed results

### Phase 2: Skill Injection Bridge
**Goal**: A SkillDefinition parsed from skill.json becomes a live ADK FunctionTool that validates LLM-supplied parameters against JSON Schema before delegating to DenoRunner
**Depends on**: Phase 1
**Requirements**: INJS-01, INJS-02, INJS-03
**Success Criteria** (what must be TRUE):
  1. SkillInjector accepts a SkillDefinition and returns an ADK FunctionTool callable from the agent's tool context
  2. A call with all required parameters passes validation and reaches DenoRunner
  3. A call with missing required parameters is rejected before Deno fires and returns a structured correction request
  4. SKILL.md content fetched from GitHub is injected into the agent context alongside the tool registration
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — Contract definitions: SkillDefinition + ValidationCorrectionRequest models, jsonschema dependency
- [x] 02-02-PLAN.md — SkillInjector TDD: BaseTool subclass, schema normalization, JSON Schema validation, SKILL.md fetch

### Phase 3: Coordinating Agent + Two-Pass Routing
**Goal**: An ADK-backed agent extracts tags from a user prompt, evaluates confidence, and routes to CatalogExplorer when confidence falls below the externalized threshold — with every routing decision logged
**Depends on**: Phase 2
**Requirements**: DISC-01, DISC-02, RELI-03, RELI-04
**Success Criteria** (what must be TRUE):
  1. A prompt with confidence >= 0.72 is answered directly without triggering CatalogExplorer
  2. A prompt with confidence < 0.72 triggers tag extraction constrained to the catalog's actual tag vocabulary
  3. The confidence threshold is read from config (env var or config file) — changing it requires no code edit
  4. Every routing decision writes a JSONL record containing prompt hash, extracted tags, confidence score, routing decision, and matched skill name
**Plans**: 1 plan

Plans:
- [x] 03-01-PLAN.md — CoordinatingAgent TDD: Config dataclass, two-pass routing, JSONL log, CatalogExplorer stub

### Phase 4: CatalogExplorer Integration + Caching
**Goal**: The agent discovers and loads real skills from the GitHub catalog with in-memory caching, GITHUB_TOKEN support, and no silent rate-limit failures
**Depends on**: Phase 3
**Requirements**: DISC-03, DISC-04, RELI-01, RELI-02
**Success Criteria** (what must be TRUE):
  1. The agent fetches catalog.yaml from GitHub and filters skills by extracted tags in a live session
  2. A matched skill's skill.json is lazy-loaded from GitHub per request without pre-fetching the full catalog
  3. A second catalog fetch within 5 minutes returns the cached result without making a GitHub network call
  4. When GITHUB_TOKEN is set in the environment, catalog fetches use authenticated requests (5000 req/hr limit)
**Plans**: 1 plan

Plans:
- [x] 04-01-PLAN.md — CatalogExplorer TDD: httpx GitHub fetch, OR-logic tag matching, TTL cache, GITHUB_TOKEN auth, catalog_error logging

### Phase 5: CLI Entry Point + End-to-End Validation
**Goal**: A user types `python main.py`, enters a natural-language prompt, sees a progress indicator during execution, and receives the skill result or a user-readable error message
**Depends on**: Phase 4
**Requirements**: EXEC-03, CLI-01, CLI-02
**Success Criteria** (what must be TRUE):
  1. Running `python main.py` without arguments starts an interactive prompt session
  2. A natural-language prompt triggers the full discovery-inject-validate-execute loop and returns the skill result
  3. At least one real TypeScript skill (`evaluar-test-case` or `especificar_user_story`) completes successfully end-to-end
  4. A progress indicator is visible in the terminal during the Deno execution window
  5. Timeout, validation failure, and execution error each produce a distinct user-readable message (not a raw Python traceback)
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md — CLI wiring: rich dep, error string alignment, status_cb on agent.run(), main.py REPL
- [x] 05-02-PLAN.md — E2E test: smoke + live full-pipeline test with real skill

### Phase 6: Local Skill Cache — Git Clone Architecture
**Goal**: All skill assets are available as local files via a managed git clone of the skills catalog — no per-file HTTP calls during routing or execution, no URL fragility, and full support for multi-file skills
**Depends on**: Phase 5
**Requirements**: REPO-01, REPO-02, REPO-03, REPO-04
**Success Criteria** (what must be TRUE):
  1. On first use, the skills catalog is cloned to `.skills-cache/` (or `SKILLS_CACHE_DIR` env var) without any manual setup
  2. A second run within the TTL reads `catalog.yaml` and all skill files from the local clone — no git network operation, no HTTP call
  3. A run after TTL expiry triggers `git pull` and updates the local clone before serving requests
  4. Deno executes `skills/{name}/index.ts` from the local clone path — no remote URL download at execution time
  5. Deleting `.skills-cache/` triggers a fresh clone on the next run (self-healing)
  6. All 57 existing non-live tests continue to pass (no regression)
**Plans**: 3 plans

Plans:
- [x] 06-01-PLAN.md — SkillCache TDD: git clone lifecycle, file-based TTL, partial-clone guard; Config cache fields
- [x] 06-02-PLAN.md — CatalogExplorer + SkillInjector refactor: local file reads, --allow-read flag, main.py wiring
- [x] 06-03-PLAN.md — Test updates: conftest fixtures, catalog explorer unit tests, skill injector local-path tests

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Deno Execution Channel | 2/2 | Complete | 2026-05-17 |
| 2. Skill Injection Bridge | 2/2 | Complete | 2026-05-17 |
| 3. Coordinating Agent + Two-Pass Routing | 1/1 | Complete | 2026-05-17 |
| 4. CatalogExplorer Integration + Caching | 1/1 | Complete | 2026-05-17 |
| 5. CLI Entry Point + End-to-End Validation | 2/2 | Complete | 2026-05-17 |
| 6. Local Skill Cache — Git Clone Architecture | 3/3 | Complete | 2026-05-17 |
