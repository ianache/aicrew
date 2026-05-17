"""
Tests for CatalogExplorer — live GitHub hits per project decision (no mocks for HTTP).

Covers:
- TTL cache behavior (monkeypatching _fetch_catalog_yaml)
- Tag matching logic (_best_match, find, get_all_tags)
- GITHUB_TOKEN auth header construction
- Failure soft-catching (non-200, network exception)

NOTE: Tests marked with @pytest.mark.live hit raw.githubusercontent.com directly.
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
    """Config with a fake GitHub token — used to test auth header injection."""
    return Config(
        gemini_api_key="test-key",
        github_token="fake-token-abc123",
        confidence_threshold=0.72,
        model_version="gemini-2.5-flash-001",
    )


@pytest.fixture
def config_no_token() -> Config:
    """Config without a GitHub token — used to test absent auth header."""
    return Config(
        gemini_api_key="test-key",
        github_token=None,
        confidence_threshold=0.72,
        model_version="gemini-2.5-flash-001",
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
    load_dotenv()
    return Config(
        gemini_api_key=os.environ.get("GEMINI_API_KEY", "placeholder-not-needed-for-catalog"),
        github_token=os.environ.get("GITHUB_TOKEN"),
        confidence_threshold=0.72,
        model_version="gemini-2.5-flash-001",
    )


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

    async def test_cache_hit_skips_network(self, config_no_token: Config) -> None:
        """Second call within TTL must reuse cached result — _fetch_catalog_yaml not called again."""
        explorer = CatalogExplorer(config_no_token)
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

    async def test_cache_miss_after_expiry(self, config_no_token: Config) -> None:
        """After TTL expires, a fresh fetch must be performed."""
        explorer = CatalogExplorer(config_no_token)
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

    async def test_failed_fetch_not_cached(self, config_no_token: Config) -> None:
        """Empty/failed fetch results must NOT be stored in _catalog_cache."""
        explorer = CatalogExplorer(config_no_token)

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

    def test_best_match_wins(self, config_no_token: Config) -> None:
        """Skill with more tag overlaps must be preferred over one with fewer."""
        explorer = CatalogExplorer(config_no_token)
        skill_a = {"path": "alpha", "name": "alpha", "description": "foo", "tags": ["x"]}
        skill_b = {"path": "beta", "name": "beta", "description": "bar", "tags": ["x", "y", "z"]}
        result = explorer._best_match([skill_a, skill_b], ["x", "y"])
        assert result is not None
        assert result["path"] == "beta"

    def test_ties_resolved_by_catalog_order(self, config_no_token: Config) -> None:
        """On equal overlap count, the skill appearing first in the catalog wins."""
        explorer = CatalogExplorer(config_no_token)
        skill_a = {"path": "alpha", "name": "alpha", "description": "foo", "tags": ["x"]}
        skill_b = {"path": "beta", "name": "beta", "description": "bar", "tags": ["x"]}
        result = explorer._best_match([skill_a, skill_b], ["x"])
        assert result is not None
        assert result["path"] == "alpha"

    def test_no_match_returns_none(self, config_no_token: Config) -> None:
        """When no skill has any tag overlap, _best_match must return None."""
        explorer = CatalogExplorer(config_no_token)
        skill = {"path": "alpha", "name": "alpha", "description": "irrelevant", "tags": ["math"]}
        result = explorer._best_match([skill], ["zzz_nonexistent_xyz"])
        assert result is None

    def test_description_fallback_matching(self, config_no_token: Config) -> None:
        """When skill has no 'tags' field, match against description words."""
        explorer = CatalogExplorer(config_no_token)
        skill = {"path": "calc", "name": "calc", "description": "Basic math calculator operations"}
        result = explorer._best_match([skill], ["calculator"])
        assert result is not None
        assert result["path"] == "calc"


# ---------------------------------------------------------------------------
# find() — live GitHub integration
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestFindLive:
    """Live GitHub hits — requires network and GITHUB_TOKEN in .env for rate limit headroom."""

    async def test_find_returns_skill_definition_on_tag_match(self, live_config: Config) -> None:
        """find() with a tag present in catalog descriptions returns a SkillDefinition."""
        explorer = CatalogExplorer(live_config)
        # "calculator" appears in the catalog (skill name + description)
        result = await explorer.find(["calculator"])
        assert result is not None, "Expected a SkillDefinition for tag='calculator', got None"
        assert isinstance(result, SkillDefinition)
        assert result.name, "SkillDefinition.name must be non-empty"
        assert result.description, "SkillDefinition.description must be non-empty"
        assert "/" not in result.path, (
            f"path must be bare skill name with no '/' prefix, got: {result.path!r}"
        )

    async def test_find_returns_none_on_no_tag_match(self, live_config: Config) -> None:
        """find() with a tag matching nothing in the catalog returns None without raising."""
        explorer = CatalogExplorer(live_config)
        result = await explorer.find(["zzz_nonexistent_tag_xyz"])
        assert result is None

    async def test_find_returns_none_on_github_failure(self, config_no_token: Config) -> None:
        """find() must return None (not raise) when _fetch_catalog_yaml fails."""
        explorer = CatalogExplorer(config_no_token)

        async def raise_network_error() -> list[dict]:
            import httpx
            raise httpx.ConnectError("simulated network failure")

        explorer._fetch_catalog_yaml = raise_network_error  # type: ignore[method-assign]

        result = await explorer.find(["calculator"])
        assert result is None


# ---------------------------------------------------------------------------
# get_all_tags() behavior
# ---------------------------------------------------------------------------

class TestGetAllTags:
    """get_all_tags() returns sorted, deduplicated list of tags across all catalog skills."""

    async def test_get_all_tags_returns_sorted_deduplicated(self, live_config: Config) -> None:
        """Live GitHub call: get_all_tags() returns a non-empty sorted list with no duplicates."""
        explorer = CatalogExplorer(live_config)
        tags = await explorer.get_all_tags()
        assert isinstance(tags, list), "get_all_tags() must return list[str]"
        assert len(tags) > 0, "Expected non-empty tag list from live catalog"
        assert tags == sorted(tags), "Tags must be sorted alphabetically"
        assert tags == sorted(set(tags)), "Tags must be deduplicated"

    async def test_get_all_tags_returns_empty_on_failure(self, config_no_token: Config) -> None:
        """When _fetch_catalog_yaml returns [], get_all_tags() returns []."""
        explorer = CatalogExplorer(config_no_token)

        async def fake_empty() -> list[dict]:
            return []

        explorer._fetch_catalog_yaml = fake_empty  # type: ignore[method-assign]

        tags = await explorer.get_all_tags()
        assert tags == []

    async def test_get_all_tags_returns_empty_on_github_failure(self, config_no_token: Config) -> None:
        """When _fetch_catalog_yaml raises, get_all_tags() returns [] and does NOT raise."""
        explorer = CatalogExplorer(config_no_token)

        async def raise_network_error() -> list[dict]:
            import httpx
            raise httpx.ConnectError("simulated network failure")

        explorer._fetch_catalog_yaml = raise_network_error  # type: ignore[method-assign]

        tags = await explorer.get_all_tags()
        assert tags == []


# ---------------------------------------------------------------------------
# GITHUB_TOKEN auth header
# ---------------------------------------------------------------------------

class TestAuthHeader:
    """_auth_headers() returns the Authorization header when a token is configured."""

    def test_auth_header_present_when_token_set(self, config_with_token: Config) -> None:
        """When github_token is set, _auth_headers() returns Authorization: Bearer header."""
        explorer = CatalogExplorer(config_with_token)
        headers = explorer._auth_headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer fake-token-abc123"

    def test_auth_header_absent_when_token_none(self, config_no_token: Config) -> None:
        """When github_token is None, _auth_headers() returns an empty dict."""
        explorer = CatalogExplorer(config_no_token)
        headers = explorer._auth_headers()
        assert headers == {}


# ---------------------------------------------------------------------------
# Failure soft-catching and error logging
# ---------------------------------------------------------------------------

class TestFailureHandling:
    """GitHub failures must be swallowed — never raise — and logged to routing.jsonl."""

    async def test_catalog_error_logged_on_non_200(
        self, config_no_token: Config, tmp_path: Path
    ) -> None:
        """Non-200 response from GitHub must produce a catalog_error record in routing.jsonl."""
        import httpx

        explorer = CatalogExplorer(config_no_token)

        # Override log path to tmp_path to avoid touching real logs/ dir in tests
        import src.catalog_explorer as ce_module
        original_log_path = ce_module._LOG_PATH
        ce_module._LOG_PATH = tmp_path / "routing.jsonl"

        try:
            # Simulate non-200 by patching httpx.AsyncClient.get
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_response.text = ""

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_instance = AsyncMock()
                mock_instance.get = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                await explorer._fetch_catalog_yaml()

            log_path = tmp_path / "routing.jsonl"
            assert log_path.exists(), "routing.jsonl must be created on catalog error"
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 1, f"Expected 1 log line, got {len(lines)}"
            record = json.loads(lines[0])
            assert record.get("type") == "catalog_error"
            assert "url" in record
            assert "reason" in record
            assert "ts" in record
        finally:
            ce_module._LOG_PATH = original_log_path
