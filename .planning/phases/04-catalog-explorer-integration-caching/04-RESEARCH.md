# Phase 4: CatalogExplorer Integration + Caching - Research

**Researched:** 2026-05-17
**Domain:** GitHub HTTP fetching with TTL caching, YAML parsing, asyncio concurrency (httpx + asyncio.gather)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**GitHub failure behavior**
- Any failure (network error, non-200 response, 4xx, 5xx) is treated equally — no distinction between connection errors and HTTP errors
- `find()` returns `None` on failure; `get_all_tags()` returns `[]` on failure
- Failures are logged to `logs/routing.jsonl` with `type='catalog_error'` (same log file as routing decisions)
- The agent proceeds silently as if no skill matched — no GitHub details exposed to the user

**Tag matching semantics**
- OR logic: a skill matches if ANY of the extracted tags appear in the skill's tag list
- Best match wins: when multiple skills qualify, the one with the most overlapping tags is returned; ties broken by catalog order
- `find()` returns `None` if no skill matches any extracted tag
- Filtering is tag-only — `catalog.yaml` entries are trusted; no validation of `skill.json` fields before returning

**get_all_tags() data source**
- Tags come from `catalog.yaml` only — no additional `skill.json` fetches
- `get_all_tags()` triggers the same catalog fetch as `find()` and shares the 5-min cache
- Returns deduplicated tags sorted alphabetically
- Returns `[]` on fetch failure (Pass 1 proceeds without vocabulary constraint)

**Rate limits & auth**
- `GITHUB_TOKEN` passed as `Authorization: Bearer {token}` header to `raw.githubusercontent.com`
- Rate-limit responses (403/429) treated the same as any other failure — logged to JSONL, return `None`/`[]`
- No special-casing for rate-limit status codes
- `CatalogExplorer` accepts a `Config` object in its constructor (consistent with `CoordinatingAgent` and `SkillInjector`)

### Claude's Discretion

- Internal cache data structure (dict, dataclass, etc.)
- Whether to use a single shared `httpx.AsyncClient` or per-request clients
- Exact `catalog.yaml` schema parsing details (key names, list structure)
- `asyncio.gather` concurrency implementation for multi-candidate skill.json fetches

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DISC-03 | CatalogExplorer fetches `catalog.yaml` from GitHub SSOT and filters skills by tag intersection | httpx AsyncClient patterns, yaml.safe_load, OR-logic tag matching |
| DISC-04 | Matched skill's `skill.json` is lazy-loaded from GitHub SSOT per request | asyncio.gather for concurrent multi-candidate fetches, per-request URL construction |
| RELI-01 | `catalog.yaml` responses are TTL-cached in-memory (5-minute TTL) to prevent GitHub rate limit exhaustion | time.monotonic() TTL pattern, tuple (expiry, data) in instance variable |
| RELI-02 | `GITHUB_TOKEN` env var supported for authenticated GitHub fetches (5000 req/hr vs 60) | httpx default_headers pattern; important caveat documented in Pitfalls |
</phase_requirements>

## Summary

Phase 4 implements `src/catalog_explorer.py` — a single class (`CatalogExplorer`) that fetches `catalog.yaml` from GitHub via `raw.githubusercontent.com`, applies OR-logic tag filtering, lazy-loads `skill.json` for matched skills, and caches the catalog with a 5-minute TTL. The class exposes exactly two async public methods: `find(tags: list[str]) -> SkillDefinition | None` and `get_all_tags() -> list[str]`. Both share the same internal cache.

The stack is entirely composed of libraries already present in `pyproject.toml`: `httpx>=0.27` for HTTP fetching and `pyyaml>=6.0.2` for YAML parsing. No new dependencies are required. The established pattern from `skill_injector.py` (per-request `async with httpx.AsyncClient()` context manager) is sufficient for this phase's fetch volume, though a shared client offers connection-pool benefits discussed below. For `asyncio.gather` on multiple `skill.json` candidates, the per-request client pattern is simpler and should be preferred.

