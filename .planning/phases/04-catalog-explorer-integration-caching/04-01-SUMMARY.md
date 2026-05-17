---
phase: 04-catalog-explorer-integration-caching
plan: "01"
subsystem: discovery
tags: [httpx, pyyaml, ttl-cache, github, catalog, tdd]

# Dependency graph
requires:
  - phase: 03-coordinating-agent-two-pass-routing
    provides: "CoordinatingAgent duck-typed contract: find(tags) -> SkillDefinition | None, get_all_tags() -> list[str]"
provides:
  - "CatalogExplorer.find(tags: list[str]) -> SkillDefinition | None — live GitHub skill discovery with tag/description matching"
  - "CatalogExplorer.get_all_tags() -> list[str] — sorted, deduplicated tag vocabulary for Pass 1 LLM constraint"
  - "_catalog_cache: 5-minute monotonic TTL cache; empty/failed fetches never cached"
  - "Soft-catching of all GitHub failures; catalog_error records written to logs/routing.jsonl"
affects:
  - 05-cli-entry-point-e2e

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TTL cache: tuple[float, list[dict]] | None — expiry stored as monotonic timestamp, only populated on non-empty success"
    - "Soft-catch pattern: find()/get_all_tags() never raise — all exceptions produce None/[] and a log record"
    - "Description-word fallback: when catalog entries lack 'tags' field, words from description and name are used for matching"
    - "skills.json (plural) file convention: skill metadata in skills/<path>/skills.json, first tool provides input_schema"

key-files:
  created:
    - src/catalog_explorer.py
    - tests/test_catalog_explorer.py
  modified: []

key-decisions:
  - "04-01: skills.json (plural) is the correct skill metadata filename — skill.json (singular) returns 404 in the live catalog"
  - "04-01: catalog.yaml has no 'tags' field per entry — _best_match falls back to description-word matching for tag overlap scoring"
  - "04-01: live_config fixture loads .env via python-dotenv and uses placeholder GEMINI_API_KEY — CatalogExplorer tests only hit GitHub, not Gemini"
  - "04-01: get_all_tags() returns description-word vocabulary when explicit tags absent — preserves CoordinatingAgent Pass 1 tag-vocabulary contract"

patterns-established:
  - "Catalog error logging: synchronous append-mode JSON lines to logs/routing.jsonl with type='catalog_error', url, reason, ts fields"
  - "Skill path is bare name (no 'skills/' prefix) — prefix added at URL construction time in _fetch_skill_json"

requirements-completed: [DISC-03, DISC-04, RELI-01, RELI-02]

# Metrics
duration: 5min
completed: 2026-05-17
---

# Phase 4 Plan 1: CatalogExplorer Summary

**CatalogExplorer with 5-minute TTL cache, description-word tag matching, Authorization: Bearer header injection, and soft-caught GitHub failures logged to routing.jsonl**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-17T13:44:23Z
- **Completed:** 2026-05-17T13:49:23Z
- **Tasks:** 2 (RED test suite + GREEN implementation)
- **Files modified:** 2

## Accomplishments

- CatalogExplorer class with `find()` and `get_all_tags()` satisfying the duck-typed CoordinatingAgent contract
- 5-minute monotonic TTL cache for catalog.yaml — empty/failed results never cached (Pitfall 2 from RESEARCH.md)
- Description-word fallback matching when catalog entries lack explicit `tags` field (actual live catalog structure)
- Authorization: Bearer header injection when `github_token` is set in Config
- All GitHub failures (non-200, network exception) are soft-caught and logged as `catalog_error` records to `logs/routing.jsonl`
- 16 new tests pass alongside 38 prior tests (54 total)

## Task Commits

1. **RED — failing test suite for CatalogExplorer** - `bee2bab` (test)
2. **GREEN — CatalogExplorer implementation** - `b86cb2e` (feat)

## Files Created/Modified

- `src/catalog_explorer.py` — CatalogExplorer class: _fetch_catalog_yaml, _get_catalog (TTL cache), _best_match (OR logic + description fallback), _fetch_skill_json, find, get_all_tags, _auth_headers, _log_error
- `tests/test_catalog_explorer.py` — 16 tests: TTL cache (3), tag matching (4), live GitHub find() (3), get_all_tags() (3), auth headers (2), error logging (1)

## Decisions Made

