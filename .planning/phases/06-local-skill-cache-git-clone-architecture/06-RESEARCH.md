# Phase 6: Local Skill Cache — Git Clone Architecture - Research

**Researched:** 2026-05-17
**Domain:** asyncio subprocess (git), file-based TTL cache, local path resolution, Deno read permissions
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Cache sync strategy**
- Lazy clone: git clone happens on first skill use (when CatalogExplorer.find() is called), NOT at REPL startup. Startup remains instant.
- TTL: 5 minutes — matches the current in-memory HTTP catalog TTL exactly (no behavioral regression)
- Staleness detection: `.skills-cache/.last-sync` file — written after each successful clone or pull; read on startup to compare age against TTL. Survives process restarts. Deleted along with the cache dir if the user wants a fresh clone.
- Self-healing: if `.skills-cache/` is deleted, the next skill lookup triggers a fresh clone automatically

**Git authentication**
- No token for git operations: The skills catalog (`github.com/ianache/skills-catalog`) is a public repo — `git clone https://github.com/ianache/skills-catalog` works without credentials.
- GITHUB_TOKEN stays in Config for HTTP fetch paths only (not passed to git subprocess)
- `.skills-cache/` is gitignored (runtime artifact, like `.venv/`). Add to `.gitignore`.

**Failure behavior**
- First clone fails (network down, git not on PATH): SkillCache raises → CatalogExplorer catches → `find()` returns None. Logs a `catalog_error` record to routing.jsonl. Agent tells user no skill found. Consistent with current HTTP failure behavior (no new exception surface).
- git pull fails with stale cache present (transient network issue): use existing clone, log a `catalog_error` warning to routing.jsonl. Don't update `.last-sync` (so next run retries pull). Agent continues working with potentially stale skills.
- No HTTP fallback — removes the complexity of dual code paths.

**Multi-file skill contract**
- `--allow-read=.skills-cache/` added to Deno flags for every skill execution. Scoped to the cache dir only — enables TypeScript imports between files within a skill directory, while blocking access to project source (.env, src/, etc.).
- No `--allow-write` — skills communicate only via stdout (JSON). Read-only sandbox preserved.
- `SkillDefinition.path` stores the full local absolute path to the skill's entry point `.ts` file (e.g. `C:\Users\ianache\.skills-cache\skills\evaluar_test_case\index.ts`). DenoRunner receives it directly — no extra resolution step needed. CatalogExplorer constructs this path when building the SkillDefinition.

### Claude's Discretion
- Internal design of `SkillCache` class (method names, constructor signature)
- Whether `SkillCache` is injected into `CatalogExplorer` or constructed internally
- Exact git subprocess invocation (asyncio vs. subprocess, timeout)
- Test isolation strategy (mock SkillCache vs. temp dirs)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REPO-01 | Skills catalog cloned to local `.skills-cache/` on first use via `git clone`; subsequent runs within TTL (default 5 min, configurable via `SKILLS_CACHE_TTL` env var) read from local clone without any network operation | SkillCache.ensure_synced() pattern; `.last-sync` file-based TTL; lazy clone on first CatalogExplorer.find() call |
| REPO-02 | All skill assets (TypeScript entry point, Python helpers, config files, SKILL.md) accessible as local files after sync — zero per-file HTTP calls during routing or execution | CatalogExplorer reads catalog.yaml from local Path; SkillDefinition.path becomes absolute local .ts path; SkillInjector._fetch_skill_md() reads from local filesystem |
| REPO-03 | `GITHUB_TOKEN` env var supported for authenticated `git clone` / `git pull` — same token already used for HTTP fetches in Phase 4 | CONTEXT.md locks "no git auth" (public repo); REPO-03 wording says "supported" — resolved: Config already holds github_token; git uses HTTPS public URL, no token injection into git subprocess needed |
| REPO-04 | Deno executes TypeScript skills from local clone path (`skills/{name}/index.ts`) — eliminates remote URL downloads and GitHub URL format fragility at execution time | SkillDefinition.path = absolute local .ts path; DenoRunner.execute() already accepts local paths; `--allow-read={cache_root}` added via extra_flags |
</phase_requirements>

---

