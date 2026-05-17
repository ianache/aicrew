---
phase: 06-local-skill-cache-git-clone-architecture
plan: "01"
subsystem: infra
tags: [git, asyncio, subprocess, pathlib, skill-cache, config]

# Dependency graph
requires:
  - phase: 05-cli-entry-point-end-to-end-validation
    provides: Config dataclass and complete v1 pipeline — Config extended here
provides:
  - src/skill_cache.py — SkillCache class with git clone lifecycle management
  - src/config.py — Config extended with skills_cache_dir and skills_cache_ttl fields
  - tests/test_skill_cache.py — 8 TDD unit tests (mocked subprocess)
affects:
  - 06-02 — catalog refactor that wires SkillCache into CatalogExplorer
  - 06-03 — skill_injector refactor that reads skills from local cache path

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD RED→GREEN flow: 8 tests written first (ImportError), then implementation"
    - "asyncio.create_subprocess_exec with communicate() for git clone/pull — never wait()"
    - "File-based TTL sync via .last-sync float timestamp"
    - "Partial-clone guard: shutil.rmtree before re-clone when cache_dir exists without .git/"
    - "Soft-fail pull: non-zero exit or TimeoutError returns stale cache, no RuntimeError"

key-files:
  created:
    - src/skill_cache.py
    - tests/test_skill_cache.py
  modified:
    - src/config.py
    - .gitignore
    - tests/conftest.py
    - tests/test_catalog_explorer.py
    - tests/test_e2e.py

key-decisions:
  - "SkillCache.mkdir() before _write_sync_timestamp() — real git creates cache_dir itself but mocked subprocess does not; mkdir(parents=True, exist_ok=True) unifies both paths"
  - "skills_cache_dir and skills_cache_ttl added as required (not Optional) Config fields — all callers updated rather than using dataclass field(default=…) to preserve fail-fast pattern"
  - "GITHUB_TOKEN not passed to git subprocess — catalog repo is public; token stays for legacy HTTP fetch only (REPO-03 confirmed)"

patterns-established:
  - "TDD: all test_skill_cache.py tests mock asyncio.create_subprocess_exec via patch() — no real network or git calls in unit tests"
  - "Soft-fail on pull: only RuntimeError on clone (no cache fallback); pull errors silently ignored"

requirements-completed:
  - REPO-01
  - REPO-03

# Metrics
duration: 4min
completed: 2026-05-17
---

# Phase 6 Plan 01: SkillCache TDD and Config Extension Summary

**SkillCache git clone lifecycle manager with TTL-based sync — lazy clone on first use, pull on expiry, partial-clone guard, and soft-fail on network errors**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-17T18:35:16Z
- **Completed:** 2026-05-17T18:39:04Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- SkillCache class in src/skill_cache.py with full git clone lifecycle (clone, TTL-based pull, partial-clone guard, soft-fail)
- 8 TDD unit tests all passing — written RED first (ImportError), then GREEN implementation
- Config extended with skills_cache_dir: Path and skills_cache_ttl: int — from_env() reads SKILLS_CACHE_DIR / SKILLS_CACHE_TTL env vars with defaults
- .gitignore updated with .skills-cache/ entry
- Full non-live suite: 65 passed, 4 deselected (live), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: SkillCache TDD — write failing tests then implement** - `4c7033b` (feat)
2. **Task 2: Config extension + .gitignore update** - `d87ae63` (feat)

_Note: TDD tasks have a single combined commit (RED+GREEN, no separate refactor needed)_

## Files Created/Modified
- `src/skill_cache.py` — SkillCache class: ensure_synced(), _clone(), _pull(), _needs_clone(), _needs_pull(), _write_sync_timestamp()
- `tests/test_skill_cache.py` — 8 unit tests with mocked asyncio.create_subprocess_exec
- `src/config.py` — Config dataclass extended with skills_cache_dir: Path and skills_cache_ttl: int; from_env() reads new env vars
- `.gitignore` — .skills-cache/ entry added
- `tests/conftest.py` — sample_config fixture updated with new required Config fields
- `tests/test_catalog_explorer.py` — local Config fixtures updated with new required fields
- `tests/test_e2e.py` — config_stub fixture updated with new required fields

## Decisions Made
- `SkillCache._clone()` calls `cache_dir.mkdir(parents=True, exist_ok=True)` before `_write_sync_timestamp()` — real git clone creates the directory, but the mocked subprocess path in tests does not; explicit mkdir unifies both paths without requiring test-specific logic.
- Config fields are required (not Optional with defaults) — preserves the fail-fast dataclass pattern established in Phase 1; all 3 test files with local Config constructors updated as Rule 1 auto-fixes.
- GITHUB_TOKEN explicitly NOT passed to git subprocess — skills-catalog repo is public; existing token field in Config stays for legacy httpx fetch compatibility only.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] cache_dir not created when subprocess is mocked**
- **Found during:** Task 1 (GREEN phase — first test run after creating skill_cache.py)
- **Issue:** `_write_sync_timestamp()` tried to write `.last-sync` into `cache_dir` which doesn't exist when `asyncio.create_subprocess_exec` is mocked (real git clone creates the directory, mock does not)
- **Fix:** Added `self._cache_dir.mkdir(parents=True, exist_ok=True)` in `_clone()` before the subprocess call — both real and mocked paths now work
- **Files modified:** src/skill_cache.py
- **Verification:** 3 failing tests (test_ensure_synced_clones_when_git_absent, test_last_sync_written_after_clone, test_partial_clone_guard) turned green
- **Committed in:** 4c7033b (Task 1 commit)

**2. [Rule 1 - Bug] Config constructor calls missing new required fields**
- **Found during:** Task 2 (full non-live suite run after Config extension)
- **Issue:** test_catalog_explorer.py (config_with_token, config_no_token, live_config fixtures) and test_e2e.py (config_stub fixture) all had Config() constructors without the new skills_cache_dir and skills_cache_ttl fields — 14 test errors
- **Fix:** Added `skills_cache_dir=Path(".skills-cache"), skills_cache_ttl=300` to each fixture; also updated tests/conftest.py sample_config fixture
- **Files modified:** tests/test_catalog_explorer.py, tests/test_e2e.py, tests/conftest.py
- **Verification:** 65 passed, 4 deselected (live), 0 errors
- **Committed in:** d87ae63 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both auto-fixes necessary for correctness. No scope creep — all fixes in files directly modified by this plan.

## Issues Encountered
None beyond the two auto-fixed deviations above.

## User Setup Required
None — no external service configuration required. .skills-cache/ is gitignored; the directory is created at runtime on first use.

## Next Phase Readiness
- SkillCache is production-ready and fully tested
- Config.skills_cache_dir and Config.skills_cache_ttl available for 06-02 CatalogExplorer refactor
- REPO-01 and REPO-03 requirements satisfied
- Ready to wire SkillCache into CatalogExplorer in plan 06-02

---
*Phase: 06-local-skill-cache-git-clone-architecture*
*Completed: 2026-05-17*
