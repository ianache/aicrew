# AIAgentsCrew — Distributed Skills Agentic Platform

## What This Is

A personal agentic platform built on Google AI ADK that dynamically discovers and executes skills without redeploying the core agent. Skills live in a GitHub-hosted catalog (`catalog.yaml` + per-skill `skill.json`); the Coordinating Agent fetches, filters, and injects them at runtime based on what the user's prompt needs. Interaction happens via CLI — type a prompt, the agent figures out which skill fits and runs it.

## Core Value

A user types any prompt and the right skill executes automatically — no manual configuration, no redeployment, just dynamic discovery and execution.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Coordinating Agent built on Google AI ADK responds to user prompts via CLI
- [ ] Agent extracts 1-3 tags from user prompt and triggers CatalogExplorer when confidence < 0.72
- [ ] CatalogExplorer fetches `catalog.yaml` from GitHub, filters skills by tag intersection, lazy-loads matching `skill.json`
- [ ] Skill parameters are validated against `skill.json` input_schema before execution (hard block on missing required fields)
- [ ] Validated skill executes via Deno sandbox with strict 5000ms timeout and `--allow-net` flag control
- [ ] Full end-to-end loop works for at least one TypeScript skill (e.g., `evaluar-test-case` or `especificar_user_story`)
- [ ] CLI entry point runnable with a single command

### Out of Scope

- WebAssembly/Extism channel — v2, after Deno channel is proven
- MCP channel (Qdrant) — v2
- Docker execution channel — future
- Multi-skill DAG chaining — v2 (discovery loop must work first)
- Vector cache auto-curation (REQ-05) — v2
- ISO 27001 immutable logging — v2
- Web UI / FastAPI endpoint — v2 (CLI is sufficient for v1 validation)
- Open-source packaging / other users — may ship later, not a v1 concern

## Context

- **Existing code:** `CatalogExplorer` (`src/catalog_explorer.py`) handles catalog fetching, tag filtering, and lazy-loading of `skill.json`. Pydantic models in `src/models/skill.py` define `CatalogManifest`, `CatalogSkill`, `SkillDefinition`, `InputSchema`. Tests hit the live GitHub repo (`https://github.com/ianache/skills-catalog`) — no mocks.
- **GitHub SSOT:** Skills catalog lives at `https://github.com/ianache/skills-catalog`. Skills follow two-level structure: `catalog.yaml` (root manifest) + `skills/<name>/skill.json` (Anthropic Tool Definition Schema).
- **Skills follow Anthropic Tool Standard:** `skill.json` is a JSON Schema that defines the contract the LLM must populate before any execution channel fires.
- **Personal use first:** The primary user is the developer (Ilver Anache). Enterprise/team scenarios are in the PRD for future reference but don't constrain v1 scope.

## Constraints

- **Tech stack:** Python 3.11 + Google AI ADK (`google-genai`) — non-negotiable, core architecture choice
- **Agent standard:** Skills must follow the Anthropic Tool Definition Schema (`skill.json` = JSON Schema with `name`, `description`, `input_schema`)
- **Execution sandbox:** Deno process invoked as subprocess with `--allow-net=<specific-domain>` and hard 5000ms timeout — no file read/write, no V8 escape
- **GitHub as SSOT:** Catalog and skills live in GitHub; no database, no local registry for v1

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Google AI ADK as agent framework | Core requirement; Gemini models + ADK tool-calling integrates with skill injection | — Pending |
| Deno sandbox for TypeScript skills (not Node) | Security-first: Deno's deny-by-default permissions + V8 isolation + 5000ms timeout are non-negotiable | — Pending |
| GitHub as skills SSOT | No infra to manage; public repo = zero-cost distribution; `catalog.yaml` is the index | — Pending |
| CLI interface for v1 | Fastest path to validate the discovery loop; web/API surface is v2 | — Pending |
| CatalogExplorer already built | Fetch, filter, lazy-load logic is done and tested; Agent layer is the missing piece | — Pending |

---
*Last updated: 2026-05-16 after initialization*