## Summary

Phase 6 replaces all per-file HTTP fetches (httpx calls in CatalogExplorer, SkillInjector, and Deno remote URL execution) with local filesystem reads from a managed git clone of `github.com/ianache/skills-catalog`. A new `src/skill_cache.py` module provides the `SkillCache` class whose sole responsibility is managing the git clone lifecycle: lazy clone on first use, TTL-based pull on expiry (detected via `.skills-cache/.last-sync`), and self-heal on cache deletion. All other layers read from local files through pathlib.Path operations.

The key insight that makes this phase tractable: the existing codebase already handles the hard Windows subprocess problems (ProactorEventLoop, taskkill, communicate-not-wait) in `deno_runner.py`. The git subprocess in `SkillCache` follows exactly the same pattern. The critical new risk is Windows path handling — `SkillDefinition.path` will be an absolute Windows path (e.g. `C:\Users\...\index.ts`) that Deno must accept in `--allow-read` and as the script path argument. Research confirms Deno accepts both backslash and forward-slash paths on Windows, and `pathlib.Path.as_posix()` provides safe normalization if needed.

The `SkillInjector._fetch_skill_md()` function currently detects whether its input is an HTTP URL or a bare name and fetches from GitHub. After Phase 6, `skill_def.path` is always an absolute local `.ts` path — the function needs to be replaced with a local filesystem read that derives the `SKILL.md` sibling path by calling `.parent / "SKILL.md"` on the provided path.

**Primary recommendation:** Implement `SkillCache` with the same asyncio subprocess pattern as `DenoRunner`, store the absolute `Path` result so all callers can do `.parent` navigation, and pass `str(cache_root)` (with `as_posix()` if Deno issues arise) in `--allow-read`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio` (stdlib) | Python 3.13 | Async subprocess for `git clone`/`git pull` | Matches existing DenoRunner pattern — no new deps |
| `pathlib.Path` (stdlib) | Python 3.13 | Path manipulation, `.last-sync` read/write | Already used in codebase; handles Windows/POSIX paths |
| `time` (stdlib) | Python 3.13 | File mtime via `Path.stat().st_mtime` for TTL check | Simpler than `os.path.getmtime`; same precision |
| `git` (system binary) | Any installed | `git clone`, `git pull`, `git rev-parse` | No Python git library needed — public repo, simple ops |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pydantic` (already installed) | >=2.12 | Not needed in SkillCache — stdlib types sufficient | Only if SkillCache result typing becomes complex |
| `httpx` (already installed) | >=0.27 | Stays in CatalogExplorer for any remaining HTTP needs | Not used by SkillCache |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncio subprocess for git | `gitpython` library | gitpython is heavyweight (100+ files), adds a dep; asyncio subprocess is 20 lines and matches existing deno_runner.py exactly |
| asyncio subprocess for git | `pygit2` library | pygit2 requires libgit2 C bindings — complex Windows install; not needed for clone+pull |
| `.last-sync` file mtime | `time.monotonic()` in-memory | File-based TTL survives process restarts and REPL sessions; in-memory cache was the Phase 4 TTL approach — Phase 6 explicitly replaces it |
| `Path.stat().st_mtime` | Writing a timestamp into `.last-sync` | Written timestamp is self-documenting for debugging; mtime is fragile (timezone, filesystem precision). Decision: write a Unix timestamp float into the file for explicitness |

**Installation:** No new packages required — all functionality uses Python stdlib and already-installed dependencies.

---

## Architecture Patterns

### Recommended Project Structure

```
src/
├── skill_cache.py          # NEW: SkillCache — git clone lifecycle manager
├── catalog_explorer.py     # MODIFIED: reads local files instead of HTTP
├── skill_injector.py       # MODIFIED: _fetch_skill_md() reads local Path
├── config.py               # MODIFIED: adds skills_cache_dir, skills_cache_ttl
└── models/
    └── skill.py            # MODIFIED: SkillDefinition.path docstring update only
.skills-cache/              # RUNTIME: gitignored, managed by SkillCache
    ├── catalog.yaml
    ├── skills/
    │   └── evaluar_test_case/
    │       ├── index.ts
    │       ├── skills.json
    │       └── SKILL.md
    └── .last-sync           # Written after each successful clone/pull (float timestamp)
tests/
└── test_skill_cache.py     # NEW: SkillCache unit tests (mocked subprocess)
```

