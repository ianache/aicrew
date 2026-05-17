# Phase 2: Skill Injection Bridge - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `SkillInjector` — the bridge that converts a `SkillDefinition` (parsed from `skill.json`) into a live ADK `FunctionTool`. Validates LLM-supplied parameters against JSON Schema before delegating to `DenoRunner`. Fetches and returns `SKILL.md` content for agent context injection. This phase establishes the ADK integration point; nothing is wired end-to-end until Phase 5.

</domain>

<decisions>
## Implementation Decisions

### Validation failure response (INJS-02)
- Missing/invalid parameters return a **Pydantic model**: `ValidationCorrectionRequest`
- Fields: `missing_fields: list[str]`, `extra_fields: list[str]` (unexpected fields), `message: str` (human-readable)
- Consistent with Pydantic-first pattern from Phase 1 — typed, serializable, testable
- When `DenoRunner.execute()` returns `ExecutionError` or `TimeoutError`, the closure **converts to a string** and returns it to the LLM (e.g., `"Skill execution failed: <stderr>"`, `"Skill timed out after 5000ms"`). No exception propagation — the LLM receives a readable string to report to the user.

### SKILL.md injection mechanism (INJS-03)
- `build_tool()` returns a **tuple**: `(FunctionTool, skill_md: str)`
- Phase 3 takes `skill_md` and appends it to the agent's system instruction for that run
- SKILL.md URL constructed from `skill_def.path`: `raw.githubusercontent.com/ianache/skills-catalog/main/{path}/SKILL.md`
- **Soft fail**: if SKILL.md fetch fails (GitHub down, 404, network error), return `(FunctionTool, "")` — empty string. The tool still executes; cognitive guidance is absent. Phase 3 checks for empty string and skips injection.

### SkillDefinition model ownership (INJS-01)
- `SkillDefinition` defined in **`src/models/skill.py`** alongside `results.py` — zero ADK/Deno dependencies, shared contract
- Minimal fields: `name: str`, `description: str`, `path: str` (e.g., `"skills/evaluar_test_case"`), `input_schema: dict`, `allow_net_domains: list[str]`
- Phase 2 defines a **fresh contract** — Phase 4 verifies that the existing CatalogExplorer produces compatible output (or adapts it). Keeps Phase 2 independently testable without live catalog.
- CatalogExplorer and SkillInjector both import from `src/models/skill.py` (single source of truth)

### FunctionTool fallback strategy (INJS-01)
- **Try primary first**: `FunctionTool(func=_execute)` where `_execute` is an async closure
- **Bake in fallback**: if ADK introspection fails, fall back to a private `_SkillBaseTool(BaseTool)` inner class with explicit `_get_declaration()` returning `types.FunctionDeclaration`
- The fallback class is private — callers never see it. Public interface is always `build_tool() -> tuple[FunctionTool, str]`
- Schema normalization before passing to ADK: inject `additionalProperties: false` if absent, AND strip unsupported keywords (`$schema`, `definitions`, `$defs`, any keyword not in `{type, properties, required, description, additionalProperties}`) — prevents silent ADK schema parsing failures

### Claude's Discretion
- Whether to use `jsonschema.Draft7Validator` or `Draft202012Validator` for INJS-02 validation
- Exact HTTP timeout for SKILL.md fetch
- Whether `ValidationCorrectionRequest` lives in `src/models/skill.py` or `src/models/results.py` (or a new `src/models/validation.py`)
- Exact error message strings returned to the LLM

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/models/results.py`: `ExecutionResult` union — SkillInjector's closure receives this from DenoRunner, converts errors to strings before returning to ADK
- `src/execution/deno_runner.py`: `DenoRunner.execute(skill_path, params, allow_net_domains)` — the callable SkillInjector wraps. Import path: `from src.execution.deno_runner import DenoRunner`
- `httpx` already in `pyproject.toml` dependencies — use for async SKILL.md fetch

### Established Patterns
- Pydantic BaseModel for all typed contracts (set by Phase 1 `results.py`)
- `DenoRunner.execute()` always returns, never raises — SkillInjector closure must follow the same spirit at the FunctionTool level (return strings, not raise to ADK)
- `pyproject.toml` already has `google-adk==1.33.0` — needs to be installed before Phase 2 tests can run

### Integration Points
- `build_tool(skill_def: SkillDefinition) -> tuple[FunctionTool, str]` — Phase 3 (CoordinatingAgent) calls this and receives both the tool and SKILL.md content
- `src/models/skill.py` (new in Phase 2) — shared contract between CatalogExplorer (Phase 4) and SkillInjector
- `jsonschema` not yet in dependencies — must be added to `pyproject.toml` for INJS-02

</code_context>

<specifics>
## Specific Ideas

- CLAUDE.md explicitly warns: "FunctionTool introspection is Phase 2's highest-risk unknown" — the TDD approach should verify the closure works with ADK 1.33.0 before committing to it
- The catalog uses `raw.githubusercontent.com` URLs (not `api.github.com`) — SKILL.md fetch should follow the same CDN-backed pattern for rate-limit safety
- `additionalProperties: false` injection is documented in CLAUDE.md as a required step to prevent LLMs from passing undeclared keys that would slip past JSON Schema validation

</specifics>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-skill-injection-bridge*
*Context gathered: 2026-05-17*
