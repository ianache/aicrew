"""
CatalogExplorer — local skill discovery from git-cloned cache with 5-minute TTL.

Reads catalog.yaml from the local SkillCache-managed git clone at
.skills-cache/catalog.yaml (no HTTP — file is read via pathlib.Path.read_text()).

All failures (clone error, missing file, parse error) are soft-caught: find() returns None,
get_all_tags() returns []. Every failure is logged as a catalog_error record to routing.jsonl.

Tag matching uses OR logic (any overlap qualifies) with the highest overlap count winning.
When a catalog entry has no explicit 'tags' field, matching falls back to words in the
description — this handles the current ianache/skills-catalog structure where tags are
embedded in descriptions rather than a dedicated field.

Skill metadata is loaded from skills/<path>/skills.json (note plural). The first tool in
the 'tools' array provides the name, description, and input_schema for SkillDefinition.
allow_net_domains is read from the skill's top-level key if present, otherwise defaults to [].

SkillDefinition.path is an absolute local .ts path (not a URL) — Phase 6 contract.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.config import Config
from src.models.skill import SkillDefinition
from src.skill_cache import SkillCache

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_LOG_PATH = Path("logs/routing.jsonl")
_TTL_SECONDS = 300  # 5-minute TTL for catalog.yaml cache

# Regex to split description text into individual words for tag matching fallback
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


class CatalogExplorer:
    """Discovers skills from the local git clone of the skills catalog.

    Constructor args:
        config: Config — kept for backward compat (not used for auth in local path).
        skill_cache: SkillCache — manages git clone lifecycle and returns local root path.

    Public interface (duck-typed by CoordinatingAgent):
        async find(tags: list[str]) -> SkillDefinition | None
        async get_all_tags() -> list[str]
    """

    def __init__(self, config: Config, skill_cache: SkillCache) -> None:
        self._config = config
        self._skill_cache = skill_cache
        # Cache tuple: (expiry_monotonic, skills_list) or None when empty/expired
        self._catalog_cache: tuple[float, list[dict]] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def find(self, tags: list[str]) -> SkillDefinition | None:
        """Return the best-matching SkillDefinition for the given tags, or None.

        Matching is OR-logic: any tag overlap qualifies; the skill with the most
        overlapping tags wins. Ties are resolved by catalog order (first wins).

        Returns None (never raises) on catalog failure or when no skill matches.
        """
        try:
            skills = await self._get_catalog()
        except Exception:
            return None
        matched = self._best_match(skills, tags)
        if matched is None:
            return None
        skill_path = matched.get("path") or matched.get("name", "")
        return await self._fetch_skill_json(skill_path)

    async def get_all_tags(self) -> list[str]:
        """Return a sorted, deduplicated list of tags from catalog.yaml.

        Tags are taken from explicit 'tags' fields on each skill entry.
        When no entry has a 'tags' field, individual words from descriptions
        are used as a fallback so that LLM tag vocabulary is never empty.

        Returns [] (never raises) on catalog failure.
        """
        try:
            skills = await self._get_catalog()
        except Exception:
            return []

        all_tags: set[str] = set()
        has_explicit_tags = any("tags" in s for s in skills)

        if has_explicit_tags:
            for skill in skills:
                all_tags.update(skill.get("tags", []))
        else:
            # Fallback: use description words + skill names as tags
            for skill in skills:
                desc = skill.get("description", "")
                name = skill.get("name", "")
                # Extract words from description and name
                words = _WORD_RE.findall((desc + " " + name).lower())
                # Filter out common stop-words and very short tokens
                all_tags.update(w for w in words if len(w) > 2)

        return sorted(all_tags)

    # ------------------------------------------------------------------
    # Catalog fetching and caching
    # ------------------------------------------------------------------

    async def _get_catalog(self) -> list[dict]:
        """Return catalog skills list, using in-memory TTL cache when valid."""
        now = time.monotonic()
        if self._catalog_cache is not None and now < self._catalog_cache[0]:
            return self._catalog_cache[1]  # cache hit

        skills = await self._fetch_catalog_yaml()
        if skills:  # Only cache non-empty success (never cache failures)
            self._catalog_cache = (now + _TTL_SECONDS, skills)
        return skills

    async def _fetch_catalog_yaml(self) -> list[dict]:
        """Read and parse catalog.yaml from the local git clone. Returns [] on any failure."""
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

    # ------------------------------------------------------------------
    # Skill file fetching
    # ------------------------------------------------------------------

    async def _fetch_skill_json(self, skill_path: str) -> SkillDefinition | None:
        """Read skills.json for a given skill path from the local clone. Returns None on failure.

        The local clone stores skill metadata in skills/<path>/skills.json (plural).
        The first tool in the 'tools' array provides the input_schema.
        SkillDefinition.path is set to the absolute local .ts path (Phase 6 contract).
        """
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

        # Extract from top-level or first tool entry
        tools: list[dict] = data.get("tools", [])
        first_tool: dict = tools[0] if tools else {}

        name: str = data.get("name") or first_tool.get("name") or skill_path
        description: str = (
            data.get("description")
            or first_tool.get("description")
            or ""
        )
        # input_schema may be under the first tool as 'input_schema' or 'parameters'
        input_schema: dict = (
            first_tool.get("input_schema")
            or first_tool.get("parameters")
            or {"type": "object", "properties": {}}
        )
        allow_net_domains: list[str] = data.get("allow_net_domains") or []

        # KEY CHANGE: absolute local path (not a URL)
        entry_point: str = data.get("entry_point") or "index.ts"
        absolute_ts_path = skill_dir / entry_point

        return SkillDefinition(
            name=name,
            description=description,
            path=str(absolute_ts_path),  # absolute local path — Phase 6 contract
            input_schema=input_schema,
            allow_net_domains=allow_net_domains,
        )

    # ------------------------------------------------------------------
    # Tag matching
    # ------------------------------------------------------------------

    def _best_match(self, skills: list[dict], tags: list[str]) -> dict | None:
        """Return the skill with the most tag overlaps (OR logic).

        When a skill has no 'tags' field, falls back to matching against words
        extracted from its description and name (case-insensitive).

        Ties resolved by catalog order (first wins). Returns None when no skill
        has any overlap with the queried tags.
        """
        query_tags_lower = {t.lower() for t in tags}
        best: dict | None = None
        best_score = 0

        for skill in skills:
            if "tags" in skill:
                skill_tags_lower = {t.lower() for t in skill["tags"]}
                score = len(query_tags_lower & skill_tags_lower)
            else:
                # Fallback: match against description words and skill name
                desc = skill.get("description", "")
                name = skill.get("name", "")
                skill_words = set(_WORD_RE.findall((desc + " " + name).lower()))
                score = len(query_tags_lower & skill_words)

            if score > best_score:
                best_score = score
                best = skill

        return best if best_score > 0 else None

    # ------------------------------------------------------------------
    # Error logging
    # ------------------------------------------------------------------

    def _log_error(self, source: str, reason: str) -> None:
        """Append a catalog_error record to routing.jsonl (synchronous, append-mode).

        The JSONL record uses key "url" (not "source") for backward compat with log parsers.
        """
        record = {
            "type": "catalog_error",
            "url": source,
            "reason": reason,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