- **skills.json (plural) not skill.json:** The live `ianache/skills-catalog` repo stores skill metadata in `skills/<path>/skills.json`. The plan referenced `skill.json` (singular) which returns 404. Confirmed via GitHub API directory listing before writing any code.
- **Description-word fallback for tag matching:** The `catalog.yaml` file has no `tags` field per skill entry (only `name`, `description`, `version`, `status`, `path`, `author`). `_best_match` falls back to extracting words from `description` and `name` fields when no explicit `tags` key is present. This makes `find(["calculator"])` return the calculator skill and `get_all_tags()` return a non-empty vocabulary.
- **live_config fixture loads dotenv independently:** Tests hit live GitHub but not Gemini. The `live_config` fixture calls `load_dotenv()` and constructs `Config` directly with a placeholder `gemini_api_key`, avoiding a `KeyError` when no `.env` file exists in the CI/test environment.
- **First tool in tools[] provides SkillDefinition fields:** The `skills.json` structure wraps tools in an array (`{"tools": [{"name": ..., "input_schema": ...}]}`). `_fetch_skill_json` extracts the first tool's `input_schema` (or `parameters` as fallback) for the `SkillDefinition`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected skill file path from `skill.json` to `skills.json`**
- **Found during:** Pre-implementation live catalog inspection
- **Issue:** The plan specified `skills/<name>/skill.json` but live GitHub returns 404 for that path; actual filename is `skills.json` (plural)
- **Fix:** `_fetch_skill_json` constructs URL as `{_BASE_URL}/skills/{skill_path}/skills.json`
- **Files modified:** `src/catalog_explorer.py`
- **Verification:** `uv run python -c ...` fetch of `skills/calculator/skills.json` returns HTTP 200 with valid JSON
- **Committed in:** b86cb2e (feat task commit)

**2. [Rule 1 - Bug] Replaced tag matching with description-word fallback**
- **Found during:** Pre-implementation live catalog inspection
- **Issue:** Plan assumed catalog entries have a `tags: [...]` field; live catalog has no such field — all entries only have `name`, `description`, `version`, `status`, `path`, `author`
- **Fix:** `_best_match` checks for explicit `tags` key first; if absent, extracts words from `description` and `name` (case-insensitive) for overlap scoring
- **Files modified:** `src/catalog_explorer.py`, `tests/test_catalog_explorer.py` (added `test_description_fallback_matching`)
- **Verification:** `find(["calculator"])` returns `SkillDefinition` for calculator skill in live test
- **Committed in:** b86cb2e (feat task commit)

**3. [Rule 1 - Bug] Adapted `get_all_tags()` to use description words when no tags field**
- **Found during:** Pre-implementation live catalog inspection
- **Issue:** Plan assumed `get_all_tags()` collects from `tags` field; live catalog has no tags field, so sorted([]) would always return [] — breaking Pass 1 vocabulary injection in CoordinatingAgent
- **Fix:** When no skill has a `tags` field, `get_all_tags()` extracts words (>2 chars) from all descriptions and names as the tag vocabulary
- **Files modified:** `src/catalog_explorer.py`
- **Verification:** Live test `test_get_all_tags_returns_sorted_deduplicated` returns non-empty sorted list
- **Committed in:** b86cb2e (feat task commit)

**4. [Rule 1 - Bug] Adapted `find(["agile"])` test to use `["calculator"]`**
- **Found during:** Writing RED tests
- **Issue:** Plan test `find(["agile"])` cannot return a SkillDefinition when no catalog skill mentions "agile" in name or description
- **Fix:** Test uses `find(["calculator"])` which matches the calculator skill via description-word matching
- **Files modified:** `tests/test_catalog_explorer.py`
- **Verification:** `test_find_returns_skill_definition_on_tag_match` passes with live GitHub
- **Committed in:** bee2bab (test commit), b86cb2e (feat commit)

---

**Total deviations:** 4 auto-fixed (4 Rule 1 bugs from plan-vs-reality catalog structure mismatch)
**Impact on plan:** All auto-fixes necessary for correctness against the live catalog. The plan was written against an assumed catalog structure; actual structure differs but the interface contract (find/get_all_tags) is fully satisfied.

## Issues Encountered

- `skills.json` (plural) vs `skill.json` — discovered before writing any code via live GitHub API inspection; no rework needed
- No `.env` file in the execution environment — the `live_config` fixture was adapted to avoid requiring `GEMINI_API_KEY` for catalog-only tests

## User Setup Required

None — no external service configuration required beyond what Phase 1 already needed.

## Next Phase Readiness

- `CatalogExplorer` satisfies the duck-typed contract expected by `CoordinatingAgent` in `agent.py`
- `find()` and `get_all_tags()` are ready for wiring into Phase 5 E2E test
- One concern: the `skills.json` `tools` array structure means `SkillDefinition.input_schema` only captures the first tool — multi-tool skills lose their additional tools at this layer. Acceptable for v1 scope.

---
*Phase: 04-catalog-explorer-integration-caching*
*Completed: 2026-05-17*