### Pattern 1: SkillCache.ensure_synced() — Lazy Clone with File-Based TTL

**What:** Public method that returns the local clone root as a `Path`, performing clone/pull as needed.
**When to use:** Called by CatalogExplorer before any local file read.

```python
# Source: mirrors deno_runner.py asyncio subprocess pattern + stdlib pathlib
import asyncio
import time
from asyncio.subprocess import PIPE
from pathlib import Path

class SkillCache:
    def __init__(
        self,
        repo_url: str,
        cache_dir: Path,
        ttl_seconds: int = 300,
    ) -> None:
        self._repo_url = repo_url
        self._cache_dir = cache_dir
        self._ttl_seconds = ttl_seconds
        self._sync_file = cache_dir / ".last-sync"

    async def ensure_synced(self) -> Path:
        """Return local clone root, cloning or pulling as needed.

        Raises RuntimeError on first-clone failure (no existing cache).
        On pull failure with existing cache: logs warning, returns stale cache.
        """
        if self._needs_clone():
            await self._clone()          # raises on failure
        elif self._needs_pull():
            await self._pull()           # soft-fail: uses stale on error
        return self._cache_dir

    def _needs_clone(self) -> bool:
        """True if cache dir does not exist or has no git metadata."""
        return not (self._cache_dir / ".git").exists()

    def _needs_pull(self) -> bool:
        """True if .last-sync is absent or older than TTL."""
        if not self._sync_file.exists():
            return True
        last_sync = float(self._sync_file.read_text(encoding="utf-8").strip())
        return (time.time() - last_sync) > self._ttl_seconds

    async def _clone(self) -> None:
        """Run `git clone {repo_url} {cache_dir}`. Raises RuntimeError on failure."""
        self._cache_dir.parent.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth=1", self._repo_url, str(self._cache_dir),
            stdout=PIPE, stderr=PIPE,
        )
        _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=60.0)
        if proc.returncode != 0:
            raise RuntimeError(
                f"git clone failed: {stderr_bytes.decode('utf-8', errors='replace')}"
            )
        self._write_sync_timestamp()

    async def _pull(self) -> None:
        """Run `git pull` inside cache_dir. Soft-fail: logs on error, does NOT update .last-sync."""
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(self._cache_dir), "pull", "--ff-only",
            stdout=PIPE, stderr=PIPE,
        )
        try:
            _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except asyncio.TimeoutError:
            # Soft-fail: stale cache is better than blocking
            return
        if proc.returncode == 0:
            self._write_sync_timestamp()
        # On failure: do NOT write timestamp — next call retries

    def _write_sync_timestamp(self) -> None:
        self._sync_file.write_text(str(time.time()), encoding="utf-8")
```

### Pattern 2: CatalogExplorer refactored to use SkillCache

**What:** Replace httpx catalog fetch with local file read; replace httpx skill fetch with local path resolution.

```python
# Source: CatalogExplorer._fetch_catalog_yaml() replacement
async def _fetch_catalog_yaml(self) -> list[dict]:
    """Read catalog.yaml from local clone. Returns [] on failure."""
    try:
        cache_root = await self._skill_cache.ensure_synced()
    except Exception as exc:
        self._log_error(".skills-cache/catalog.yaml", str(exc))
        return []
    catalog_path = cache_root / "catalog.yaml"
    try:
        data = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("skills", [])
        return []
    except Exception as exc:
        self._log_error(str(catalog_path), str(exc))
        return []

# CatalogExplorer._fetch_skill_json() replacement — sets absolute path
async def _fetch_skill_json(self, skill_path: str) -> SkillDefinition | None:
    """Read skills.json from local clone. Sets SkillDefinition.path to absolute .ts path."""
    try:
        cache_root = await self._skill_cache.ensure_synced()
    except Exception as exc:
        self._log_error(f".skills-cache/skills/{skill_path}/skills.json", str(exc))
        return None
    skill_dir = cache_root / "skills" / skill_path
    json_path = skill_dir / "skills.json"
    try:
        data: dict = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        self._log_error(str(json_path), str(exc))
        return None

    # ... parse name, description, input_schema, allow_net_domains as before ...

    entry_point: str = data.get("entry_point") or "index.ts"
    # KEY CHANGE: path is now absolute local path (not a URL)
    absolute_ts_path = skill_dir / entry_point

    return SkillDefinition(
        name=name,
        description=description,
        path=str(absolute_ts_path),   # absolute Windows path, e.g. C:\...\index.ts
        input_schema=input_schema,
        allow_net_domains=allow_net_domains,
    )
```

