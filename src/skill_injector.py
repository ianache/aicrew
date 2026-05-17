"""
SkillInjector — ADK BaseTool Construction with JSON Schema Validation.

Design constraints:
- Uses BaseTool subclass (_SkillBaseTool) with explicit _get_declaration() — NOT FunctionTool.
  FunctionTool in ADK 1.33.0 drops all args for **kwargs closures (verified in research).
- Schema normalization strips ADK-incompatible keys before types.Schema.model_validate().
  Raw schema from skill.json may contain $schema, definitions, $defs, examples which
  types.Schema rejects (extra='forbid' in Pydantic model).
- Missing/extra field validation computed directly from schema, NOT from jsonschema e.path.
  jsonschema 'required' validator errors do NOT reliably populate e.path (pitfall verified).
- run_async always returns str or dict — never raises. Callers (ADK) receive serializable output.
- build_tool() is async — SKILL.md is now read from the local git clone (no HTTP).
- _fetch_skill_md reads SKILL.md via pathlib.Path(path).parent / "SKILL.md" (Phase 6 contract).
- run_async passes --allow-read={cache_root} in extra_flags to DenoRunner for local .ts access.

Anti-patterns avoided:
- Never use FunctionTool (drops **kwargs args in ADK 1.33.0)
- Never pass raw input_schema to types.Schema.model_validate (must normalize first)
- Never call asyncio.run() inside build_tool() (already async)
- Never raise exceptions from run_async (return strings or dicts)
- Never use e.path for required field extraction (use schema-based computation)
"""
from pathlib import Path

from jsonschema import Draft7Validator
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from src.execution.deno_runner import DenoRunner
from src.models.results import ExecutionSuccess, ExecutionError, ValidationFailure
from src.models.results import TimeoutError as SkillTimeoutError
from src.models.skill import SkillDefinition, ValidationCorrectionRequest


# ---------------------------------------------------------------------------
# Allowed keys for types.Schema.model_validate (ADK 1.33.0, extra='forbid')
# ---------------------------------------------------------------------------

_ALLOWED_SCHEMA_KEYS: frozenset[str] = frozenset({
    "type",
    "properties",
    "required",
    "description",
    "additionalProperties",
    "items",
    "enum",
    "format",
    "default",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
    "anyOf",
    "title",
})

# Root-level keys to strip unconditionally (never valid in ADK schema)
_ROOT_STRIP_KEYS: frozenset[str] = frozenset({
    "$schema",
    "definitions",
    "$defs",
    "examples",
})


# ---------------------------------------------------------------------------
# _normalize_schema
# ---------------------------------------------------------------------------

def _normalize_schema(schema: dict) -> dict:
    """Recursively normalize a JSON Schema dict for ADK types.Schema compatibility.

    Strips: $schema, definitions, $defs, examples (at any level).
    Filters: removes any keys not in _ALLOWED_SCHEMA_KEYS union _ROOT_STRIP_KEYS handling.
    Injects: additionalProperties=False if not already set.
    Recurses: into 'properties' values and 'items' if present.

    Returns a new dict — does not mutate the input.
    """
    result: dict = {}

    for key, value in schema.items():
        # Strip disallowed root-level metadata keys at every level
        if key in _ROOT_STRIP_KEYS:
            continue
        # Keep only keys that ADK's types.Schema accepts
        if key not in _ALLOWED_SCHEMA_KEYS:
            continue

        if key == "properties" and isinstance(value, dict):
            # Recurse into each property sub-schema
            result["properties"] = {
                prop_name: _normalize_schema(prop_schema)
                for prop_name, prop_schema in value.items()
                if isinstance(prop_schema, dict)
            }
        elif key == "items" and isinstance(value, dict):
            # Recurse into array items schema
            result["items"] = _normalize_schema(value)
        elif key == "anyOf" and isinstance(value, list):
            # Recurse into anyOf sub-schemas
            result["anyOf"] = [
                _normalize_schema(s) if isinstance(s, dict) else s
                for s in value
            ]
        else:
            result[key] = value

    # Inject additionalProperties: false if not already set — only for object schemas
    # (type: object or schemas with properties). Non-object schemas (string, integer, etc.)
    # must NOT receive additionalProperties: false — ADK types.Schema rejects it there.
    is_object_schema = (
        result.get("type") == "object"
        or "properties" in result
    )
    if is_object_schema and "additionalProperties" not in result:
        result["additionalProperties"] = False

    return result


# ---------------------------------------------------------------------------
# _fetch_skill_md
# ---------------------------------------------------------------------------

async def _fetch_skill_md(path: str, timeout: float = 5.0) -> str:
    """Read SKILL.md from the local clone.

    path is an absolute local .ts path (Phase 6 contract).
    Derives SKILL.md: Path(path).parent / "SKILL.md".
    timeout parameter kept for signature compat — no longer used (no network call).
    Returns "" on any failure (file not found, permission error) — soft-fail.
    """
    try:
        skill_md_path = Path(path).parent / "SKILL.md"
        if skill_md_path.exists():
            return skill_md_path.read_text(encoding="utf-8")
        return ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# _SkillBaseTool — private ADK BaseTool subclass
# ---------------------------------------------------------------------------

