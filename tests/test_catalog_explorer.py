"""
Tests for CatalogExplorer — Phase 6 refactored to use local SkillCache.

Covers:
- TTL cache behavior (monkeypatching _fetch_catalog_yaml)
- Tag matching logic (_best_match, find, get_all_tags)
- Failure soft-catching (file not found, exception)

NOTE: Tests marked with @pytest.mark.live trigger a real git clone / pull via SkillCache.
All other tests use a mock_skill_cache fixture — no network I/O.
All tests are async (asyncio_mode = auto in pyproject.toml).
"""
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.config import Config
from src.catalog_explorer import CatalogExplorer
from src.models.skill import SkillDefinition


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config_with_token() -> Config:
    """Config with a fake GitHub token — kept for fixture compat."""
    from pathlib import Path

    return Config(
        gemini_api_key="test-key",
        github_token="fake-token-abc123",
        confidence_threshold=0.72,
        model_version="gemini-2.5-flash",
        skills_cache_dir=Path(".skills-cache"),
        skills_cache_ttl=300,
    )


@pytest.fixture
def config_no_token() -> Config:
    """Config without a GitHub token."""
    from pathlib import Path

    return Config(
        gemini_api_key="test-key",
        github_token=None,
        confidence_threshold=0.72,
        model_version="gemini-2.5-flash",
        skills_cache_dir=Path(".skills-cache"),
        skills_cache_ttl=300,
    )


@pytest.fixture
def live_config() -> Config:
    """Config loaded from real environment — used for live GitHub tests.

    Loads .env via python-dotenv so GITHUB_TOKEN is available for authenticated
    catalog fetches. Uses a placeholder GEMINI_API_KEY when not set (live catalog
    tests only hit GitHub, not Gemini).
    """
    import os
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv()
    return Config(
        gemini_api_key=os.environ.get("GEMINI_API_KEY", "placeholder-not-needed-for-catalog"),
        github_token=os.environ.get("GITHUB_TOKEN"),
        confidence_threshold=0.72,
        model_version="gemini-2.5-flash",
        skills_cache_dir=Path(".skills-cache"),
        skills_cache_ttl=300,
    )


@pytest.fixture
def mock_skill_cache():
    """AsyncMock-backed SkillCache — returns a fake path on ensure_synced()."""
    cache = AsyncMock()
    cache.ensure_synced = AsyncMock(return_value=Path("/fake/.skills-cache"))
    return cache


def _make_skill_entries(*names_and_descs: tuple[str, str, str]) -> list[dict]:
    """Build minimal catalog skill entries for unit tests.
    Each tuple: (path, name, description).
    """
    return [
        {"path": path, "name": name, "description": desc}
        for path, name, desc in names_and_descs
    ]


# ---------------------------------------------------------------------------
# TTL cache behavior
# ---------------------------------------------------------------------------

class TestTTLCache:
    """CatalogExplorer caches the catalog.yaml result for 5 minutes (300 s)."""

    async def test_cache_hit_skips_network(
        self, config_no_token: Config, mock_skill_cache
    ) -> None:
        """Second call within TTL must reuse cached result — _fetch_catalog_yaml not called again."""
        explorer = CatalogExplorer(config_no_token, mock_skill_cache)
        fake_skills = _make_skill_entries(("calculator", "calculator", "Basic math calculator"))

        call_count = 0

        async def fake_fetch() -> list[dict]:
            nonlocal call_count
            call_count += 1
            return fake_skills

        explorer._fetch_catalog_yaml = fake_fetch  # type: ignore[method-assign]

        # First call — populates cache
        await explorer._get_catalog()
        # Second call — must hit cache
        await explorer._get_catalog()

        assert call_count == 1, f"Expected 1 network call, got {call_count}"

    async def test_cache_miss_after_expiry(
        self, config_no_token: Config, mock_skill_cache
    ) -> None:
        """After TTL expires, a fresh fetch must be performed."""
        explorer = CatalogExplorer(config_no_token, mock_skill_cache)
        fake_skills = _make_skill_entries(("calculator", "calculator", "Basic math calculator"))

        # Pre-seed an expired cache entry (timestamp in the past)
        explorer._catalog_cache = (time.monotonic() - 1, fake_skills)

        call_count = 0

        async def fake_fetch() -> list[dict]:
            nonlocal call_count
            call_count += 1
            return fake_skills

        explorer._fetch_catalog_yaml = fake_fetch  # type: ignore[method-assign]

        await explorer._get_catalog()

        assert call_count == 1, "Expected 1 network call after cache expiry"

    async def test_failed_fetch_not_cached(
        self, config_no_token: Config, mock_skill_cache
    ) -> None:
        """Empty/failed fetch results must NOT be stored in _catalog_cache."""
        explorer = CatalogExplorer(config_no_token, mock_skill_cache)

        async def fake_fetch_empty() -> list[dict]:
            return []

        explorer._fetch_catalog_yaml = fake_fetch_empty  # type: ignore[method-assign]

        await explorer._get_catalog()

        assert explorer._catalog_cache is None, (
            "_catalog_cache must remain None after a failed/empty fetch"
        )


