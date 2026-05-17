---
phase: 03-coordinating-agent-two-pass-routing
plan: "01"
subsystem: api
tags: [google-adk, pydantic, routing, jsonl, config, llmagent, runner, session]

# Dependency graph
requires:
  - phase: 02-skill-injection-bridge
    provides: SkillInjector.build_tool() returning (BaseTool, skill_md) tuple
  - phase: 01-deno-execution-channel
    provides: DenoRunner.execute() for skill subprocess execution

provides:
  - "CoordinatingAgent.run(prompt) -> str — confidence-gated two-pass routing"
  - "Config.from_env() — frozen dataclass for all env var reads"
  - "JSONL routing log at logs/routing.jsonl — every decision logged with prompt_hash, tags, confidence, decision, skill_name, ts"
  - "TagExtractionResult — Pydantic model for structured Pass 1 output"

affects:
  - 04-catalog-explorer-integration
  - 05-cli-entry-point-e2e

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-pass LlmAgent routing: Pass 1 with output_schema=TagExtractionResult, Pass 2 with injected tool"
    - "Config frozen dataclass — single env var read point, injected into CoordinatingAgent.__init__"
    - "runner.agent direct attribute swap between passes (verified safe in ADK 1.33.0)"
    - "Fresh InMemorySessionService per run() call — prevents unbounded memory growth"
    - "JSONL log: append-mode open(), json.dumps(record) + newline — one record per run()"
    - "Optional _runner and _session_service constructor params for clean test injection"

key-files:
  created:
    - src/config.py
    - src/agent.py
    - tests/test_agent.py
    - tests/conftest.py
  modified: []

key-decisions:
  - "Three routing paths (not two): Pass 1 extraction, direct-answer LlmAgent (high-confidence), Pass 2 tool-injected (low-confidence) — because Pass 1 with output_schema always returns JSON, not natural language"
  - "Fresh LlmAgent per run() for all paths — never mutate agent.tools between calls (prevents tool carryover across REPL invocations)"
  - "Tag vocabulary injected into Pass 1 instruction per run() after get_all_tags() resolves — constrains structured output to catalog-valid terms (DISC-02)"
  - "Optional _runner/_session_service constructor params — avoids monkey-patching; enables clean test injection without attribute access hacks"
  - "Session state read AFTER async for loop completes — not during iteration (state_delta applied during append_event)"

patterns-established:
  - "Pattern: Always read session.state['routing'] with dict .get() — validate_schema returns dict, not Pydantic instance"
  - "Pattern: include_contents='none' on every LlmAgent — prevents history contamination across passes"
  - "Pattern: One Runner per CoordinatingAgent instance; runner.agent swapped per pass via direct assignment"
  - "Pattern: get_all_tags() called at start of run() to ensure vocabulary constraint is current"

requirements-completed: [DISC-01, DISC-02, RELI-03, RELI-04]

# Metrics
duration: 3min
completed: 2026-05-17
---

# Phase 3 Plan 01: CoordinatingAgent with Config Summary

**LlmAgent two-pass confidence-gated routing with frozen Config dataclass, catalog tag vocabulary constraint, and append-mode JSONL decision log**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-17T07:17:03Z
- **Completed:** 2026-05-17T07:20:00Z
- **Tasks:** 2 (RED + GREEN TDD phases)
- **Files modified:** 4 created

## Accomplishments

- `src/config.py` — frozen Config dataclass reading GEMINI_API_KEY (required), GITHUB_TOKEN, CONFIDENCE_THRESHOLD (default 0.72), MODEL_VERSION (default gemini-2.5-flash-001) from env
- `src/agent.py` — CoordinatingAgent with three routing paths: structured Pass 1 tag extraction, direct-answer LlmAgent for high-confidence prompts, tool-injected Pass 2 LlmAgent for low-confidence prompts; JSONL log appended on every run()
- `tests/test_agent.py` — 10 TDD tests covering all routing paths, JSONL structure/append, tag vocabulary constraint, tool isolation across runs
- `tests/conftest.py` — shared fixtures: sample_skill_def, mock_catalog_explorer, sample_config; available to all test modules
- 38 total tests pass (10 new + 28 from Phases 1+2) — zero regressions

## Task Commits

1. **TDD RED: Add failing test suite for CoordinatingAgent** — `88c77d6` (test)
2. **TDD GREEN: Implement CoordinatingAgent and Config** — `98752e3` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/config.py` — frozen Config dataclass, Config.from_env() classmethod, all 4 fields
- `src/agent.py` — CoordinatingAgent class, run() async method, TagExtractionResult Pydantic model, _write_routing_log() function, _LOG_PATH module constant (monkeypatchable for tests)
- `tests/test_agent.py` — 10 tests in 5 classes: TestConfig, TestCoordinatingAgentRouting, TestRoutingLog, TestPass1Vocabulary, TestToolIsolation
- `tests/conftest.py` — shared fixtures for all test modules

## Decisions Made

- Three routing paths implemented (not two): Pass 1 always does structured extraction; high-confidence prompts get a separate direct-answer LlmAgent (no output_schema, no tools); low-confidence prompts get a tool-injected Pass 2. This is necessary because Pass 1 with output_schema always returns JSON, never natural language (Pitfall 1 from RESEARCH.md).
- Optional `_runner` and `_session_service` constructor parameters added to CoordinatingAgent.__init__ — enables clean test injection without monkey-patching or attribute hacks; tests construct CoordinatingAgent then patch these injected instances directly.
- Tag vocabulary fetched via `get_all_tags()` at the start of each `run()` call — ensures constraint is always current; the Pass 1 LlmAgent's instruction is updated per call (LlmAgent.instruction is a plain attribute, safely mutable).
- `_LOG_PATH` exported as a module-level constant in `src/agent.py` — allows test isolation via `monkeypatch.setattr(agent_module, '_LOG_PATH', tmp_path / 'routing.jsonl')` without needing to refactor logging into a class.

## Deviations from Plan

None — plan executed exactly as written. All architectural decisions and mocking strategies described in the plan matched the implementation without modification.

## Issues Encountered

None — all 10 tests passed on the first GREEN implementation run. The ADK patterns from RESEARCH.md (output_schema, runner.agent swap, session state timing, include_contents='none') worked exactly as documented.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `CoordinatingAgent` is fully tested with stubbed CatalogExplorer — ready for Phase 4 integration
- `Config.from_env()` is in place — Phase 5 CLI entry point can call it directly
- `logs/routing.jsonl` append infrastructure is ready — routing decisions will be visible immediately once real Gemini API calls occur
- Phase 4 must implement `CatalogExplorer` with `find(tags)` and `get_all_tags()` methods matching the duck-typed contract used in Phase 3

---
*Phase: 03-coordinating-agent-two-pass-routing*
*Completed: 2026-05-17*