class _SkillBaseTool(BaseTool):
    """Private ADK BaseTool subclass for a single SkillDefinition.

    Never imported directly by callers — access only via SkillInjector.build_tool().

    _get_declaration() exposes the normalized JSON Schema to the LLM as a FunctionDeclaration.
    run_async() validates args against the schema before dispatching to DenoRunner.execute().
    """

    def __init__(
        self,
        skill_def: SkillDefinition,
        runner: DenoRunner,
        normalized_schema: dict,
    ) -> None:
        super().__init__(name=skill_def.name, description=skill_def.description)
        self._skill_def = skill_def
        self._runner = runner
        self._normalized_schema = normalized_schema

    @staticmethod
    def _strip_additional_properties(schema: dict) -> dict:
        """Recursively remove additionalProperties — Gemini API rejects it in function schemas."""
        result = {k: v for k, v in schema.items() if k != "additionalProperties"}
        if "properties" in result and isinstance(result["properties"], dict):
            result["properties"] = {
                k: _SkillBaseTool._strip_additional_properties(v)
                for k, v in result["properties"].items()
                if isinstance(v, dict)
            }
        if "items" in result and isinstance(result["items"], dict):
            result["items"] = _SkillBaseTool._strip_additional_properties(result["items"])
        return result

    def _get_declaration(self) -> types.FunctionDeclaration:
        """Return the ADK FunctionDeclaration with the normalized schema as parameters.

        additionalProperties is stripped before passing to Gemini — the API rejects it.
        The full schema (with additionalProperties) is kept in self._normalized_schema for
        jsonschema validation in run_async().
        """
        gemini_schema = self._strip_additional_properties(self._normalized_schema)
        parameters = types.Schema.model_validate(gemini_schema)
        return types.FunctionDeclaration(
            name=self._skill_def.name,
            description=self._skill_def.description,
            parameters=parameters,
        )

    async def run_async(self, *, args: dict, tool_context: ToolContext) -> str | dict:
        """Validate args against the JSON Schema, then execute via DenoRunner.

        Step 1: Compute missing_fields and extra_fields directly from schema.
        Step 2: If validation errors exist, return ValidationCorrectionRequest.model_dump().
        Step 3: Execute via DenoRunner.execute().
        Step 4: Dispatch on result type — return data dict or error string.

        Never raises — all outcomes returned as str or dict.
        """
        schema = self._normalized_schema

        # Step 1: Schema-based validation (direct computation — not jsonschema e.path)
        missing_fields = [
            f for f in schema.get("required", []) if f not in args
        ]
        extra_fields = [
            k for k in args if k not in schema.get("properties", {})
        ]

        # Step 2: Return correction request if any validation errors
        if missing_fields or extra_fields:
            missing_str = ", ".join(missing_fields) if missing_fields else "none"
            extra_str = ", ".join(extra_fields) if extra_fields else "none"
            message = (
                f"Skill call validation failed. "
                f"Missing required fields: {missing_str}. "
                f"Extra/undeclared fields: {extra_str}."
            )
            return ValidationCorrectionRequest(
                missing_fields=missing_fields,
                extra_fields=extra_fields,
                message=message,
            ).model_dump()

        # Step 3: Execute via DenoRunner
        # Derive cache root from absolute .ts path: parents[2] = .skills-cache/
        # For bare paths (tests), Path.parents[2] may not exist — guard with try/except
        try:
            cache_root = Path(self._skill_def.path).parents[2]
            allow_read_flag = f"--allow-read={cache_root.as_posix()}"
            extra_flags = [allow_read_flag]
        except IndexError:
            extra_flags = []

        result = await self._runner.execute(
            self._skill_def.path,
            args,
            self._skill_def.allow_net_domains,
            extra_flags=extra_flags,
        )

        # Step 4: Dispatch on result type
        if isinstance(result, ExecutionSuccess):
            return result.data
        elif isinstance(result, SkillTimeoutError):
            return "Skill timed out after 5s."
        elif isinstance(result, ExecutionError):
            first_line = result.stderr.splitlines()[0] if result.stderr.strip() else result.stderr
            return f"Skill failed (exit {result.exit_code}): {first_line}"
        elif isinstance(result, ValidationFailure):
            return f"Skill domain validation failed: {result.invalid_domain}"
        else:
            return f"Skill returned unexpected result type: {type(result).__name__}"


# ---------------------------------------------------------------------------
# SkillInjector — public API
# ---------------------------------------------------------------------------

class SkillInjector:
    """Converts a SkillDefinition into a live ADK BaseTool subclass.

    Usage:
        injector = SkillInjector(runner)
        tool, skill_md = await injector.build_tool(skill_def)
        # tool: _SkillBaseTool instance (BaseTool subclass) — inject into ADK agent
        # skill_md: SKILL.md content string — inject into agent system instruction

    build_tool() is async — must be awaited. It fetches SKILL.md from GitHub concurrently
    with schema normalization. The fetched SKILL.md is returned as a string alongside the
    tool so callers can append it to the agent's system instruction for richer context.
    """

    def __init__(self, runner: DenoRunner) -> None:
        self._runner = runner

    async def build_tool(self, skill_def: SkillDefinition) -> tuple[BaseTool, str]:
        """Build an ADK BaseTool from a SkillDefinition and fetch its SKILL.md guide.

        Args:
            skill_def: The SkillDefinition from CatalogExplorer.find().

        Returns:
            A (tool, skill_md) tuple where:
            - tool is a _SkillBaseTool instance (BaseTool subclass) ready for ADK injection
            - skill_md is the SKILL.md string content (may be "" if fetch fails — soft fail)
        """
        # Normalize schema first (must happen before _SkillBaseTool construction)
        normalized_schema = _normalize_schema(skill_def.input_schema)

        # Fetch SKILL.md from GitHub catalog (soft-fail — "" on any error)
        skill_md = await _fetch_skill_md(skill_def.path)

        # Construct the BaseTool subclass
        tool = _SkillBaseTool(skill_def, self._runner, normalized_schema)

        return tool, skill_md
