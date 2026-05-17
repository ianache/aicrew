# Phase 1: Deno Execution Channel - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `DenoRunner` — a Python subprocess runner that invokes TypeScript skill files via Deno with strict permission flags, a hard 5000ms timeout, clean process cleanup, and typed error results. Zero ADK dependency. This component is the isolated execution sandbox that Phase 2 (SkillInjector) will call.

</domain>

<decisions>
## Implementation Decisions

### Skill I/O protocol
- Python passes parameters to the Deno subprocess as JSON written to **stdin**
- TypeScript skills receive input by reading `Deno.stdin` and parsing JSON
- Skills return their result as a **single JSON object written to stdout**
- Stderr is reserved exclusively for error output (not mixed with result)
- If stdout cannot be parsed as valid JSON, DenoRunner returns an `execution_error` — strict contract enforcement, no lenient fallback

### Permission model
- Caller passes `--allow-net` domains explicitly to `DenoRunner.execute()` as a list of domain strings (e.g., `['gitlab.com']`)
- DenoRunner does NOT read `skill.json` internally — it only runs what the caller gives it
- Domain validation uses strict hostname regex before flag construction: `^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$` — rejects IPs, wildcards, paths, ports, and flag injection vectors
- An invalid domain string returns a `validation_failure` before the subprocess is created (no Deno process spawned)
- The caller (Phase 2 SkillInjector) is responsible for specifying all Deno permission flags — DenoRunner does not hardcode any deny flags

### Result type design
- Typed results modeled as **Pydantic models** (already in stack)
- Success: `ExecutionSuccess(data: dict)` — contains the parsed JSON from stdout
- Errors are a discriminated union — each error type carries minimal but diagnostic fields:
  - `TimeoutError(type='timeout', elapsed_ms: int)`
  - `ExecutionError(type='execution_error', exit_code: int, stderr: str)`
  - `ValidationFailure(type='validation_failure', invalid_domain: str)`
- `DenoRunner.execute()` **always returns** `ExecutionSuccess | TimeoutError | ExecutionError | ValidationFailure` — never raises exceptions for execution outcomes
- Callers use `isinstance()` checks, no try/except needed at call sites

### Module structure
- DenoRunner lives at: `src/execution/deno_runner.py`
- Package: `src/execution/__init__.py` (execution channel package — designed to grow with WebAssembly and MCP channels in v2)
- Import path: `from src.execution.deno_runner import DenoRunner`
- Tests at: `tests/execution/test_deno_runner.py` (mirrors src/ structure)
- Test fixtures: `tests/fixtures/skills/echo_skill.ts` — a minimal TS file that reads JSON from stdin and echoes it back; used for timeout, success, and error tests without network dependency

### Claude's Discretion
- Exact process group kill implementation (SIGKILL vs SIGTERM escalation, platform-specific handling)
- asyncio vs subprocess threading model for the subprocess execution
- How to detect zombie processes and verify cleanup in tests
- Exact Pydantic model inheritance hierarchy (base class vs separate models)

</decisions>

<specifics>
## Specific Ideas

- The PRD explicitly calls out "aislamiento V8 con timeouts innegociables de 5000ms" — the timeout is a hard requirement, not configurable in Phase 1
- TC-03 in the PRD acceptance matrix is the target: "The orchestrator kills the process at the strict 5000ms timeout, cleans ephemeral resources, and returns a controlled error to the log without degrading the core"
- Skills in the catalog use `--allow-net=gitlab.com`, `--allow-net=github.com` patterns — the domain list passed by the caller maps directly to a single `--allow-net=domain1,domain2` Deno flag

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- No existing code — greenfield project
- Pydantic already in `requirements.txt` — use for all result models
- `pytest` and `pytest-asyncio` already in stack — async test support ready

### Established Patterns
- No established patterns yet — Phase 1 sets the conventions
- Pydantic usage in results here will set the pattern for the whole codebase

### Integration Points
- Phase 2 (SkillInjector) will call `DenoRunner.execute(skill_path, params, allow_net_domains)` — this is the primary downstream consumer
- The `ExecutionSuccess | ExecutionError` return type will flow up through Phase 2 → Phase 3 routing decisions

</code_context>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-deno-execution-channel*
*Context gathered: 2026-05-17*
