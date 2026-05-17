"""
TDD test suite for CoordinatingAgent and Config — Phase 3, Plan 03-01.

Tests cover:
- Config.from_env(): defaults, env overrides, missing GEMINI_API_KEY
- CoordinatingAgent routing: high-confidence, low-confidence, no-skill-found paths
- JSONL routing log: structure, append behavior
- Pass 1 tag vocabulary constraint
- Tool isolation across consecutive run() calls

All tests use AsyncMock stubs for CatalogExplorer and SkillInjector — no live ADK calls.
Runner.run_async() is patched per-test via an async generator mock.
InMemorySessionService.get_session / create_session are patched to inject session state.

asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio decorators needed.
"""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.config import Config
from src.agent import CoordinatingAgent
from src.models.skill import SkillDefinition


# ---------------------------------------------------------------------------
# Helper: async generator mock for runner.run_async()
# ---------------------------------------------------------------------------

def _make_run_async_mock(text: str = "mock answer"):
    """Return an async generator function that yields one final-response event."""
    async def _mock_run_async(*args, **kwargs):
        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_part = MagicMock()
        mock_part.text = text
        mock_part.thought = False
        mock_event.content = MagicMock()
        mock_event.content.parts = [mock_part]
        yield mock_event

    return _mock_run_async


def _make_session_mock(confidence: float, tags: list[str], session_id: str = "test-session"):
    """Return a MagicMock Session with routing state pre-populated."""
    mock_session = MagicMock()
    mock_session.state = {"routing": {"confidence": confidence, "tags": tags}}
    mock_session.id = session_id
    return mock_session


def _build_agent_with_mocks(
    mock_catalog_explorer,
    mock_skill_injector,
    sample_config,
    confidence: float,
    tags: list[str],
    run_text: str = "mock answer",
):
    """Construct a CoordinatingAgent with mocked Runner and SessionService injected."""
    agent = CoordinatingAgent(
        catalog_explorer=mock_catalog_explorer,
        skill_injector=mock_skill_injector,
        config=sample_config,
    )

    mock_session = _make_session_mock(confidence, tags)

    # Patch session service on the agent instance
    agent._session_service.create_session = AsyncMock(return_value=mock_session)
    agent._session_service.get_session = AsyncMock(return_value=mock_session)

    # Patch runner.run_async on the instance
    agent._runner.run_async = _make_run_async_mock(run_text)

    return agent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_skill_injector(sample_skill_def):
    """A MagicMock-backed SkillInjector stub for CoordinatingAgent tests."""
    injector = MagicMock()
    mock_tool = MagicMock()
    injector.build_tool = AsyncMock(return_value=(mock_tool, "# SKILL.md content"))
    return injector


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    """Redirect routing JSONL log to a temporary path for isolation."""
    import src.agent as agent_module
    log_file = tmp_path / "routing.jsonl"
    monkeypatch.setattr(agent_module, "_LOG_PATH", log_file)
    return log_file


# ---------------------------------------------------------------------------
# TestConfig — Config.from_env() behavior
# ---------------------------------------------------------------------------

