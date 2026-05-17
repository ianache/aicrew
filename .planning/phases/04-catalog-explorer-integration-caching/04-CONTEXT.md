# Phase 4: CatalogExplorer Integration + Caching - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement `src/catalog_explorer.py` — fetches `catalog.yaml` from GitHub via `raw.githubusercontent.com`, filters skills by tag intersection, lazy-loads `skill.json` per matched skill, provides a 5-min TTL in-memory cache, and supports `GITHUB_TOKEN` Bearer auth. Exposes two methods: `find(tags)` and `get_all_tags()`. CLI, agent wiring, and E2E tests are Phase 5.

</domain>

<decisions>
## Implementation Decisions

### GitHub failure behavior
- Any failure (network error, non-200 response, 4xx, 5xx) is treated equally — no distinction between connection errors and HTTP errors
- `find()` returns `None` on failure; `get_all_tags()` returns `[]` on failure
- Failures are logged to `logs/routing.jsonl` with `type='catalog_error'` (same log file as routing decisions)
- The agent proceeds silently as if no skill matched — no GitHub details exposed to the user

### Tag matching semantics
- **OR logic**: a skill matches if ANY of the extracted tags appear in the skill's tag list
- **Best match wins**: when multiple skills qualify, the one with the most overlapping tags is returned; ties broken by catalog order
- `find()` returns `None` if no skill matches any extracted tag
- Filtering is tag-only — `catalog.yaml` entries are trusted; no validation of `skill.json` fields before returning

### get_all_tags() data source
- Tags come from `catalog.yaml` only — no additional `skill.json` fetches
- `get_all_tags()` triggers the same catalog fetch as `find()` and shares the 5-min cache
- Returns deduplicated tags sorted **alphabetically**
- Returns `[]` on fetch failure (Pass 1 proceeds without vocabulary constraint)

### Rate limits & auth
- `GITHUB_TOKEN` passed as `Authorization: Bearer {token}` header to `raw.githubusercontent.com`
- Rate-limit responses (403/429) treated the same as any other failure — logged to JSONL, return `None`/`[]`
- No special-casing for rate-limit status codes
- `CatalogExplorer` accepts a `Config` object in its constructor (consistent with `CoordinatingAgent` and `SkillInjector`)

### Claude's Discretion
- Internal cache data structure (dict, dataclass, etc.)
- Whether to use a single shared `httpx.AsyncClient` or per-request clients
- Exact `catalog.yaml` schema parsing details (key names, list structure)
- `asyncio.gather` concurrency implementation for multi-candidate skill.json fetches

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/config.py` — `Config` dataclass with `github_token: str | None` field; inject via constructor
- `src/models/skill.py` — `SkillDefinition` is the exact return type for `find()`; fields: `name`, `description`, `path`, `input_schema`, `allow_net_domains`
- `logs/routing.jsonl` — existing log target; `catalog_error` entries join routing decision entries in this file

### Established Patterns
- Constructor injection: all components (`CoordinatingAgent`, `SkillInjector`) receive `Config` as a constructor argument — follow this pattern
- Duck-typed interface: `CoordinatingAgent` calls `catalog_explorer.find(tags: list[str])` and `catalog_explorer.get_all_tags()` — these signatures are locked
- JSONL logging: `agent.py` uses `open(_LOG_PATH, 'a')` for append-mode logging to `logs/routing.jsonl`

### Integration Points
- `CoordinatingAgent.__init__` accepts `catalog_explorer` as first positional arg (duck-typed, no ABC) — `CatalogExplorer` must expose `find()` and `get_all_tags()`
- URL base: `raw.githubusercontent.com/ianache/skills-catalog/main/` — catalog.yaml at root, skill.json at `skills/{name}/skill.json`
- CLAUDE.md: tests hit the live GitHub repo (`https://github.com/ianache/skills-catalog`) — no mocks per project decision

</code_context>

<specifics>
## Specific Ideas

- No specific references — standard httpx async patterns apply

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-catalog-explorer-integration-caching*
*Context gathered: 2026-05-17*