A critical runtime finding: GitHub officially confirmed (May 2025) that `raw.githubusercontent.com` rate limits were tightened for unauthenticated requests. Community reports indicate tokens sent via `Authorization: Bearer` header to `raw.githubusercontent.com` may or may not be respected (GitHub's documentation is incomplete on this). However, the CONTEXT.md decision locks in the Bearer token approach — implement it as specified. The TTL cache (RELI-01) provides the primary protection against rate-limit exhaustion by eliminating repeated catalog.yaml fetches; the token is a secondary guard for `skill.json` lazy-loads.

**Primary recommendation:** Follow the `skill_injector.py` httpx pattern exactly — per-request `async with httpx.AsyncClient()`, soft-fail on any exception or non-200, yaml.safe_load on the catalog response body, cache tuple `(expiry: float, data: list[dict])` in `self._catalog_cache`. Keep the class under 100 lines.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | `>=0.27,<1` (already in pyproject.toml) | Async HTTP GET for catalog.yaml and skill.json | Already used in skill_injector.py; async-native, better than aiohttp for simple fetch tasks |
| `pyyaml` | `>=6.0.2,<7` (already in pyproject.toml) | Parse catalog.yaml response body | Already in pyproject.toml; yaml.safe_load is the security-required variant |
| `asyncio` | stdlib | `asyncio.gather()` for concurrent skill.json fetches | No install needed; standard concurrency primitive |
| `time` | stdlib | `time.monotonic()` for TTL expiry tracking | Monotonic clock unaffected by system clock adjustments — correct for elapsed-time measurements |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` | stdlib | Parse skill.json response body | Already used everywhere in the project |
| `src.models.skill` | internal | `SkillDefinition` return type | Shared contract between CatalogExplorer and SkillInjector |
| `src.config` | internal | `Config.github_token` for Bearer auth | Injected in constructor following established pattern |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-request `async with httpx.AsyncClient()` | Shared long-lived `AsyncClient` as instance variable | Shared client gives connection pooling benefit; per-request is simpler and avoids lifecycle management (who calls `.aclose()`). For 2-3 requests per catalog operation, per-request wins on simplicity. |
| `time.monotonic()` manual TTL | `cachetools.TTLCache` or `async-cache` library | Third-party cache libs would be clean but add dependencies not in pyproject.toml; manual tuple `(expiry, data)` is 4 lines and no new deps |
| `yaml.safe_load()` inline | Pre-built Pydantic model for catalog.yaml | Pydantic parsing is cleaner but adds model maintenance overhead; trust the catalog YAML and parse inline per locked decision |

**Installation:** No new packages required. All dependencies already in `pyproject.toml`.

## Architecture Patterns

### Recommended Module Structure

```
src/
└── catalog_explorer.py     # CatalogExplorer class — all logic in one file, ~80-100 lines
```

The class has no sub-modules. It is self-contained with no imports from ADK.

### Pattern 1: TTL Cache with `time.monotonic()`

**What:** Store `(expiry_ts, data)` tuples as instance variables. On access, compare `time.monotonic()` against `expiry_ts`. If expired (or None), fetch fresh. If fresh, return cached data.

**When to use:** For `catalog.yaml` — the only remote resource fetched on every `find()` or `get_all_tags()` call.

**Example:**
```python
import time

class CatalogExplorer:
    _TTL_SECONDS = 300  # 5 minutes

    def __init__(self, config: Config) -> None:
        self._config = config
        self._catalog_cache: tuple[float, list[dict]] | None = None
        # _catalog_cache stores (expiry_monotonic, skills_list)

    async def _get_catalog(self) -> list[dict]:
        """Return cached catalog or fetch fresh. Returns [] on any failure."""
        now = time.monotonic()
        if self._catalog_cache is not None and now < self._catalog_cache[0]:
            return self._catalog_cache[1]  # cache hit

        skills = await self._fetch_catalog_yaml()  # returns [] on failure
        if skills:  # only cache successful fetches
            self._catalog_cache = (now + self._TTL_SECONDS, skills)
        return skills
```

**Key constraint:** Only cache successful fetches. A failure response must NOT be cached — the next call must retry GitHub immediately.

### Pattern 2: OR-Logic Tag Matching with Best-Match Selection

**What:** Iterate all skills in `catalog.yaml`. For each skill, count how many of the queried tags appear in the skill's tag list. Keep the skill with the highest overlap count. Ties resolved by catalog order (first entry wins).

**When to use:** Every `find()` call after catalog fetch.

**Example:**
```python
def _best_match(self, skills: list[dict], tags: list[str]) -> dict | None:
    """Return the skill with the most tag overlaps, or None if no match."""
    best: dict | None = None
    best_count = 0
    tag_set = set(tags)
    for skill in skills:
        skill_tags = set(skill.get("tags", []))
        overlap = len(tag_set & skill_tags)
        if overlap > best_count:
            best = skill
            best_count = overlap
    return best  # None if no skill had any overlap
```

### Pattern 3: Lazy skill.json Fetch

**What:** After `_best_match` identifies a winning skill entry (from `catalog.yaml`), fetch its `skill.json` to build a `SkillDefinition`. URL pattern: `https://raw.githubusercontent.com/ianache/skills-catalog/main/skills/{name}/skill.json`. Parse JSON, construct `SkillDefinition`.

**When to use:** Only in `find()`, after a match is identified. Never pre-fetch.

**Example:**
```python
async def _fetch_skill_json(self, skill_name: str) -> SkillDefinition | None:
    url = (
        f"https://raw.githubusercontent.com/ianache/skills-catalog/main/"
        f"skills/{skill_name}/skill.json"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            headers = self._auth_headers()
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return None
            data = resp.json()
            return SkillDefinition(
                name=data["name"],
                description=data["description"],
                path=skill_name,       # bare name, no 'skills/' prefix (per 02-01 decision)
                input_schema=data["input_schema"],
                allow_net_domains=data.get("allow_net_domains", []),
            )
    except Exception:
        return None

def _auth_headers(self) -> dict:
    if self._config.github_token:
        return {"Authorization": f"Bearer {self._config.github_token}"}
    return {}
```

### Pattern 4: asyncio.gather for Multiple Candidate Fetches

**What:** When `catalog.yaml` has multiple candidate skills (all with tag overlap > 0), the current design selects the best match first then fetches only that skill.json. However, if the design ever needs to pre-screen multiple candidates, use `asyncio.gather` with a shared client.

**When to use:** Only if best-match selection is moved post skill.json fetch. For current design (select then fetch), single fetch is correct.

**Example (for reference):**
```python
# Multiple concurrent fetches — only use if fetching N candidates simultaneously
async with httpx.AsyncClient(timeout=5.0) as client:
    tasks = [self._fetch_one(client, name) for name in candidate_names]
    results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Note:** The CONTEXT.md decision (best match wins before lazy-load) means only ONE skill.json fetch happens per `find()` call. The `asyncio.gather` pattern is documented for completeness but not required by the current spec.

### Pattern 5: catalog_error JSONL Logging

**What:** On any GitHub failure in `find()` or `get_all_tags()`, write a JSONL record to `logs/routing.jsonl` with `type='catalog_error'`. Follow the exact same append pattern as `_write_routing_log()` in `agent.py`.

**When to use:** Whenever a catalog fetch returns non-200 or raises an exception.

**Example:**
```python
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

_LOG_PATH = Path("logs/routing.jsonl")

def _write_catalog_error(url: str, reason: str) -> None:
    record = {
        "type": "catalog_error",
        "url": url,
        "reason": reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
```

**Note:** The JSONL write is synchronous (as in `agent.py`). For a single-user CLI, this is acceptable. Do not introduce aiofiles — it is not in `pyproject.toml` and is unnecessary overhead for a low-frequency log write.

### Anti-Patterns to Avoid

- **Caching failed fetches:** If GitHub returns 503, caching the empty result means the next 5 minutes will also return empty — even if GitHub recovers after 10 seconds. Only cache `len(skills) > 0` results.
- **Global `_catalog_cache` at module level:** Would leak state between tests and across multiple `CatalogExplorer` instances. Cache must live on the instance (`self._catalog_cache`).
- **Fetching skill.json for all catalog entries at init time:** Defeats lazy-loading. `skill.json` is only fetched when a tag match is found in `catalog.yaml`.
- **Using `yaml.load()` without a Loader:** Security risk. Always `yaml.safe_load()`.
- **Raising exceptions from `find()` or `get_all_tags()`:** Both methods must never raise. All failures are soft-caught and converted to `None`/`[]`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async HTTP fetch | Custom `asyncio.open_connection` or `urllib` wrapper | `httpx.AsyncClient` | Already in project; connection pooling, timeout, auth headers built-in |
| YAML parsing | Custom text parser for catalog.yaml | `yaml.safe_load()` | Already in project; handles all YAML edge cases; security-safe |
| TTL cache | External Redis, `cachetools.TTLCache`, or `async-cache` library | Manual `(expiry, data)` tuple on instance | No new dep; 4 lines; sufficient for single-process CLI |
| Rate limit tracking | Counter with rolling window, exponential backoff | Treat all failures equally (locked decision) | Locked by CONTEXT.md — no special rate-limit handling code |

**Key insight:** Every library needed is already installed. The implementation is glue code between httpx, pyyaml, and the existing `SkillDefinition` model.

## Common Pitfalls

### Pitfall 1: raw.githubusercontent.com Auth Token May Not Raise Rate Limits

**What goes wrong:** `Authorization: Bearer {GITHUB_TOKEN}` is sent to `raw.githubusercontent.com`, but GitHub community reports (2025-05) indicate the raw content CDN may silently ignore the token — no rate limit headers are returned, and the token provides no verified benefit.

**Why it happens:** `raw.githubusercontent.com` is a CDN-backed static file server, not the REST API endpoint. Auth is documented for the REST API (`api.github.com`), not the raw CDN.

**How to avoid:** The CONTEXT.md locks in the Bearer token approach — implement it as specified. The 5-minute TTL cache (RELI-01) is the primary rate-limit defense; it reduces catalog.yaml fetches from O(prompts) to O(1/5min). The token is a best-effort secondary guard. Tests should not depend on the token actually raising the rate limit.

**Warning signs:** HTTP 429 responses even when `GITHUB_TOKEN` is set — treat same as any other failure (log + return None/[]).

### Pitfall 2: Caching Failures Locks Out Recovery

**What goes wrong:** On a transient GitHub error (503, network timeout), the cache is populated with an empty list. The next 5 minutes return [] from cache without retrying GitHub. The catalog appears empty for the entire TTL window.

**Why it happens:** Naive cache logic: "if cache is empty, fetch; store result either way."

**How to avoid:** Only cache non-empty successful responses. If `skills == []` (empty catalog or failed fetch), do NOT update `_catalog_cache`. The next `find()` or `get_all_tags()` call will retry GitHub.

```python
if skills:  # non-empty only
    self._catalog_cache = (now + self._TTL_SECONDS, skills)
```

### Pitfall 3: skill.json `path` Field Must Be Bare Skill Name

**What goes wrong:** `SkillDefinition.path` is set to `"skills/evaluar_test_case"` (with prefix), but `skill_injector.py` adds the `skills/` prefix at URL construction time. Result: double-prefix URL `skills/skills/evaluar_test_case/SKILL.md`.

**Why it happens:** Reading the GitHub URL and thinking the full path goes in `SkillDefinition.path`.

**How to avoid:** Confirmed in STATE.md (02-01 decision): `SkillDefinition.path` stores the bare skill name (`"evaluar_test_case"`), no `"skills/"` prefix. CatalogExplorer sets `path=skill_name` (the directory name from `catalog.yaml`).

### Pitfall 4: YAML Key Assumptions Without Verification

**What goes wrong:** Code assumes `catalog.yaml` uses a specific key name (e.g., `skills`, `entries`, `catalog`) for the list of skills. If the actual file uses a different key, `skills = data["skills"]` raises `KeyError`.

**Why it happens:** The catalog.yaml schema is declared out of scope for verification in CONTEXT.md ("Exact `catalog.yaml` schema parsing details — Claude's Discretion").

**How to avoid:** Test against the live catalog (`https://raw.githubusercontent.com/ianache/skills-catalog/main/catalog.yaml`) during Wave 0 or the first test. Use `data.get("skills", [])` defensively; log the actual parsed keys if list is empty to aid debugging.

**Note:** As of research date, the live catalog at `https://github.com/ianache/skills-catalog` exists. The exact YAML structure must be verified by fetching it — this is a Wave 0 task.

### Pitfall 5: `asyncio.gather` with `return_exceptions=False` Aborts All Fetches on First Error

**What goes wrong:** When fetching multiple `skill.json` files concurrently, if one HTTP call raises, `asyncio.gather()` cancels the others and re-raises. A single 404 kills all concurrent fetches.

**Why it happens:** `asyncio.gather` default behavior is `return_exceptions=False`.

**How to avoid:** Use `return_exceptions=True` for any multi-candidate concurrent fetch:
```python
results = await asyncio.gather(*tasks, return_exceptions=True)
```
Filter out `Exception` instances from results. However, the current design selects best-match first then fetches ONE skill.json, making this pitfall moot for the Phase 4 spec. Document it for future multi-candidate pre-screening.

### Pitfall 6: Test Hits Live GitHub — No Mock, Must Have Network Access

**What goes wrong:** Tests silently pass in CI where GitHub is blocked, masking real breakage.

**Why it happens:** CLAUDE.md explicitly locks "tests hit the live GitHub repo — no mocks per project decision."

**How to avoid:** Run tests in an environment with GitHub network access. Mark tests with `@pytest.mark.skip` conditions if GitHub is unreachable rather than mocking. Verify `GITHUB_TOKEN` is set in the test environment for rate limit headroom.

## Code Examples

Verified patterns from project sources and official docs:

### Full CatalogExplorer Skeleton

```python
# src/catalog_explorer.py
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from src.config import Config
from src.models.skill import SkillDefinition

_LOG_PATH = Path("logs/routing.jsonl")
_TTL_SECONDS = 300  # 5 minutes
_BASE_URL = "https://raw.githubusercontent.com/ianache/skills-catalog/main"


class CatalogExplorer:
    def __init__(self, config: Config) -> None:
        self._config = config
        # Tuple of (expiry_monotonic: float, skills: list[dict]) or None
        self._catalog_cache: tuple[float, list[dict]] | None = None

    def _auth_headers(self) -> dict:
        if self._config.github_token:
            return {"Authorization": f"Bearer {self._config.github_token}"}
        return {}

    async def _fetch_catalog_yaml(self) -> list[dict]:
        """Fetch catalog.yaml. Returns [] on any failure."""
        url = f"{_BASE_URL}/catalog.yaml"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=self._auth_headers())
            if resp.status_code != 200:
                self._log_error(url, f"HTTP {resp.status_code}")
                return []
            data = yaml.safe_load(resp.text)
            return data.get("skills", []) if isinstance(data, dict) else []
        except Exception as exc:
            self._log_error(url, str(exc))
            return []

    async def _get_catalog(self) -> list[dict]:
        """Return cached catalog or fetch fresh."""
        now = time.monotonic()
        if self._catalog_cache is not None and now < self._catalog_cache[0]:
            return self._catalog_cache[1]
        skills = await self._fetch_catalog_yaml()
        if skills:  # only cache non-empty successful responses
            self._catalog_cache = (now + _TTL_SECONDS, skills)
        return skills

    def _best_match(self, skills: list[dict], tags: list[str]) -> dict | None:
        """OR-logic: return skill with most tag overlaps; ties by catalog order."""
        tag_set = set(tags)
        best, best_count = None, 0
        for skill in skills:
            overlap = len(tag_set & set(skill.get("tags", [])))
            if overlap > best_count:
                best, best_count = skill, overlap
        return best

    async def _fetch_skill_json(self, skill_name: str) -> SkillDefinition | None:
        """Lazy-load skill.json for the matched skill."""
        url = f"{_BASE_URL}/skills/{skill_name}/skill.json"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=self._auth_headers())
            if resp.status_code != 200:
                self._log_error(url, f"HTTP {resp.status_code}")
                return None
            data = resp.json()
            return SkillDefinition(
                name=data["name"],
                description=data["description"],
                path=skill_name,  # bare name — no 'skills/' prefix (02-01 decision)
                input_schema=data["input_schema"],
                allow_net_domains=data.get("allow_net_domains", []),
            )
        except Exception as exc:
            self._log_error(url, str(exc))
            return None

    async def find(self, tags: list[str]) -> SkillDefinition | None:
        """Find the best-matching skill by tag intersection. Returns None on no match or error."""
        skills = await self._get_catalog()
        matched = self._best_match(skills, tags)
        if matched is None:
            return None
        skill_name = matched.get("name") or matched.get("path", "")
        return await self._fetch_skill_json(skill_name)

    async def get_all_tags(self) -> list[str]:
        """Return deduplicated, alphabetically sorted tags from catalog.yaml."""
        skills = await self._get_catalog()
        all_tags: set[str] = set()
        for skill in skills:
            all_tags.update(skill.get("tags", []))
        return sorted(all_tags)

    def _log_error(self, url: str, reason: str) -> None:
        record = {
            "type": "catalog_error",
            "url": url,
            "reason": reason,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
```

### httpx Per-Request Pattern (from skill_injector.py — established project pattern)

```python
# Source: src/skill_injector.py (existing code)
async with httpx.AsyncClient(timeout=timeout) as client:
    response = await client.get(url)
    if response.status_code == 200:
        return response.text
    return ""
```

### yaml.safe_load Pattern

```python
# Source: CLAUDE.md constraint — always yaml.safe_load, never yaml.load
import yaml
data = yaml.safe_load(response_text)  # returns dict, list, or None
```

### time.monotonic() TTL Pattern

```python
# Source: cachetools library docs (uses time.monotonic internally)
# Monotonic clock: unaffected by system clock changes (NTP adjustments, DST)
import time
expiry = time.monotonic() + 300  # 5 minutes from now
is_fresh = time.monotonic() < expiry
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `requests` (sync) | `httpx.AsyncClient` (async) | httpx ~0.18+ | Non-blocking; required for asyncio agent loop |
| `yaml.load()` | `yaml.safe_load()` | PyYAML security advisory | Prevents arbitrary code execution via YAML deserialization |
| `api.github.com` for file content | `raw.githubusercontent.com` | Always | CDN-backed, no API quota consumed for content reads |

**Deprecated/outdated:**
- `aiohttp` for this project: httpx is already installed and provides equivalent async HTTP. Do not add aiohttp.
- `cachetools` or `async-cache` libraries: unnecessary for a single-variable TTL; add no benefit over manual `time.monotonic()` tuple.

## Open Questions

1. **catalog.yaml exact schema (key names)**
   - What we know: CLAUDE.md says the file has skills with tags; the URL is `raw.githubusercontent.com/ianache/skills-catalog/main/catalog.yaml`
   - What's unclear: The exact YAML structure — top-level key for the skill list, per-skill keys (is it `name`, `path`, `tags`? Any `allow_net_domains` at catalog level?)
   - Recommendation: Wave 0 task — `curl https://raw.githubusercontent.com/ianache/skills-catalog/main/catalog.yaml` and adapt parser. Use `data.get("skills", [])` as the first attempt; log the actual keys if empty.

2. **raw.githubusercontent.com Bearer token effectiveness**
   - What we know: GitHub community discussion (2025) indicates the CDN may ignore the `Authorization` header; GitHub's May 2025 rate limit announcement does not clarify this definitively
   - What's unclear: Whether sending `Authorization: Bearer {GITHUB_TOKEN}` actually raises the rate limit from 60 to 5000/hr for raw CDN requests
   - Recommendation: Implement as specified in CONTEXT.md. The 5-min TTL cache is the primary rate-limit defense regardless. If 429s occur even with the token set, the existing failure handling (log + return None) prevents crashes.

3. **skill.json `allow_net_domains` field presence**
   - What we know: `SkillDefinition.allow_net_domains: list[str]` with `[]` as valid value
   - What's unclear: Whether the live `skill.json` files include `allow_net_domains` or if it needs a `data.get("allow_net_domains", [])` fallback
   - Recommendation: Always use `data.get("allow_net_domains", [])` — safe regardless of field presence.

## Sources

### Primary (HIGH confidence)
- `src/skill_injector.py` (project source) — httpx per-request AsyncClient pattern with timeout=5.0, soft-fail on non-200
- `src/agent.py` (project source) — JSONL append pattern: `open(_LOG_PATH, "a")`, mkdir parents
- `src/models/skill.py` (project source) — `SkillDefinition` field contract, `path` is bare name (02-01 decision)
- `src/config.py` (project source) — `Config.github_token: str | None`, constructor injection pattern
- `.planning/STATE.md` (project state) — 02-01 decision: `SkillDefinition.path` bare name, no `skills/` prefix
- https://www.python-httpx.org/advanced/clients/ — shared client vs per-request recommendations
- https://www.python-httpx.org/async/ — AsyncClient context manager pattern

### Secondary (MEDIUM confidence)
- https://github.blog/changelog/2025-05-08-updated-rate-limits-for-unauthenticated-requests/ — GitHub May 2025 rate limit tightening affecting raw.githubusercontent.com
- https://pyyaml.org/wiki/PyYAMLDocumentation — yaml.safe_load() security requirement
- cachetools docs — `time.monotonic()` is the standard for TTL expiry tracking (library itself uses it internally)

### Tertiary (LOW confidence — needs validation)
- https://github.com/orgs/community/discussions/160828 — Community claim that raw.githubusercontent.com ignores Bearer tokens; unverified by official GitHub docs. **Flag: implement token header as specified; do not rely on it for rate limit guarantees.**

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in pyproject.toml, patterns verified in existing project code
- Architecture: HIGH — CatalogExplorer contract locked in agent.py (duck-typed call sites confirmed), SkillDefinition field constraints confirmed in STATE.md
- Pitfalls: HIGH for Pitfalls 2-6 (verified against project decisions and stdlib behavior); MEDIUM for Pitfall 1 (raw.githubusercontent.com auth — community report only, not official docs)

**Research date:** 2026-05-17
**Valid until:** 2026-06-17 (stable stdlib + httpx + pyyaml stack; GitHub rate limit policy — recheck if 429s appear in testing)
