---
phase: 06-local-skill-cache-git-clone-architecture
plan: "02"
subsystem: infra
tags: [git, pathlib, skill-cache, catalog-explorer, skill-injector, deno, httpx-removal]

# Dependency graph
requires:
  - phase: 06-local-skill-cache-git-clone-architecture
    plan: "01"
    provides: SkillCache class with git clone lifecycle + Config.skills_cache_dir/skills_cache_ttl
provides:
  - src/catalog_explorer.py — CatalogExplorer refactored to read catalog.yaml and skills.json from local git clone via SkillCache
  - src/skill_injector.py — _fetch_skill_md reads local SKILL.md via pathlib; run_async passes --allow-read to DenoRunner
  - main.py — SkillCache constructed and injected into CatalogExplorer dependency chain
affects:
  - 06-03 — test fixture updates for CatalogExplorer(config, skill_cache) constructor and local path contract

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Local file reads via pathlib.Path.read_text() replace all httpx HTTP fetches in routing path"
    - "cache_root derived from SkillDefinition.path via Path.parents[2] — .skills-cache/ is always 3 levels up from the .ts file"
    - "IndexError guard on Path.parents[2] for bare skill names in tests (parents[2] raises IndexError)"
    - "--allow-read={cache_root.as_posix()} passed as extra_flag to DenoRunner for local .ts execution"

key-files:
  created: []
  modified:
    - src/catalog_explorer.py
    - src/skill_injector.py
    - main.py

key-decisions:
  - "SkillDefinition.path is absolute local .ts path (not a URL) — Phase 6 contract; CatalogExplorer sets path=str(skill_dir / entry_point)"
  - "cache_root = Path(skill_def.path).parents[2] — the .skills-cache/ root is always 3 path levels above the .ts entry point (.skills-cache/skills/<name>/index.ts)"
  - "IndexError guard (try/except) on parents[2] call — bare skill names (e.g. 'evaluar_test_case') have insufficient path depth; returns empty extra_flags for backward compat"
  - "_log_error parameter renamed from url to source; JSONL key stays 'url' for backward compat with log parsers"

patterns-established:
  - "Zero HTTP in routing/execution path: all catalog.yaml, skills.json, SKILL.md reads now via local pathlib calls"
  - "Soft-fail chain: SkillCache.ensure_synced() → Path.read_text() → SkillDefinition; each level returns None/[] on failure, never raises"

requirements-completed:
  - REPO-02
  - REPO-04

# Metrics
duration: 4min
completed: 2026-05-17
---

# Phase 6 Plan 02: CatalogExplorer + SkillInjector Local Path Refactor Summary

**HTTP-free skill routing: CatalogExplorer reads catalog.yaml and skills.json from local git clone via SkillCache; SkillInjector reads SKILL.md via pathlib and passes --allow-read to Deno subprocess**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-17T18:40:00Z
- **Completed:** 2026-05-17T18:44:05Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- CatalogExplorer fully ported from httpx to local file reads — no HTTP in the skill routing path
- SkillDefinition.path is now an absolute local .ts path (was a raw.githubusercontent.com URL)
- SkillInjector reads SKILL.md from the local clone via pathlib (no httpx, no URL construction)
- DenoRunner receives `--allow-read={cache_root}` so Deno can access local .ts files
- main.py wires SkillCache(repo_url, cache_dir, ttl_seconds) and injects it into CatalogExplorer
- 38 non-live tests still pass (test_skill_cache + test_agent + test_deno_runner + TestNormalizeSchema)

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor CatalogExplorer — local file reads via SkillCache** - `01691a2` (feat)
2. **Task 2: Refactor SkillInjector — local SKILL.md + --allow-read flag** - `68898f2` (feat)

## Files Created/Modified
- `src/catalog_explorer.py` — Removed httpx import and _BASE_URL; added SkillCache import; __init__ takes skill_cache: SkillCache; _fetch_catalog_yaml and _fetch_skill_json use pathlib local reads; SkillDefinition.path is absolute .ts path
- `src/skill_injector.py` — Removed httpx import; added pathlib.Path import; _fetch_skill_md reads Path(path).parent/"SKILL.md"; run_async derives cache_root from parents[2] and passes --allow-read to DenoRunner
- `main.py` — Added SkillCache import; constructs SkillCache(repo_url, config.skills_cache_dir, config.skills_cache_ttl); passes skill_cache to CatalogExplorer constructor

## Decisions Made
- SkillDefinition.path is set to `str(skill_dir / entry_point)` — an absolute Windows path — establishing the Phase 6 local path contract that all downstream layers depend on
- cache_root derived from `Path(skill_def.path).parents[2]` because the layout is `.skills-cache/skills/<skill_name>/index.ts`, so `parents[2]` is always `.skills-cache/`
- IndexError guard around `parents[2]` preserves backward compatibility for test fixtures that use bare skill names (short paths with fewer than 3 components)
- `_log_error` first parameter renamed from `url` to `source` (more accurate naming); JSONL record key remains `"url"` for backward compat with existing log parsers

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
None — both tasks completed on first attempt, all verifications passed.

## User Setup Required
None — changes are internal refactors. Runtime behavior is identical; the only user-visible difference is that skills are now executed from local .ts files instead of GitHub URLs.

## Next Phase Readiness
- REPO-02 satisfied: zero HTTP calls during routing/execution path (catalog.yaml, skills.json, SKILL.md all local)
- REPO-04 satisfied: Deno executes local .ts files with --allow-read flag
- Ready for Plan 06-03: test fixture updates (CatalogExplorer constructor change, local path contract)
- test_catalog_explorer.py and test_skill_injector.py (non-normalize tests) are expected to fail until 06-03 updates their fixtures

---
*Phase: 06-local-skill-cache-git-clone-architecture*
*Completed: 2026-05-17*
