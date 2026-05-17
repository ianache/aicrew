# Phase 6: Local Skill Cache — Git Clone Architecture - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace all per-file HTTP fetches (httpx in CatalogExplorer, SkillInjector, DenoRunner) with reads
from a managed local git clone of the skills catalog. A new `src/skill_cache.py` module manages
the clone lifecycle. CatalogExplorer, SkillInjector, and DenoRunner are updated to read from
local filesystem paths. SkillDefinition.path transitions from a remote URL to a local absolute path.

Out of scope: new skills, new skill types, new Deno permission types beyond what Phase 6 requires.

</domain>

<decisions>
## Implementation Decisions

### Cache sync strategy
- **Lazy clone**: git clone happens on first skill use (when CatalogExplorer.find() is called),
  NOT at REPL startup. Startup remains instant.
- **TTL**: 5 minutes — matches the current in-memory HTTP catalog TTL exactly (no behavioral regression)
- **Staleness detection**: `.skills-cache/.last-sync` file — written after each successful clone or pull;
  read on startup to compare age against TTL. Survives process restarts. Deleted along with the cache
  dir if the user wants a fresh clone.
- **Self-healing**: if `.skills-cache/` is deleted, the next skill lookup triggers a fresh clone automatically

### Git authentication
- **No token for git operations**: The skills catalog (`github.com/ianache/skills-catalog`) is a public
  repo — `git clone https://github.com/ianache/skills-catalog` works without credentials.
- GITHUB_TOKEN stays in Config for HTTP fetch paths only (not passed to git subprocess)
- `.skills-cache/` is gitignored (runtime artifact, like `.venv/`). Add to `.gitignore`.

### Failure behavior
- **First clone fails** (network down, git not on PATH): SkillCache raises → CatalogExplorer catches →
  `find()` returns None. Logs a `catalog_error` record to routing.jsonl. Agent tells user no skill found.
  Consistent with current HTTP failure behavior (no new exception surface).
- **git pull fails with stale cache present** (transient network issue): use existing clone, log a
  `catalog_error` warning to routing.jsonl. Don't update `.last-sync` (so next run retries pull).
  Agent continues working with potentially stale skills.
- No HTTP fallback — removes the complexity of dual code paths.

### Multi-file skill contract
- **`--allow-read=.skills-cache/`** added to Deno flags for every skill execution. Scoped to the
  cache dir only — enables TypeScript imports between files within a skill directory, while blocking
  access to project source (.env, src/, etc.).
- **No `--allow-write`** — skills communicate only via stdout (JSON). Read-only sandbox preserved.
- **`SkillDefinition.path`** stores the full local absolute path to the skill's entry point `.ts` file
  (e.g. `C:\Users\ianache\.skills-cache\skills\evaluar_test_case\index.ts`). DenoRunner receives it
  directly — no extra resolution step needed. CatalogExplorer constructs this path when building
  the SkillDefinition.

### Claude's Discretion
- Internal design of `SkillCache` class (method names, constructor signature)
- Whether `SkillCache` is injected into `CatalogExplorer` or constructed internally
- Exact git subprocess invocation (asyncio vs. subprocess, timeout)
- Test isolation strategy (mock SkillCache vs. temp dirs)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Config.github_token`: already present — NOT used for git auth (public repo), but stays for HTTP fallback
- `CatalogExplorer._log_error()`: reuse this pattern for logging cache failures to routing.jsonl
- `DenoRunner.execute(skill_path, params, allow_net_domains, extra_flags=[])`: `extra_flags` param
  already exists for caller-supplied flags — `--allow-read=.skills-cache/` passes here
- `_DOMAIN_RE` in deno_runner.py: validates allow_net domains; no equivalent needed for local paths

### Established Patterns
- **TTL cache pattern**: `CatalogExplorer._catalog_cache: tuple[float, list[dict]] | None` uses
  `time.monotonic()`. Phase 6 replaces in-memory TTL with file-based `.last-sync` for persistence.
- **Soft-fail pattern**: all `CatalogExplorer` fetch methods return None/[] on failure (never raise).
  `SkillCache` should raise internally; `CatalogExplorer` catches and soft-fails.
- **Config injection**: `CatalogExplorer.__init__` receives `Config` — `SkillCache` should also
  receive `Config` if it needs any config values (e.g., SKILLS_CACHE_DIR env var if added later).
- **asyncio subprocess**: `deno_runner.py` uses `asyncio.create_subprocess_exec` — git clone/pull
  should follow the same pattern for consistency

### Integration Points
- `CatalogExplorer._fetch_catalog_yaml()` → replace httpx fetch with `SkillCache.local_path / "catalog.yaml"` read
- `CatalogExplorer._fetch_skill_json()` → replace httpx fetch with local `skills/{path}/skills.json` read;
  `SkillDefinition.path` set to absolute path of `skills/{path}/{entry_point}`
- `SkillInjector._fetch_skill_md()` → replace httpx fetch with local `skills/{path}/SKILL.md` read;
  derive path from `skill_def.path` (already absolute TS path → strip filename, look for SKILL.md)
- `DenoRunner.execute()` → add `--allow-read={cache_root}` to extra_flags; `skill_path` is now local,
  domain validation only applies to allow_net, not allow_read
- `.gitignore` → add `.skills-cache/` entry

### New module: src/skill_cache.py
- `SkillCache` class manages `git clone` + `git pull` + `.last-sync` lifecycle
- Public interface: `async ensure_synced() -> Path` — returns local clone root, triggering clone/pull as needed
- Constructor: `SkillCache(repo_url: str, cache_dir: Path, ttl_seconds: int = 300)`
- `CatalogExplorer` receives `SkillCache` instance (injected or created internally)

</code_context>

<specifics>
## Specific Ideas

- "The catalog is public — skip auth for git, don't add complexity for token-in-URL"
- "Stale cache is better than no cache during a network blip"
- "Deno read access scoped to .skills-cache/ only — no access to project src or .env"
- "SkillDefinition.path becomes a full absolute local path — DenoRunner needs zero changes"

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 06-local-skill-cache-git-clone-architecture*
*Context gathered: 2026-05-17*