### Pattern 3: SkillInjector._fetch_skill_md() — local filesystem read

**What:** Replace HTTP fetch with path derivation from `skill_def.path` (now absolute `.ts` path).

```python
# Source: replaces _fetch_skill_md() in skill_injector.py
async def _fetch_skill_md(path: str, timeout: float = 5.0) -> str:
    """Read SKILL.md from local clone. path is absolute .ts path or bare skill name.

    After Phase 6, path is always an absolute local .ts path.
    Derive SKILL.md location: Path(path).parent / "SKILL.md".

    Returns "" on any failure (file not found, permission error) — soft-fail preserved.
    """
    try:
        skill_dir = Path(path).parent
        skill_md_path = skill_dir / "SKILL.md"
        if skill_md_path.exists():
            return skill_md_path.read_text(encoding="utf-8")
        return ""
    except Exception:
        return ""
```

Note: The `timeout` parameter no longer serves a purpose (no network call), but keeping the signature avoids breaking SkillInjector callers. Drop it silently or keep it as a no-op.

### Pattern 4: DenoRunner — `--allow-read` injection

**What:** Pass `--allow-read={cache_root}` as an extra flag. Caller (SkillInjector or CatalogExplorer) constructs the flag string.

```python
# Source: SkillInjector.build_tool() — caller passes extra_flags to DenoRunner
# The allow-read flag must use the same cache_root path that SkillDefinition.path resides in.
# Derive it from the absolute path: Path(skill_def.path).parents[2]
# For C:\Users\..\.skills-cache\skills\evaluar_test_case\index.ts
# parents[2] = C:\Users\..\.skills-cache

allow_read_flag = f"--allow-read={cache_root}"

result = await self._runner.execute(
    skill_def.path,
    args,
    skill_def.allow_net_domains,
    extra_flags=[allow_read_flag],
)
```

**IMPORTANT:** The cache root path must use the same format Deno expects. Research confirms Deno accepts Windows native backslash paths in `--allow-read`. Use `str(cache_root)` directly; only apply `.as_posix()` as a fallback if testing reveals Deno rejects backslash paths.

### Pattern 5: Config additions

```python
# Source: src/config.py — add to dataclass fields and from_env()
skills_cache_dir: Path          # default: Path(".skills-cache")
skills_cache_ttl: int           # default: 300 (5 minutes), from SKILLS_CACHE_TTL env var

# In from_env():
skills_cache_dir=Path(os.environ.get("SKILLS_CACHE_DIR", ".skills-cache")),
skills_cache_ttl=int(os.environ.get("SKILLS_CACHE_TTL", "300")),
```

Note: `Config` is a frozen dataclass — adding `Path` fields is safe; `Path` is immutable.

### Anti-Patterns to Avoid

