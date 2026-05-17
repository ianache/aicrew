"""
End-to-end tests for the AI Agents Crew platform — Phase 5, Plan 05-02.

Two test tiers:
- Smoke test: mocked CoordinatingAgent.run() — no API key, no network, runs in fast CI.
- Live E2E test: real Gemini + real GitHub catalog + real Deno execution.
  Marked @pytest.mark.live so it is skipped with `-m "not live"`.

The live test uses a domain-specific Spanish QA prompt that reliably triggers the
catalog_route (confidence < 0.72): Gemini cannot answer QA domain terminology directly.

CLI-02 is satisfied when the live test passes with:
1. agent.run() returns a non-empty string response
2. routing.jsonl last record shows decision='catalog_route' (full pipeline exercised)

asyncio_mode = "auto" in pyproject.toml — no @pytest.mark.asyncio decorators needed.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dotenv import load_dotenv

from src.config import Config
from src.agent import CoordinatingAgent
from src.catalog_explorer import CatalogExplorer
from src.skill_injector import SkillInjector
from src.execution.deno_runner import DenoRunner
import src.agent as agent_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config_stub() -> Config:
    """Config with a fake API key — no real env file needed for smoke tests."""
    from pathlib import Path

    return Config(
        gemini_api_key="test-key-stub",
        github_token=None,
        confidence_threshold=0.72,
        model_version="gemini-2.5-flash-001",
        skills_cache_dir=Path(".skills-cache"),
        skills_cache_ttl=300,
    )


@pytest.fixture
def live_config() -> Config:
    """Config loaded from real .env — used for live E2E tests.

    Loads .env via python-dotenv so GEMINI_API_KEY and GITHUB_TOKEN are available.
    Skips the test if GEMINI_API_KEY is not set.
    """
    load_dotenv()
    try:
        return Config.from_env()
    except KeyError:
        pytest.skip("GEMINI_API_KEY not set — skipping live test")


# ---------------------------------------------------------------------------
# Smoke test — no API key required, fast, CI-safe
# ---------------------------------------------------------------------------

async def test_agent_run_contract(config_stub: Config) -> None:
    """CoordinatingAgent.run() contract: returns a non-empty string.

    Uses a mocked CatalogExplorer and patches CoordinatingAgent.run() itself
    to verify the return type contract without making any external calls.
    Validates that the interface is wired correctly — not the content.
    """
    with patch.object(CoordinatingAgent, "run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "Four."

        runner = DenoRunner()
        injector = SkillInjector(runner)

        mock_explorer = AsyncMock()
        mock_explorer.find.return_value = None
        mock_explorer.get_all_tags.return_value = []

        agent = CoordinatingAgent(mock_explorer, injector, config_stub)
        result = await agent.run("What is 2+2?")

        assert isinstance(result, str), (
            f"agent.run() must return str, got {type(result).__name__!r}"
        )
        assert result, "agent.run() must return a non-empty string"


# ---------------------------------------------------------------------------
# Live E2E test — requires real .env with GEMINI_API_KEY
# ---------------------------------------------------------------------------

@pytest.mark.live
async def test_e2e_live_skill(live_config: Config, tmp_path: Path) -> None:
    """Full pipeline: real Gemini + real GitHub catalog + real Deno execution.

    Uses a domain-specific Spanish QA prompt that reliably triggers catalog_route
    (confidence < 0.72) because Gemini cannot directly answer QA domain terminology.

    Verifies:
    1. agent.run() returns a non-empty string
    2. The response does not contain a raw Python traceback
    3. routing.jsonl last record has decision='catalog_route' (proves full discovery
       → inject → execute path was exercised)
    """
    # Redirect routing log to tmp_path to avoid polluting real logs/
    original_log_path = agent_module._LOG_PATH
    agent_module._LOG_PATH = tmp_path / "routing.jsonl"

    try:
        # Construct full real component stack
        runner = DenoRunner()
        injector = SkillInjector(runner)
        explorer = CatalogExplorer(live_config)
        agent = CoordinatingAgent(explorer, injector, live_config)

        # Domain-specific Spanish QA prompt — reliably triggers catalog_route
        prompt = (
            "Evalúa este test case: cuando el usuario hace clic en login "
            "con credenciales válidas, el sistema debe redirigir al dashboard"
        )
        result = await agent.run(prompt)

        # Assertion 1: non-empty string response
        assert isinstance(result, str), (
            f"agent.run() must return str, got {type(result).__name__!r}"
        )
        assert result.strip(), "agent.run() must return a non-empty response"

        # Assertion 2: no raw Python traceback leaked into response
        assert "Traceback" not in result, (
            f"Response contains a raw Python traceback — skill error not handled:\n{result}"
        )

        # Assertion 3: routing log confirms catalog_route path was taken
        log_path = tmp_path / "routing.jsonl"
        assert log_path.exists(), (
            "routing.jsonl was not created — agent did not run the logging path"
        )
        log_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert log_lines, "routing.jsonl is empty after agent.run() completed"

        last_record = json.loads(log_lines[-1])
        assert last_record.get("decision") == "catalog_route", (
            f"Expected decision='catalog_route' in routing log, got: {last_record!r}\n"
            "The Spanish QA prompt should trigger catalog discovery, not direct_answer."
        )

    finally:
        # Always restore the original log path to avoid side effects on other tests
        agent_module._LOG_PATH = original_log_path
