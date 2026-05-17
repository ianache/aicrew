"""
Shared pytest fixtures for all test modules.

Provides:
- sample_skill_def: a SkillDefinition instance for use in Phase 2 + Phase 3 tests
- mock_catalog_explorer: an AsyncMock-backed CatalogExplorer stub for Phase 3 tests
- sample_config: a Config instance with test defaults for Phase 3 tests
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.models.skill import SkillDefinition


@pytest.fixture
def sample_skill_def() -> SkillDefinition:
    """A minimal SkillDefinition used in SkillInjector and CoordinatingAgent tests."""
    return SkillDefinition(
        name="evaluar_test_case",
        description="Evaluates a test case",
        path="evaluar_test_case",
        input_schema={
            "type": "object",
            "properties": {"test_case": {"type": "string"}},
            "required": ["test_case"],
        },
        allow_net_domains=["github.com"],
    )


@pytest.fixture
def mock_catalog_explorer(sample_skill_def: SkillDefinition) -> MagicMock:
    """A MagicMock-backed CatalogExplorer stub exposing the two methods
    CoordinatingAgent requires: find() and get_all_tags()."""
    explorer = MagicMock()
    explorer.find = AsyncMock(return_value=sample_skill_def)
    explorer.get_all_tags = AsyncMock(
        return_value=["evaluation", "test", "story", "review"]
    )
    return explorer


@pytest.fixture
def sample_config():
    """A Config instance with test-safe defaults (no GEMINI_API_KEY env read)."""
    from src.config import Config

    return Config(
        gemini_api_key="test-api-key",
        github_token=None,
        confidence_threshold=0.72,
        model_version="gemini-2.5-flash-001",
    )