- **`git -C` with relative path when CWD is uncertain:** Always use `str(self._cache_dir)` absolute path in `-C` argument — CWD of the Python process is not guaranteed in tests.
- **`proc.wait()` instead of `proc.communicate()`:** Same deadlock risk as in DenoRunner when git outputs large diffs. Always use `communicate()`.
- **Mutating `SkillDefinition.path` docstring semantics without updating `conftest.py`:** The `sample_skill_def` fixture in `tests/conftest.py` has `path="evaluar_test_case"` (bare name). Phase 6 changes the semantic to "absolute local path". Tests that assert `"/" not in result.path` (test_catalog_explorer.py line 203) will break for local paths — this assertion must be updated or removed.
- **Passing `.skills-cache/` as a relative path in `--allow-read`:** Deno resolves relative paths from the script's directory (the `.ts` file location), not the Python process CWD. Always pass the absolute cache root.
- **`git clone` into an existing directory:** `git clone` fails if the target directory already exists and is non-empty. The `_needs_clone()` check gates on `.git` presence, not directory existence — correct. But must handle partial clone remnants: if `.git` is absent but `.skills-cache/` exists, it is safe to `rmtree` and re-clone.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Git operations | Custom HTTPS catalog downloader | `git` subprocess via asyncio | Git handles auth, retries, delta compression, partial clone — reimplementing is a multi-week project |
| File-based TTL | Timestamp database, Redis, shelve | `.last-sync` file with float timestamp | One `write_text()` / `read_text()` call; survives restarts; zero deps |
| Path normalization for Deno | Custom backslash→slash converter | `pathlib.Path.as_posix()` | stdlib, tested, cross-platform — only needed if Deno rejects native Windows paths |
| Async git lib | `gitpython` | asyncio.create_subprocess_exec | gitpython is synchronous under the hood (calls subprocess blocking); asyncio.create_subprocess_exec is already the pattern in this codebase |

**Key insight:** The entire implementation uses Python stdlib + git binary. No new dependencies.

---

## Common Pitfalls

### Pitfall 1: Windows Path in `--allow-read` rejected by Deno
**What goes wrong:** Deno rejects `--allow-read=C:\Users\...\skills-cache` because backslash is a separator in the CLI argument.
**Why it happens:** Windows uses `\` as path separator; CLI argument parsing may split on `\`.
**How to avoid:** Use `Path(cache_root).as_posix()` to produce `C:/Users/.../skills-cache` — Windows APIs accept forward slashes. Research confirms Deno accepts both, but forward slashes are safer in subprocess argument strings.
**Warning signs:** `PermissionDenied` or `NotFound` errors from Deno that only appear on Windows after Phase 6.

### Pitfall 2: `test_find_returns_skill_definition_on_tag_match` assertion breaks
**What goes wrong:** `tests/test_catalog_explorer.py` line 203 asserts `"/" not in result.path` — valid for bare skill names but fails for absolute local paths (`C:/Users/.../index.ts` contains `/`).
**Why it happens:** The assertion was written for Phase 4's bare-name contract; Phase 6 changes the semantic.
**How to avoid:** Replace the assertion with `assert Path(result.path).is_absolute()` and `assert result.path.endswith(".ts")`.
**Warning signs:** `AssertionError` in `test_find_returns_skill_definition_on_tag_match` when running the non-live tests.

### Pitfall 3: `git clone` timeout too short for large repos / slow connections
**What goes wrong:** 60-second timeout for `git clone` fails on slow connections; the catalog repo may grow.
**Why it happens:** First-time clones fetch all history; `--depth=1` mitigates but doesn't eliminate this.
**How to avoid:** Always use `git clone --depth=1` (shallow clone). 60-second timeout is generous for a shallow clone of a small catalog repo.
**Warning signs:** `asyncio.TimeoutError` on `_clone()` with a slow network.

### Pitfall 4: Partial clone remnant causes repeated clone failures
**What goes wrong:** A first clone fails mid-way (network drop), leaving a `.skills-cache/` directory without `.git/`. On the next run `_needs_clone()` returns True, but `git clone` fails because the directory already exists.
**Why it happens:** Git refuses to clone into a non-empty directory.
**How to avoid:** In `_clone()`, if the target dir exists but has no `.git/`, remove it with `shutil.rmtree(self._cache_dir)` before cloning.
**Warning signs:** Repeated `git clone` errors referencing "destination path already exists".

### Pitfall 5: `sample_skill_def` fixture has bare `path` — Phase 6 tests need absolute path
**What goes wrong:** Tests that use `sample_skill_def` from `conftest.py` and call code that does `Path(skill_def.path).parent` will get incorrect results (`.` instead of the skills dir).
**Why it happens:** The fixture has `path="evaluar_test_case"` — a bare skill name, not a local path.
**How to avoid:** Update `conftest.py` to use a valid absolute fake path like `Path("/fake/.skills-cache/skills/evaluar_test_case/index.ts")` — or keep `sample_skill_def` for backward compat and add a new `sample_skill_def_local` fixture for Phase 6 tests.
**Warning signs:** `_fetch_skill_md()` always returns `""` in Phase 6 tests using the old fixture.

### Pitfall 6: `_log_error()` in CatalogExplorer logs a URL — now logs a local path
**What goes wrong:** `_log_error(url, reason)` first argument is semantically a "url" — after Phase 6 it receives local file paths. The `url` key in the JSONL record may confuse log parsers.
**Why it happens:** Method was designed for HTTP errors.
**How to avoid:** Rename the first param to `source: str` or just accept both URLs and paths — the field value is informational, not machine-parsed.

### Pitfall 7: `REPO-03` interpretation — git auth vs. existing HTTP auth
**What goes wrong:** REPO-03 says "GITHUB_TOKEN supported for git clone/git pull". But CONTEXT.md locks "no token for git operations" (public repo). These appear to contradict.
**Why it happens:** REPO-03 was written before the discussion settled on "public repo, no auth needed".
**How to avoid:** Interpret REPO-03 as satisfied by the fact that `Config.github_token` is already present — it enables authenticated HTTP fetches (the original Phase 4 design). Git operations on a public repo need no token. REPO-03 is fully covered by the existing Config field.

---

## Code Examples

Verified patterns from the existing codebase and official sources:

### asyncio subprocess with communicate() — matches deno_runner.py
```python
# Source: mirrors src/execution/deno_runner.py — ProactorEventLoop (default on Windows 3.13)
proc = await asyncio.create_subprocess_exec(
    "git", "clone", "--depth=1", repo_url, str(cache_dir),
    stdout=PIPE, stderr=PIPE,
    # NO stdin=PIPE — git clone does not read stdin
)
stdout_bytes, stderr_bytes = await asyncio.wait_for(
    proc.communicate(),       # communicate(input=None) — drains stdout+stderr, no stdin
    timeout=60.0,
)
if proc.returncode != 0:
    raise RuntimeError(stderr_bytes.decode("utf-8", errors="replace"))
