---
phase: 02-skill-injection-bridge
plan: "02"
subsystem: skill-injection
tags: [adk, baseTool, jsonschema, httpx, pydantic, schema-normalization, tdd]

requires:
  - phase: 02-skill-injection-bridge/02-01
    provides: SkillDefinition and ValidationCorrectionRequest Pydantic models
  - phase: 01-deno-execution-channel
    provides: DenoRunner.execute(), ExecutionResult union type variants

provides:
  - SkillInjector class with async build_tool(skill_def) -> tuple[BaseTool, str]
  - _SkillBaseTool ADK BaseTool subclass with _get_declaration() and run_async()
  - _normalize_schema() recursive JSON Schema cleaner for ADK compatibility
  - _fetch_skill_md() async httpx fetcher with soft-fail for GitHub catalog SKILL.md

affects:
  - 03-coordinating-agent (CoordinatingAgent injects tool from SkillInjector.build_tool)
  - 04-catalog-explorer (CatalogExplorer.find() returns SkillDefinition consumed by build_tool)

tech-stack:
  added: []
  patterns:
    - "ADK BaseTool subclass pattern (not FunctionTool) for explicit schema control via _get_declaration()"
    - "Schema-based validation: missing_fields and extra_fields computed directly, not from jsonschema e.path"
    - "Soft-fail async fetch: _fetch_skill_md returns '' on any exception or non-200 status"
    - "additionalProperties:false injected only on object schemas (type:object or has properties key)"

key-files:
  created:
    - src/skill_injector.py
    - tests/test_skill_injector.py
  modified: []

key-decisions:
  - "Used BaseTool subclass (not FunctionTool) — FunctionTool drops all args for **kwargs closures in ADK 1.33.0"
  - "additionalProperties:false injected only on object schemas — non-object sub-schemas (string, integer) must not receive it (ADK types.Schema rejects it)"
  - "Missing/extra field validation computed directly from schema, not from jsonschema e.path — required validator errors do not reliably populate e.path"
  - "ValidationCorrectionRequest returned as .model_dump() dict — not as Pydantic object — for consistent ADK serialization"
  - "build_tool() is async def — httpx.AsyncClient used for SKILL.md fetch, no asyncio.run() nesting"
  - "SKILL.md fetch uses real GitHub HTTP in tests (per CLAUDE.md policy); DenoRunner mocked with AsyncMock to avoid subprocess overhead"

patterns-established:
  - "TDD RED/GREEN cycle: write all tests first (import fails), implement until all pass"
  - "BaseTool._get_declaration() as explicit ADK integration point — avoids FunctionTool introspection pitfall"
  - "Schema normalization before types.Schema.model_validate() is mandatory — raw skill.json may have $schema, definitions, examples"

requirements-completed: [INJS-01, INJS-02, INJS-03]

duration: 3min
completed: 2026-05-17
---

# Phase 2 Plan 02: SkillInjector Summary

**ADK BaseTool subclass with recursive JSON Schema normalization, Draft7Validator field checking, and soft-fail SKILL.md fetch from GitHub skills catalog**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-17T06:59:55Z
- **Completed:** 2026-05-17T07:02:55Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `tests/test_skill_injector.py` with 18 TDD tests covering all behaviors: schema normalization, BaseTool declaration, run_async validation paths, execution result dispatch, and build_tool SKILL.md fetch
- Created `src/skill_injector.py` with `_normalize_schema()`, `_fetch_skill_md()`, `_SkillBaseTool(BaseTool)`, and `SkillInjector` — full implementation passing all 18 tests
- Zero regressions: all 10 Phase 1 DenoRunner tests still pass (28 total, 0 failures)
- Auto-fixed one bug during GREEN phase: `additionalProperties:false` scoped to object schemas only — non-object property sub-schemas (type:string, etc.) must not receive the key

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — Write failing test suite for SkillInjector** - `8ab1d63` (test)
2. **Task 2: GREEN — Implement SkillInjector until all tests pass** - `93db2e3` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/skill_injector.py` — SkillInjector, _SkillBaseTool, _normalize_schema, _fetch_skill_md; ~170 lines of implementation + docstrings
- `tests/test_skill_injector.py` — 18 TDD tests in 3 classes (TestNormalizeSchema, TestSkillBaseTool, TestSkillInjectorBuildTool); ~220 lines

## Decisions Made

- **BaseTool subclass over FunctionTool:** FunctionTool in ADK 1.33.0 drops all args for `**kwargs` closures — BaseTool with explicit `_get_declaration()` avoids this pitfall entirely
- **Direct schema computation for validation:** `missing_fields = [f for f in required if f not in args]` instead of `jsonschema e.path` — jsonschema's required validator does not reliably populate `e.path` for required field errors
- **additionalProperties:false scoped to object schemas only:** Non-object sub-schemas cannot have this key per ADK's `types.Schema` model (Pydantic extra='forbid'). Auto-fixed during GREEN phase.
- **SKILL.md soft-fail:** `_fetch_skill_md` returns `""` on any exception or non-200 status — tool remains usable even when GitHub is unreachable
- **Real HTTP in build_tool tests:** Tests 16-18 hit the live `ianache/skills-catalog` GitHub repo per CLAUDE.md policy ("no mocks" for catalog fetches)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] additionalProperties:false injection scoped to object schemas only**
- **Found during:** Task 2 (GREEN — implementing _normalize_schema)
- **Issue:** Initial implementation injected `additionalProperties:false` on every schema node during recursion, including non-object sub-schemas (e.g. `{"type": "string"}`). Test 5 (test_preserves_allowed_keys) failed: `items: {"type": "string"}` became `{"type": "string", "additionalProperties": false}` which doesn't match the expected `{"type": "string"}`. Also, ADK's `types.Schema` with `extra='forbid'` rejects `additionalProperties` on non-object schemas.
- **Fix:** Added `is_object_schema = result.get("type") == "object" or "properties" in result` guard — injection only happens when the schema describes an object. Non-object schemas recurse (to strip examples etc.) but do not receive the injection.
- **Files modified:** `src/skill_injector.py`
- **Verification:** All 18 tests pass after fix; idempotency test (Test 6) confirms no double-injection
- **Committed in:** `93db2e3` (Task 2 / GREEN phase commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Fix essential for ADK compatibility and test correctness. No scope creep.

## Issues Encountered

None beyond the auto-fixed deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `from src.skill_injector import SkillInjector` is ready for Phase 3 (CoordinatingAgent)
- `SkillInjector(runner).build_tool(skill_def)` returns `(BaseTool, str)` — tool injected into ADK agent, skill_md appended to system instruction
- `_normalize_schema` and `_SkillBaseTool` are private; only `SkillInjector` is the public API
- Phase 1 regression confirmed: 10/10 DenoRunner tests still pass

---
*Phase: 02-skill-injection-bridge*
*Completed: 2026-05-17*