# ---------------------------------------------------------------------------
# Tag matching (OR logic, best match wins)
# ---------------------------------------------------------------------------

class TestTagMatching:
    """_best_match implements OR logic: count overlapping tags, highest count wins."""

    def test_best_match_wins(self, config_no_token: Config, mock_skill_cache) -> None:
        """Skill with more tag overlaps must be preferred over one with fewer."""
        explorer = CatalogExplorer(config_no_token, mock_skill_cache)
        skill_a = {"path": "alpha", "name": "alpha", "description": "foo", "tags": ["x"]}
        skill_b = {"path": "beta", "name": "beta", "description": "bar", "tags": ["x", "y", "z"]}
        result = explorer._best_match([skill_a, skill_b], ["x", "y"])
        assert result is not None
        assert result["path"] == "beta"

    def test_ties_resolved_by_catalog_order(
        self, config_no_token: Config, mock_skill_cache
    ) -> None:
        """On equal overlap count, the skill appearing first in the catalog wins."""
        explorer = CatalogExplorer(config_no_token, mock_skill_cache)
        skill_a = {"path": "alpha", "name": "alpha", "description": "foo", "tags": ["x"]}
        skill_b = {"path": "beta", "name": "beta", "description": "bar", "tags": ["x"]}
        result = explorer._best_match([skill_a, skill_b], ["x"])
        assert result is not None
        assert result["path"] == "alpha"

    def test_no_match_returns_none(
        self, config_no_token: Config, mock_skill_cache
    ) -> None:
        """When no skill has any tag overlap, _best_match must return None."""
        explorer = CatalogExplorer(config_no_token, mock_skill_cache)
        skill = {"path": "alpha", "name": "alpha", "description": "irrelevant", "tags": ["math"]}
        result = explorer._best_match([skill], ["zzz_nonexistent_xyz"])
        assert result is None

    def test_description_fallback_matching(
        self, config_no_token: Config, mock_skill_cache
    ) -> None:
        """When skill has no 'tags' field, match against description words."""
        explorer = CatalogExplorer(config_no_token, mock_skill_cache)
        skill = {"path": "calc", "name": "calc", "description": "Basic math calculator operations"}
        result = explorer._best_match([skill], ["calculator"])
        assert result is not None
        assert result["path"] == "calc"


# ---------------------------------------------------------------------------
# find() — live GitHub integration
# ---------------------------------------------------------------------------

def _seed_cache(tmp_path) -> None:
    """Helper to seed the temporary git cache from the workspace .skills-cache.
    This avoids slow or failing git clones in network-constrained environments.
    """
    workspace_cache = Path(__file__).parents[1] / ".skills-cache"
    temp_cache_dir = tmp_path / ".skills-cache"
    if workspace_cache.exists():
        import shutil
        shutil.copytree(workspace_cache, temp_cache_dir, ignore=shutil.ignore_patterns(".git"))
        (temp_cache_dir / ".git").mkdir(parents=True, exist_ok=True)


@pytest.mark.live
class TestFindLive:
    """Live GitHub hits — requires network and GITHUB_TOKEN in .env for rate limit headroom."""

    async def test_find_returns_skill_definition_on_tag_match(
        self, live_config: Config, tmp_path
    ) -> None:
        """find() with a tag present in catalog descriptions returns a SkillDefinition."""
        _seed_cache(tmp_path)
        from src.skill_cache import SkillCache
        skill_cache = SkillCache(
            repo_url="https://github.com/ianache/skills-catalog",
            cache_dir=tmp_path / ".skills-cache",
            ttl_seconds=300,
        )
        explorer = CatalogExplorer(live_config, skill_cache)
        # "calculate" is a tag in the catalog for the calculator skill
        result = await explorer.find(["calculate"])
        assert result is not None, "Expected a SkillDefinition for tag='calculate', got None"
        assert isinstance(result, SkillDefinition)
        assert result.name, "SkillDefinition.name must be non-empty"
        assert result.description, "SkillDefinition.description must be non-empty"
        from pathlib import Path as _Path
        assert _Path(result.path).is_absolute(), (
            f"Expected absolute path, got: {result.path!r}"
        )
        assert result.path.endswith(".ts"), (
            f"Expected .ts entry point, got: {result.path!r}"
        )

    async def test_find_returns_none_on_no_tag_match(
        self, live_config: Config, tmp_path
    ) -> None:
        """find() with a tag matching nothing in the catalog returns None without raising."""
        _seed_cache(tmp_path)
        from src.skill_cache import SkillCache
        skill_cache = SkillCache(
            repo_url="https://github.com/ianache/skills-catalog",
            cache_dir=tmp_path / ".skills-cache",
            ttl_seconds=300,
        )
        explorer = CatalogExplorer(live_config, skill_cache)
        result = await explorer.find(["zzz_nonexistent_tag_xyz"])
        assert result is None

    async def test_find_returns_none_on_github_failure(
        self, config_no_token: Config, mock_skill_cache
    ) -> None:
        """find() must return None (not raise) when _fetch_catalog_yaml fails."""
        explorer = CatalogExplorer(config_no_token, mock_skill_cache)

        async def raise_network_error() -> list[dict]:
            raise Exception("simulated network failure")

        explorer._fetch_catalog_yaml = raise_network_error  # type: ignore[method-assign]

        result = await explorer.find(["calculator"])
        assert result is None


