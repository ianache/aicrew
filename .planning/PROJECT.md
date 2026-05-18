# AIAgentsCrew — Distributed Skills Agentic Platform

## What This Is

A personal agentic platform built on Google AI ADK that dynamically discovers and executes TypeScript skills without redeploying the core agent. Skills live in a GitHub-hosted catalog (`catalog.yaml` + per-skill `skills.json`); the Coordinating Agent fetches, filters, and injects them at runtime based on what the user's prompt needs. Interaction happens via CLI — type a prompt, the agent figures out which skill fits and runs it via a local git-cloned Deno sandbox. Shipped v1.0 with a 6-phase, 11-plan build from scratch in one day.

## Core Value

A user types any prompt and the right skill executes automatically — no manual configuration, no redeployment, just dynamic discovery and execution.

## Requirements

### Validated

- ✓ Coordinating Agent built on Google AI ADK responds to user prompts via CLI — v1.0
- ✓ Agent extracts 1-3 tags from user prompt and triggers CatalogExplorer when confidence < 0.72 — v1.0
- ✓ CatalogExplorer reads `catalog.yaml` from local git clone, filters skills by tag intersection, lazy-loads matching `skills.json` — v1.0
- ✓ Skill parameters are validated against `skills.json` input_schema before execution (hard block on missing required fields) — v1.0
- ✓ Validated skill executes via Deno sandbox with strict 5000ms timeout and `--allow-net` flag control — v1.0
- ✓ Full end-to-end loop works for at least one TypeScript skill — v1.0
- ✓ CLI entry point runnable with a single command (`uv run python main.py`) — v1.0
- ✓ Skills catalog cloned to `.skills-cache/` with 5-min TTL git pull refresh — v1.0
- ✓ Zero per-file HTTP calls during routing or execution after initial clone — v1.0
- ✓ Deno executes from local clone path with `--allow-read=.skills-cache/` — v1.0

### Active

- [ ] Multi-skill DAG chaining — single prompt triggers sequential execution of multiple skills
- [ ] FastAPI endpoint — expose agent as HTTP service for programmatic use

### Out of Scope

- WebAssembly/Extism channel — v2, after Deno channel is proven
- MCP channel (Qdrant) — v2
- Docker execution channel — future
- Vector cache auto-curation — v2
- ISO 27001 immutable logging — v2
- Open-source packaging / other users — may ship later, not a v1 concern

## Context

- **v1.0 shipped 2026-05-17** — 6 phases, 11 plans, 66 commits, ~3,200 lines Python, 62 non-live tests passing
- **Tech stack:** Python 3.13, Google AI ADK 1.33.0, google-genai ≥1.72, Deno 2.6.7, pytest 8+, Rich
- **GitHub SSOT:** Skills catalog at `https://github.com/ianache/skills-catalog`. Structure: `catalog.yaml` + `skills/<name>/skills.json` (plural) + `skills/<name>/index.ts` + `skills/<name>/SKILL.md`
- **Local cache:** `.skills-cache/` — git clone of the catalog, 5-min TTL, lazy (first skill use), self-healing on delete
- **Routing:** Two-pass — Pass 1 extracts tags with confidence score, Pass 2 injects tool and re-runs when confidence < 0.72
- **Personal use first:** Primary user is the developer (Ilver Anache)

## Constraints

- **Tech stack:** Python 3.13 + Google AI ADK (`google-genai ≥1.72,<2`) — hard upper bound on google-genai (v2 breaks ADK 1.33.0)
- **ADK note:** `FunctionTool` drops `**kwargs` args in ADK 1.33.0 — use `BaseTool` subclass with explicit `_get_declaration()`
- **Execution sandbox:** Deno invoked with `--allow-net=<domain>`, `--allow-read=.skills-cache/`, hard 5000ms timeout — no write access, no V8 escape
- **Windows:** `taskkill /F /T /PID` for process cleanup (no `os.killpg`); always `proc.communicate()` not `proc.wait()` (pipe deadlock on large stdout)
- **GitHub as SSOT:** Catalog and skills live in GitHub; local clone is a cache, not a registry

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Google AI ADK as agent framework | Core requirement; Gemini models + ADK tool-calling | ✓ Works — two-pass routing pattern effective |
| Deno sandbox for TypeScript skills | Security-first: deny-by-default permissions + V8 isolation | ✓ Works — `--allow-net` + `--allow-read` scoped correctly |
| GitHub as skills SSOT + local clone | Zero infra; git clone eliminates URL fragility and per-file HTTP | ✓ Works — `.last-sync` TTL file survives restarts |
| CLI interface for v1 | Fastest path to validate the discovery loop | ✓ Works — Rich spinner + structured error strings |
| `BaseTool` subclass not `FunctionTool` | `FunctionTool` drops `**kwargs` args in ADK 1.33.0 | ✓ Confirmed — `_get_declaration()` explicit schema required |
| `proc.communicate()` never `proc.wait()` | `proc.wait()` deadlocks on large Deno stdout (Windows) | ✓ Confirmed — mandatory pattern |
| Three routing paths not two | `output_schema` always returns JSON, not natural language | ✓ Confirmed — Pass 1 extraction, direct-answer, Pass 2 tool-injected |
| `additionalProperties:false` strip for Gemini | ADK types.Schema rejects extra keys at `_get_declaration()` time | ✓ Fixed post-Phase-5 — required for live E2E |
| `skills.json` plural not `skill.json` | Actual filename in the live catalog returns 404 for singular | ✓ Confirmed — live catalog inspection required |
| `entry_point` field in `skills.json` | Multi-file skills need explicit entry point; defaults to `index.ts` | ✓ Works — `SkillCache` reads field, builds absolute path |

---
*Last updated: 2026-05-17 after v1.0 milestone*
