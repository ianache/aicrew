"""
Skill domain models — shared contract between CatalogExplorer (Phase 4) and SkillInjector (Phase 2).

SkillDefinition is the shared contract between CatalogExplorer (Phase 4) and SkillInjector (Phase 2).
ValidationCorrectionRequest is returned by SkillInjector._SkillBaseTool.run_async() when JSON Schema
validation fails — returned as .model_dump() dict, not as the Pydantic object, for consistent ADK
serialization.

Zero imports from ADK, Deno, or execution modules.
"""
from pydantic import BaseModel


class SkillDefinition(BaseModel):
    """Describes a single skill loaded from the GitHub catalog.

    path is the bare skill name (e.g. 'evaluar_test_case'), NOT prefixed with 'skills/'.
    The 'skills/' prefix is added only at URL construction time in skill_injector.py.

    input_schema is the raw JSON Schema object from skill.json. It is NOT normalized here —
    normalization (e.g. injecting additionalProperties:false) happens in SkillInjector._normalize_schema().

    allow_net_domains is passed directly to DenoRunner.execute() as the allow_net_domains argument.
    An empty list means no network access is granted to the skill subprocess.
    """

    name: str
    """Matches the 'name' key in skill.json."""

    description: str
    """Plain text description of what the skill does."""

    path: str
    """Bare skill name, e.g. 'evaluar_test_case'. No 'skills/' prefix."""

    input_schema: dict
    """Raw JSON Schema object from skill.json. Not normalized here."""

    allow_net_domains: list[str]
    """Validated hostnames for --allow-net flag. Empty list = no network access."""


class ValidationCorrectionRequest(BaseModel):
    """Returned by SkillInjector._SkillBaseTool.run_async() when JSON Schema validation fails.

    Callers receive this as .model_dump() dict (not the Pydantic object) for consistent ADK
    serialization. The message field provides a human-readable summary the LLM can relay to
    the user explaining what went wrong and what is needed.
    """

    missing_fields: list[str]
    """Fields in input_schema.required that are absent from the LLM payload."""

    extra_fields: list[str]
    """Fields in the LLM payload not present in input_schema.properties."""

    message: str
    """Human-readable summary for the LLM to report to the user."""