# ---------------------------------------------------------------------------
# get_all_tags() behavior
# ---------------------------------------------------------------------------

class TestGetAllTags:
    """get_all_tags() returns sorted, deduplicated list of tags across all catalog skills."""

    @pytest.mark.live
    async def test_get_all_tags_returns_sorted_deduplicated(
        self, live_config: Config, tmp_path
    ) -> None:
        """Live GitHub call: get_all_tags() returns a non-empty sorted list with no duplicates."""
        _seed_cache(tmp_path)
        from src.skill_cache import SkillCache
        skill_cache = SkillCache(
            repo_url="https://github.com/ianache/skills-catalog",
            cache_dir=tmp_path / ".skills-cache",
            ttl_seconds=300,
        )
        explorer = CatalogExplorer(live_config, skill_cache)
        tags = await explorer.get_all_tags()
        assert isinstance(tags, list), "get_all_tags() must return list[str]"
        assert len(tags) > 0, "Expected non-empty tag list from live catalog"
        assert tags == sorted(tags), "Tags must be sorted alphabetically"
        assert tags == sorted(set(tags)), "Tags must be deduplicated"

    async def test_get_all_tags_returns_empty_on_failure(
        self, config_no_token: Config, mock_skill_cache
    ) -> None:
        """When _fetch_catalog_yaml returns [], get_all_tags() returns []."""
        explorer = CatalogExplorer(config_no_token, mock_skill_cache)

        async def fake_empty() -> list[dict]:
            return []

        explorer._fetch_catalog_yaml = fake_empty  # type: ignore[method-assign]

        tags = await explorer.get_all_tags()
        assert tags == []

    async def test_get_all_tags_returns_empty_on_github_failure(
        self, config_no_token: Config, mock_skill_cache
    ) -> None:
        """When _fetch_catalog_yaml raises, get_all_tags() returns [] and does NOT raise."""
        explorer = CatalogExplorer(config_no_token, mock_skill_cache)

        async def raise_network_error() -> list[dict]:
            raise Exception("simulated network failure")

        explorer._fetch_catalog_yaml = raise_network_error  # type: ignore[method-assign]

        tags = await explorer.get_all_tags()
        assert tags == []


# ---------------------------------------------------------------------------
# Failure soft-catching and error logging
# ---------------------------------------------------------------------------

class TestFailureHandling:
    """Catalog failures must be swallowed — never raise — and logged to routing.jsonl."""

    async def test_catalog_error_logged_on_file_read_failure(
        self, config_no_token: Config, tmp_path: Path, mock_skill_cache
    ) -> None:
        """File read failure (catalog.yaml not found) must produce a catalog_error record."""
        import src.catalog_explorer as ce_module
        original_log_path = ce_module._LOG_PATH
        ce_module._LOG_PATH = tmp_path / "routing.jsonl"
        try:
            explorer = CatalogExplorer(config_no_token, mock_skill_cache)
            # ensure_synced succeeds but catalog.yaml does not exist in returned path
            mock_skill_cache.ensure_synced.return_value = tmp_path  # empty dir, no catalog.yaml
            await explorer._fetch_catalog_yaml()
            log_path = tmp_path / "routing.jsonl"
            assert log_path.exists(), "routing.jsonl must be created on catalog error"
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) >= 1, f"Expected at least 1 log line, got {len(lines)}"
            record = json.loads(lines[0])
            assert record.get("type") == "catalog_error"
            assert "url" in record
            assert "reason" in record
            assert "ts" in record
        finally:
            ce_module._LOG_PATH = original_log_path
