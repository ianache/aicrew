# Requirements: AIAgentsCrew — Distributed Skills Agentic Platform

**Defined:** 2026-05-16
**Core Value:** A user types any prompt and the right skill executes automatically — no manual configuration, no redeployment, just dynamic discovery and execution.

## v1 Requirements

### Discovery & Routing

- [x] **DISC-01**: Coordinating Agent routes user prompt via confidence-gated fallback — if confidence < configurable threshold (default 0.72), delegates to CatalogExplorer
- [x] **DISC-02**: Pass 1 tag extraction constrains output to the catalog's actual tag vocabulary to prevent open-vocabulary mismatch
- [x] **DISC-03**: CatalogExplorer fetches `catalog.yaml` from GitHub SSOT and filters skills by tag intersection (already built — this requirement covers contract verification against new SkillInjector)
- [x] **DISC-04**: Matched skill's `skill.json` is lazy-loaded from GitHub SSOT per request (already built — this requirement covers integration into the v1 pipeline)

### Injection

- [x] **INJS-01**: SkillInjector converts `SkillDefinition` (from `skill.json`) to a live ADK `FunctionTool` via `BaseToolset.get_tools()` for runtime injection into the agent's active tool context
- [x] **INJS-02**: LLM payload is validated against `skill.json` `input_schema` (JSON Schema) before Deno fires — missing required fields block the call and return a structured correction request to the agent (no infrastructure call made)
- [x] **INJS-03**: `SKILL.md` cognitive guide content is fetched from GitHub and injected into agent context alongside `skill.json`

### Execution

- [x] **EXEC-01**: Matched skill executes via Deno subprocess with `--allow-net=<validated-domain>` (domain validated against regex before flag construction), no file I/O permissions, hard 5000ms timeout; process group killed on timeout with no zombie processes
- [x] **EXEC-02**: Execution errors return typed structured results (timeout / validation_failure / execution_error) — not generic Python exceptions propagated raw to the user
- [x] **EXEC-03**: CLI shows a progress indicator during the Deno execution window so the user knows the skill is running

### Reliability

- [x] **RELI-01**: `catalog.yaml` responses are TTL-cached in-memory (5-minute TTL) to prevent GitHub rate limit exhaustion during active development
- [x] **RELI-02**: `GITHUB_TOKEN` env var supported for authenticated GitHub fetches (5000 req/hr vs 60 unauthenticated)
- [x] **RELI-03**: Confidence threshold is externalized to config (env var or config file) — re-calibratable without code change
- [x] **RELI-04**: Each routing decision logged to JSONL (prompt hash, extracted tags, confidence score, routing decision, matched skill name if any)

### CLI

- [x] **CLI-01**: User runs `python main.py` from terminal, enters a natural-language prompt, receives a result
- [x] **CLI-02**: End-to-end happy path verified with at least one real TypeScript skill from the GitHub catalog (`evaluar-test-case` or `especificar_user_story`)

### Repository Cache (Phase 6)

- [ ] **REPO-01**: Skills catalog cloned to local `.skills-cache/` on first use via `git clone`; subsequent runs within TTL (default 5 min, configurable via `SKILLS_CACHE_TTL` env var) read from local clone without any network operation
- [ ] **REPO-02**: All skill assets (TypeScript entry point, Python helpers, config files, SKILL.md) accessible as local files after sync — zero per-file HTTP calls during routing or execution
- [ ] **REPO-03**: `GITHUB_TOKEN` env var supported for authenticated `git clone` / `git pull` — same token already used for HTTP fetches in Phase 4
- [ ] **REPO-04**: Deno executes TypeScript skills from local clone path (`skills/{name}/index.ts`) — eliminates remote URL downloads and GitHub URL format fragility at execution time

## v2 Requirements

### Orchestration

- **ORCH-01**: Multi-skill DAG chaining — single prompt triggers sequential execution of multiple skills (user story → test case → evaluation)
- **ORCH-02**: Vector cache auto-curation — after successful skill execution, index skill metadata in local Qdrant for sub-72ms future routing

### Execution Channels

- **CHAN-01**: WebAssembly/Extism channel for closed-compute skills (calculator) — microsecond latency, no network, fully isolated memory
- **CHAN-02**: MCP channel for Qdrant knowledge base integration (`qdrant_kb`)

### Observability

- **OBS-01**: ISO 27001 / BASC-aligned immutable execution logs — full lifecycle capture from prompt to output

## Out of Scope

| Feature | Reason |
|---------|--------|
| FastAPI / web endpoint | CLI sufficient for v1 validation; orthogonal to core loop |
| Docker execution channel | Future — not needed until SRE-class skills are added |
| Multi-user / enterprise auth | Personal use first; team/compliance scenarios are v2+ |
| Open-source packaging | May ship later; not a v1 concern |
| Frontend / dashboard UI | CLI is the v1 interface |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXEC-01 | Phase 1 | Complete (01-02) |
| EXEC-02 | Phase 1 | Complete (01-01) |
| INJS-01 | Phase 2 | Complete |
| INJS-02 | Phase 2 | Complete |
| INJS-03 | Phase 2 | Complete |
| DISC-01 | Phase 3 | Complete |
| DISC-02 | Phase 3 | Complete |
| RELI-03 | Phase 3 | Complete |
| RELI-04 | Phase 3 | Complete |
| DISC-03 | Phase 4 | Complete (04-01) |
| DISC-04 | Phase 4 | Complete (04-01) |
| RELI-01 | Phase 4 | Complete (04-01) |
| RELI-02 | Phase 4 | Complete (04-01) |
| EXEC-03 | Phase 5 | Complete (05-01) |
| CLI-01 | Phase 5 | Complete (05-01) |
| CLI-02 | Phase 5 | Pending (05-02) |

| REPO-01 | Phase 6 | Not started |
| REPO-02 | Phase 6 | Not started |
| REPO-03 | Phase 6 | Not started |
| REPO-04 | Phase 6 | Not started |

**Coverage:**
- v1 requirements: 20 total (16 original + 4 Phase 6)
- Mapped to phases: 20
- Unmapped: 0

---
*Requirements defined: 2026-05-16*
*Last updated: 2026-05-17 after 04-01 completion*