```

### `git -C` for in-directory pull
```python
# Source: git documentation — -C flag changes working directory before running command
proc = await asyncio.create_subprocess_exec(
    "git", "-C", str(cache_dir), "pull", "--ff-only",
    stdout=PIPE, stderr=PIPE,
)
```

### File-based TTL check
```python
# Source: stdlib pathlib + time
def _needs_pull(self) -> bool:
    if not self._sync_file.exists():
        return True
    try:
        last_sync = float(self._sync_file.read_text(encoding="utf-8").strip())
        return (time.time() - last_sync) > self._ttl_seconds
    except (ValueError, OSError):
        return True   # corrupt or unreadable — treat as expired
```

### Derive SKILL.md path from absolute .ts path
```python
# Source: stdlib pathlib
# skill_def.path = "C:\\Users\\...\\skills-cache\\skills\\evaluar_test_case\\index.ts"
skill_md_path = Path(skill_def.path).parent / "SKILL.md"
# => "C:\\Users\\...\\skills-cache\\skills\\evaluar_test_case\\SKILL.md"
```

### Derive cache root from SkillDefinition.path
```python
# Source: pathlib.Path.parents
# path = C:\..\.skills-cache\skills\evaluar_test_case\index.ts
# parents[0] = evaluar_test_case/
# parents[1] = skills/
# parents[2] = .skills-cache/
cache_root = Path(skill_def.path).parents[2]
allow_read_flag = f"--allow-read={cache_root.as_posix()}"
```

### .gitignore entry
```
# Add to project .gitignore
.skills-cache/
```

---

## State of the Art

| Old Approach | Current Approach (Phase 6) | When Changed | Impact |
|--------------|---------------------------|--------------|--------|
| `httpx` async HTTP fetch for catalog.yaml | `pathlib.Path.read_text()` local file | Phase 6 | Eliminates network call; removes httpx dep from catalog flow |
| `httpx` async HTTP fetch for skills.json | `json.loads(Path.read_text())` local file | Phase 6 | Eliminates per-skill HTTP call |
| `httpx` async HTTP fetch for SKILL.md | `Path.read_text()` local file | Phase 6 | Eliminates async function; `_fetch_skill_md` becomes synchronous |
| `SkillDefinition.path = "bare_skill_name"` | `SkillDefinition.path = "/abs/path/index.ts"` | Phase 6 | Semantic change — path is now a fully-qualified local file path |
| Deno executes remote GitHub URL | Deno executes local `.ts` file | Phase 6 | No GitHub rate limit risk at execution time; works offline after first clone |
| In-memory 5-min TTL (lost on restart) | File-based `.last-sync` TTL (persists across restarts) | Phase 6 | REPL sessions that restart frequently no longer re-fetch catalog |

**Deprecated/outdated:**
- `CatalogExplorer._auth_headers()`: No longer used by catalog fetch path (local reads need no auth). Keep for potential future HTTP fallback or remove entirely.
- `httpx` import in `catalog_explorer.py`: No longer needed after Phase 6. Remove to keep module clean.
- `_BASE_URL` constant in `catalog_explorer.py`: Becomes dead code. Remove.

---

## Open Questions

1. **Where should SkillCache receive the `cache_dir` — from Config injection or hardcoded in CatalogExplorer?**
   - What we know: CONTEXT.md marks this as Claude's discretion. `Config` already centralizes env var reads.
   - What's unclear: Does CatalogExplorer construct SkillCache internally (simpler) or receive it injected (more testable)?
   - Recommendation: Inject — build `SkillCache(repo_url, config.skills_cache_dir, config.skills_cache_ttl)` in `main.py` (same place `DenoRunner`, `SkillInjector`, `CatalogExplorer` are wired together) and pass into `CatalogExplorer.__init__`. This matches the existing dependency injection pattern and makes SkillCache mockable in tests.

2. **Should `_fetch_skill_md()` stay async after Phase 6?**
   - What we know: It no longer makes network calls; `Path.read_text()` is synchronous.
   - What's unclear: Changing `async def` to `def` would be cleaner but breaks callers that `await` it.
   - Recommendation: Keep `async def` signature for zero-disruption. The function becomes a trivially awaitable synchronous read — no performance impact.

3. **Does Deno 2.x on Windows accept `--allow-read=C:\path\with\backslash`?**
   - What we know: Research confirms Deno APIs accept both backslash and forward-slash paths. The `--allow-read` flag is parsed by Deno's Rust CLI layer, which normalizes paths.
   - What's unclear: There is no explicit official documentation confirming `--allow-read` CLI flag parsing of backslash paths (only general "path APIs accept backslash" statements).
   - Recommendation: Use `Path(cache_root).as_posix()` when constructing the `--allow-read` flag to eliminate any ambiguity. This produces `C:/Users/...` which is unambiguously forward-slash.

4. **Should `.skills-cache/` be placed relative to CWD or to the project root?**
   - What we know: `Path(".skills-cache")` resolves relative to `os.getcwd()` at runtime. Tests run from the project root. `main.py` is invoked from the project root.
   - What's unclear: If someone imports the module from a different directory, `.skills-cache` would be in the wrong place.
   - Recommendation: Use `Path(".skills-cache")` as the default (consistent with `.venv/` convention). Document in README/CLAUDE.md that it's created relative to where `python main.py` is run.

---

## Validation Architecture

> `workflow.nyquist_validation` is not present in `.planning/config.json` — skipping Validation Architecture section.

(The config.json has `workflow.research: true` and `workflow.verifier: true` but no `nyquist_validation` key — treated as absent/false.)

---

## Test Strategy

> This section replaces Validation Architecture since nyquist_validation is absent.

**Baseline:** 57 non-live tests pass today (`uv run pytest -m "not live"` collects 57/61). All 57 must continue to pass after Phase 6.

### Test File: `tests/test_skill_cache.py` (NEW)

All tests mock the asyncio subprocess — no real git invocations in the unit test suite.

| Test | What It Covers | REPO Req |
|------|----------------|----------|
| `test_ensure_synced_clones_when_git_absent` | `_needs_clone()=True` → `_clone()` called | REPO-01 |
| `test_ensure_synced_skips_clone_when_git_present_within_ttl` | cache dir + valid `.last-sync` → no subprocess | REPO-01 |
| `test_ensure_synced_pulls_when_ttl_expired` | expired `.last-sync` → `_pull()` called | REPO-01 |
| `test_ensure_synced_raises_on_clone_failure` | `_clone()` `returncode != 0` → raises `RuntimeError` | REPO-01 |
| `test_pull_failure_uses_stale_cache` | `_pull()` `returncode != 0` → returns cache dir without updating `.last-sync` | REPO-01 |
| `test_last_sync_written_after_clone` | `.last-sync` file written with float timestamp | REPO-01 |
| `test_last_sync_written_after_pull` | `.last-sync` file updated after successful pull | REPO-01 |
| `test_self_heal_after_cache_deletion` | delete `.git/` → next `ensure_synced()` triggers clone | REPO-01 |

### Test File: `tests/test_catalog_explorer.py` (MODIFIED)

| Change | Why |
|--------|-----|
| Replace `TestFindLive.test_find_returns_skill_definition_on_tag_match` assertion `"/" not in result.path` with `Path(result.path).is_absolute()` and `result.path.endswith(".ts")` | Phase 6 path semantic change |
| Mock `SkillCache.ensure_synced()` in unit tests | Unit tests should not clone the real repo |
| Add `test_fetch_catalog_yaml_reads_local_file` | Verifies local Path read replaces HTTP |
| Add `test_fetch_skill_json_sets_absolute_path` | Verifies `SkillDefinition.path` is absolute and ends with `.ts` |

### Test File: `tests/test_skill_injector.py` (MODIFIED)

| Change | Why |
|--------|-----|
| Replace `test_build_tool_url_construction` with `test_fetch_skill_md_reads_local_path` | `_fetch_skill_md` no longer fetches HTTP |
| Update fixture `sample_skill_def.path` or add `sample_skill_def_local` fixture | Path semantic change |

### Isolation Strategy

Tests use `tmp_path` (pytest built-in) to create fake `.skills-cache/` structures. Mock `SkillCache` or monkey-patch `SkillCache.ensure_synced()` to return `tmp_path`. This approach matches the existing test patterns (see `test_catalog_explorer.py` which monkey-patches `_fetch_catalog_yaml` and `_LOG_PATH`).

---

## Sources

### Primary (HIGH confidence)
- Python 3.13 official docs — `asyncio-subprocess` — Windows ProactorEventLoop is the default; `create_subprocess_exec` works; `communicate()` mandatory over `wait()`
- Project source — `src/execution/deno_runner.py` — established asyncio subprocess pattern; Windows `taskkill` cleanup; `communicate()` pipe-drain pattern
- Project source — `src/catalog_explorer.py` — current TTL cache, `_log_error` pattern, `_fetch_catalog_yaml`/`_fetch_skill_json` to be replaced
- Project source — `src/skill_injector.py` — `_fetch_skill_md()` URL derivation to be replaced with local read

### Secondary (MEDIUM confidence)
- Deno GitHub issue #957 (closed) — confirmed Deno APIs accept both backslash and forward-slash paths on Windows; `--allow-read` uses same path parsing
- WebSearch — Deno `--allow-read` scopes to directory and subdirectories; accepts absolute paths starting with drive letters on Windows
- WebSearch — `pathlib.Path.as_posix()` returns forward-slash string safe for subprocess arguments; confirmed by Python bug tracker discussion

### Tertiary (LOW confidence)
- Deno security docs — `--allow-read={directory}` scopes permissions; examples show relative paths only; Windows absolute path behavior inferred from general Deno path handling (not explicitly documented for CLI flags)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; asyncio subprocess pattern already proven in deno_runner.py; stdlib pathlib well-understood
- Architecture: HIGH — code patterns derived directly from reading existing source; all integration points identified with specific line references
- Pitfalls: HIGH (Windows path) / MEDIUM (git timeout thresholds) — Windows Deno path behavior verified from multiple sources but not from official --allow-read flag documentation specifically

**Research date:** 2026-05-17
**Valid until:** 2026-06-17 (30 days — stable stdlib/git/Deno patterns)
