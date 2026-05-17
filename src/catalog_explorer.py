"""
CatalogExplorer — GitHub-backed skill discovery with 5-minute TTL cache.

Fetches catalog.yaml from the GitHub SSOT at raw.githubusercontent.com/ianache/skills-catalog
(CDN-backed, no API rate limit). Caches the result for _TTL_SECONDS to avoid rate exhaustion.

GITHUB_TOKEN is injected via Config — when set, all HTTP requests include an
Authorization: Bearer header (raises GitHub rate limit from 60 to 5000 req/hr).

All failures (non-200, network exception, parse error) are soft-caught: find() returns None,
get_all_tags() returns []. Every failure is logged as a catalog_error record to routing.jsonl.

Tag matching uses OR logic (any overlap qualifies) with the highest overlap count winning.
When a catalog entry has no explicit 'tags' field, matching falls back to words in the
description — this handles the current ianache/skills-catalog structure where tags are
embedded in descriptions rather than a dedicated field.

Skill metadata is loaded from skills/<path>/skills.json (note plural). The first tool in
the 'tools' array provides the name, description, and input_schema for SkillDefinition.
allow_net_domains is read from the skill's top-level key if present, otherwise defaults to [].
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from src.config import Config
from src.models.skill import SkillDefinition

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_LOG_PATH = Path("logs/routing.jsonl")
_TTL_SECONDS = 300  # 5-minute TTL for catalog.yaml cache
_BASE_URL = "https://raw.githubusercontent.com/ianache/skills-catalog/main"

# Regex to split description text into individual words for tag matching fallback
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


class CatalogExplorer:
    """Discovers skills from the GitHub catalog, with TTL caching and GITHUB_TOKEN support.

    Constructor args:
        config: Config — provides github_token for auth headers.

    Public interface (duck-typed by CoordinatingAgent):
        async find(tags: list[str]) -> SkillDefinition | None
        async get_all_tags() -> list[str]
    """

    def __init__(self, config: Config) -> None:
        self._config = config
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
    # Auth helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict:
        """Return Authorization header dict when github_token is configured, else {}."""
        if self._config.github_token:
            return {"Authorization": f"Bearer {self._config.github_token}"}
        return {}

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
        """Fetch and parse catalog.yaml from GitHub. Returns [] on any failure."""
        url = f"{_BASE_URL}/catalog.yaml"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=self._auth_headers())
            if response.status_code != 200:
                self._log_error(url, f"HTTP {response.status_code}")
                return []
            data = yaml.safe_load(response.text)
            if isinstance(data, dict):
                return data.get("skills", [])
            return []
        except Exception as exc:
            self._log_error(url, str(exc))
            return []

    # ------------------------------------------------------------------
    # Skill file fetching
    # ------------------------------------------------------------------

    async def _fetch_skill_json(self, skill_path: str) -> SkillDefinition | None:
        """Fetch skills.json for a given skill path. Returns None on failure.

        The GitHub catalog stores skill metadata in skills/<path>/skills.json (plural).
        The first tool in the 'tools' array provides the input_schema.
        """
        url = f"{_BASE_URL}/skills/{skill_path}/skills.json"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=self._auth_headers())
            if response.status_code != 200:
                self._log_error(url, f"HTTP {response.status_code}")
                return None
            data: dict = json.loads(response.text)
        except Exception as exc:
            self._log_error(url, str(exc))
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

        return SkillDefinition(
            name=name,
            description=description,
            path=skill_path,  # Bare name — no 'skills/' prefix (02-01 decision)
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

    def _log_error(self, url: str, reason: str) -> None:
        """Append a catalog_error record to routing.jsonl (synchronous, append-mode)."""
        record = {
            "type": "catalog_error",
            "url": url,
            "reason": reason,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