class TestConfig:

    def test_config_reads_defaults(self, monkeypatch):
        """Config.from_env() reads defaults when only GEMINI_API_KEY is set."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.delenv("CONFIDENCE_THRESHOLD", raising=False)
        monkeypatch.delenv("MODEL_VERSION", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = Config.from_env()

        assert config.gemini_api_key == "test-key-123"
        assert config.confidence_threshold == 0.72
        assert config.model_version == "gemini-2.5-flash-001"
        assert config.github_token is None

    def test_config_reads_env_overrides(self, monkeypatch):
        """Config.from_env() applies overrides for CONFIDENCE_THRESHOLD and MODEL_VERSION."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-456")
        monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.5")
        monkeypatch.setenv("MODEL_VERSION", "gemini-2.5-pro")

        config = Config.from_env()

        assert config.confidence_threshold == 0.5
        assert config.model_version == "gemini-2.5-pro"

    def test_config_raises_without_gemini_key(self, monkeypatch):
        """Config.from_env() raises KeyError when GEMINI_API_KEY is not set."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with pytest.raises(KeyError):
            Config.from_env()


# ---------------------------------------------------------------------------
# TestCoordinatingAgentRouting — run() path coverage
# ---------------------------------------------------------------------------

class TestCoordinatingAgentRouting:

    async def test_high_confidence_skips_catalog(
        self, mock_catalog_explorer, mock_skill_injector, sample_config, log_path
    ):
        """High-confidence path: catalog_explorer.find is NOT called; decision='direct_answer'."""
        agent = _build_agent_with_mocks(
            mock_catalog_explorer, mock_skill_injector, sample_config,
            confidence=0.85, tags=["evaluation"],
        )

        result = await agent.run("What is 2 + 2?")

        # CatalogExplorer.find must not be called on high-confidence prompts
        mock_catalog_explorer.find.assert_not_called()

        # JSONL log must record 'direct_answer' decision
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        record = json.loads(lines[-1])
        assert record["decision"] == "direct_answer"

    async def test_low_confidence_routes_to_catalog(
        self, mock_catalog_explorer, mock_skill_injector, sample_config, log_path, sample_skill_def
    ):
        """Low-confidence path: find() is called with extracted tags; decision='catalog_route'."""
        agent = _build_agent_with_mocks(
            mock_catalog_explorer, mock_skill_injector, sample_config,
            confidence=0.4, tags=["evaluation"],
        )

        await agent.run("Evaluate this test case for me")

        # CatalogExplorer.find must be called with the extracted tags
        mock_catalog_explorer.find.assert_called_once_with(["evaluation"])

        # SkillInjector.build_tool must be called with the returned SkillDefinition
        mock_skill_injector.build_tool.assert_called_once_with(sample_skill_def)

        # JSONL log must record 'catalog_route' decision
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        record = json.loads(lines[-1])
        assert record["decision"] == "catalog_route"

    async def test_low_confidence_no_skill_found(
        self, mock_catalog_explorer, mock_skill_injector, sample_config, log_path
    ):
        """When catalog returns None, run() returns a 'no skill found' message; decision='no_skill_found'."""
        mock_catalog_explorer.find = AsyncMock(return_value=None)

        agent = _build_agent_with_mocks(
            mock_catalog_explorer, mock_skill_injector, sample_config,
            confidence=0.3, tags=["unknown"],
        )

        result = await agent.run("Do something obscure")

        # Must include a human-readable 'no skill found' message
        assert "no" in result.lower() or "skill" in result.lower() or "found" in result.lower()

        # JSONL log must record 'no_skill_found'
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        record = json.loads(lines[-1])
        assert record["decision"] == "no_skill_found"


# ---------------------------------------------------------------------------
# TestRoutingLog — JSONL log structure and append behavior
# ---------------------------------------------------------------------------

class TestRoutingLog:

    async def test_routing_log_written(
        self, mock_catalog_explorer, mock_skill_injector, sample_config, log_path
    ):
        """After run(), logs/routing.jsonl contains a valid JSONL record with all required keys."""
        agent = _build_agent_with_mocks(
            mock_catalog_explorer, mock_skill_injector, sample_config,
            confidence=0.85, tags=["test"],
        )

        await agent.run("Test the routing log")

        assert log_path.exists(), "routing.jsonl was not created"
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert set(record.keys()) >= {"prompt_hash", "tags", "confidence", "decision", "skill_name", "ts"}

        # prompt_hash must be a 12-char hex string
        assert isinstance(record["prompt_hash"], str)
        assert len(record["prompt_hash"]) == 12
        assert all(c in "0123456789abcdef" for c in record["prompt_hash"])

        # confidence must be a float
        assert isinstance(record["confidence"], float)

        # ts must be a non-empty ISO string
        assert isinstance(record["ts"], str)
        assert len(record["ts"]) > 10

    async def test_routing_log_appends(
        self, mock_catalog_explorer, mock_skill_injector, sample_config, log_path
    ):
        """Two consecutive run() calls produce two JSONL lines (append, not overwrite)."""
        agent = _build_agent_with_mocks(
            mock_catalog_explorer, mock_skill_injector, sample_config,
            confidence=0.85, tags=["test"],
        )

        await agent.run("First prompt")
        await agent.run("Second prompt")

        lines = [
            l for l in log_path.read_text(encoding="utf-8").strip().split("\n") if l.strip()
        ]
        assert len(lines) == 2

        record1 = json.loads(lines[0])
        record2 = json.loads(lines[1])
        # The two prompts produce different hashes
        assert record1["prompt_hash"] != record2["prompt_hash"]


# ---------------------------------------------------------------------------
# TestPass1Vocabulary — tag vocabulary constraint
# ---------------------------------------------------------------------------

class TestPass1Vocabulary:

    async def test_pass1_uses_tag_vocabulary(
        self, mock_catalog_explorer, mock_skill_injector, sample_config, log_path
    ):
        """CoordinatingAgent calls catalog_explorer.get_all_tags() during construction or run()
        and includes the result in the Pass 1 system instruction."""
        agent = _build_agent_with_mocks(
            mock_catalog_explorer, mock_skill_injector, sample_config,
            confidence=0.85, tags=["test"],
        )

        await agent.run("Any prompt")

        # get_all_tags() must have been called (to constrain Pass 1 vocabulary)
        mock_catalog_explorer.get_all_tags.assert_called()

        # The tag vocabulary should appear in the Pass 1 agent's instruction
        pass1_instruction = agent._pass1_agent.instruction
        assert "evaluation" in pass1_instruction or "test" in pass1_instruction, (
            f"Expected tag vocabulary in Pass 1 instruction, got: {pass1_instruction!r}"
        )


# ---------------------------------------------------------------------------
# TestToolIsolation — tool not shared across consecutive run() calls
# ---------------------------------------------------------------------------

class TestToolIsolation:

    async def test_tools_not_shared_across_runs(
        self, mock_catalog_explorer, mock_skill_injector, sample_config, log_path
    ):
        """Two low-confidence run() calls each invoke build_tool() independently."""
        agent = _build_agent_with_mocks(
            mock_catalog_explorer, mock_skill_injector, sample_config,
            confidence=0.3, tags=["evaluation"],
        )

        await agent.run("First evaluation prompt")
        await agent.run("Second evaluation prompt")

        # build_tool() must be called once per low-confidence run — not shared
        assert mock_skill_injector.build_tool.call_count == 2
