---
phase: 01-deno-execution-channel
plan: 02
subsystem: execution
tags: [asyncio, deno, subprocess, timeout, zombie-cleanup, pydantic, tdd, windows]

# Dependency graph
requires:
  - phase: 01-deno-execution-channel/01-01
    provides: "src/models/results.py (ExecutionSuccess, TimeoutError, ExecutionError, ValidationFailure), TypeScript test fixtures (echo_skill.ts, slow_skill.ts), Python package structure"
provides:
  - DenoRunner class in src/execution/deno_runner.py with asyncio subprocess execution
  - Domain validation via _DOMAIN_RE regex before subprocess spawn
  - 5000ms hard timeout with Windows process tree kill (taskkill /F /T /PID)
  - Zombie process prevention via mandatory second await proc.communicate() after kill
  - Full Phase 1 test suite (10 tests) in tests/execution/test_deno_runner.py
affects: [02-skill-injection-bridge, 03-coordinating-agent, all-phases]

# Tech tracking
tech-stack:
  added: [asyncio.create_subprocess_exec, asyncio.wait_for, taskkill (Windows)]
  patterns: [tdd-red-green, never-raise-return-typed, asyncio-subprocess-communicate, process-tree-kill-windows]

key-files:
  created:
    - src/execution/deno_runner.py
    - tests/execution/test_deno_runner.py
  modified:
    - pyproject.toml

key-decisions:
  - "Use asyncio.wait_for(proc.communicate(), timeout=5.0) — never proc.wait() which deadlocks on large stdout"
  - "After timeout kill: mandatory second await proc.communicate() to drain pipes and collect exit code (prevents zombie)"
  - "Domain regex _DOMAIN_RE = r'^[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$' rejects IPs (192.168.x.x) and wildcards (*.example.com)"
  - "Windows-only: taskkill /F /T /PID kills entire process tree; os.killpg POSIX path retained for non-Windows CI"
  - "pyproject.toml fixed: added [project] table and switched build-backend to setuptools.build_meta for uv run compatibility"

patterns-established:
  - "tdd-cycle: write all failing tests first (RED commit), then implement (GREEN commit) — tests verified to import-error before implementation"
  - "subprocess-communicate: always use proc.communicate() with asyncio.wait_for; never proc.wait(); drain pipes after kill"
  - "domain-validation-first: validate all domains before spawning any subprocess — ValidationFailure returned in < 100ms"

requirements-completed: [EXEC-01, EXEC-02]

# Metrics
duration: 3min
completed: 2026-05-17
---

# Phase 1 Plan 02: DenoRunner Summary

**asyncio Deno subprocess runner with 5000ms hard timeout, Windows process-tree kill via taskkill, domain regex validation, and 10-test TDD suite — all Phase 1 success criteria verified**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-17T06:26:42Z
- **Completed:** 2026-05-17T06:29:14Z
- **Tasks:** 2 (RED + GREEN TDD cycles)
- **Files modified:** 3

## Accomplishments
- 10 async test cases written and confirmed failing (RED) before any implementation
- DenoRunner implemented: domain validation, asyncio subprocess, 5000ms timeout, zombie cleanup
- All 10 tests pass (GREEN): success, timeout, zombie, domain validation (IP/wildcard), non-zero exit, invalid JSON, valid domain

## Task Commits

Each task was committed atomically:

1. **Task 1: RED phase — failing test suite** - `a44c38a` (test)
2. **Task 2: GREEN phase — DenoRunner implementation** - `1eeca50` (feat)

**Plan metadata:** (docs: complete plan — committed after this summary)

_Note: TDD plan — RED commit then GREEN commit._

## Files Created/Modified
- `src/execution/deno_runner.py` - DenoRunner class with asyncio subprocess, timeout, domain validation, zombie cleanup
- `tests/execution/test_deno_runner.py` - Full Phase 1 test suite: 10 async tests, no mocks, real Deno subprocesses
- `pyproject.toml` - Added [project] table and fixed build-backend to setuptools.build_meta (Rule 3 deviation)

## Decisions Made
- `proc.communicate()` used exclusively — never `proc.wait()` to avoid pipe deadlock when Deno stdout > ~4KB
- Two-step kill: `_kill_process_tree(proc.pid)` then `await proc.communicate()` (drain) — mandatory for zombie prevention
- `_DOMAIN_RE` pre-compiled at module level, fullmatch used (not match/search) — prevents partial matches like "192.168.1.1extra"
- POSIX fallback retained in `_kill_process_tree()` for non-Windows CI environments

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed pyproject.toml missing [project] table for uv run**
- **Found during:** Task 1 (RED phase — first test run)
- **Issue:** `uv run pytest` requires a `[project]` table in pyproject.toml; Plan 01-01 created pyproject.toml without it. Also, `setuptools.backends.legacy` does not exist in installed setuptools version.
- **Fix:** Added `[project]` table with name, version, requires-python, and dependencies. Changed build-backend from `setuptools.backends.legacy:build` to `setuptools.build_meta`.
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run pytest` successfully created venv, installed 122 packages, and ran tests
- **Committed in:** `a44c38a` (Task 1 RED phase commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Fix necessary for test runner to function. No scope creep — pyproject.toml already existed from Plan 01-01.

## Issues Encountered
- pyproject.toml lacked `[project]` table required by uv run. Fixed inline during RED phase (Rule 3). All planned tests proceeded normally after fix.

## User Setup Required
None - no external service configuration required. Deno must be on PATH (already verified in Plan 01-01 setup).

## Next Phase Readiness
- `src/execution/deno_runner.py` fully implements EXEC-01 and EXEC-02 requirements
- All 10 Phase 1 tests pass; `uv run pytest tests/execution/` exits with code 0
- Phase 2 (Skill Injection Bridge) can begin: `src/skill_injector.py` depends on `DenoRunner` + result models — both now available
- Zero deno.exe zombie processes confirmed after test suite completes

---
*Phase: 01-deno-execution-channel*
*Completed: 2026-05-17*
