"""
Config — centralized environment variable reads for the AI Agents Crew platform.

All env var reads happen here and only here. Config is a frozen dataclass — immutable after
construction. Callers receive a Config instance via Config.from_env() at startup (in main.py)
and inject it into CoordinatingAgent.__init__ — never read env vars directly in other modules.

Design constraints:
- GEMINI_API_KEY is required — from_env() raises KeyError if absent (fail-fast at startup)
- CONFIDENCE_THRESHOLD defaults to 0.72 — recalibrate without code change via env var
- MODEL_VERSION defaults to 'gemini-2.5-flash-001' — pinned per ADK 1.33.0 requirements
- GITHUB_TOKEN is optional — raises catalog fetch rate limit from 60 to 5000 req/hr

Anti-patterns avoided:
- Never hardcode threshold or model version in other modules — always read from Config
- Never call Config.from_env() inside CoordinatingAgent (breaks testability via injection)
"""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Frozen dataclass holding all runtime configuration for the platform.

    Fields:
        gemini_api_key: Required. Gemini API key for LLM access.
        github_token: Optional. GitHub PAT for authenticated catalog fetches (5000 req/hr).
        confidence_threshold: Routing gate — prompts below this threshold trigger catalog lookup.
        model_version: Gemini model version string passed to ADK LlmAgent.
        skills_cache_dir: Local directory for the git-cloned skills catalog. Default: .skills-cache
        skills_cache_ttl: Seconds before a git pull refresh is attempted. Default: 300
    """

    gemini_api_key: str
    github_token: str | None
    confidence_threshold: float
    model_version: str
    skills_cache_dir: Path
    skills_cache_ttl: int

    @classmethod
    def from_env(cls) -> "Config":
        """Construct Config by reading all required and optional environment variables.

        Raises:
            KeyError: If GEMINI_API_KEY is not set in the environment.
        """
        return cls(
            gemini_api_key=os.environ["GEMINI_API_KEY"],
            github_token=os.environ.get("GITHUB_TOKEN"),
            confidence_threshold=float(
                os.environ.get("CONFIDENCE_THRESHOLD", "0.72")
            ),
            model_version=os.environ.get(
                "MODEL_VERSION", "gemini-2.5-flash-001"
            ),
            skills_cache_dir=Path(
                os.environ.get("SKILLS_CACHE_DIR", ".skills-cache")
            ),
            skills_cache_ttl=int(
                os.environ.get("SKILLS_CACHE_TTL", "300")
            ),
        )
