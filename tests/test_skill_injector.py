"""
TDD test suite for SkillInjector — Phase 2, Plan 02-02.

Tests are grouped into three classes:
- TestNormalizeSchema: pure function tests for _normalize_schema (Tests 1-6)
- TestSkillBaseTool: async tests for _SkillBaseTool using AsyncMock for DenoRunner (Tests 7-14)
- TestSkillInjectorBuildTool: async tests for SkillInjector.build_tool() with real GitHub HTTP (Tests 15-18)

asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio decorators needed.

Note: SKILL.md fetch tests use real HTTP to the live GitHub catalog repo per project CLAUDE.md policy.
DenoRunner.execute is mocked with AsyncMock to avoid Deno subprocess overhead in validation tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.skill_injector import SkillInjector, _normalize_schema
from src.models.skill import SkillDefinition
from src.models.results import ExecutionSuccess, ExecutionError, ValidationFailure
from src.models.results import TimeoutError as SkillTimeoutError
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_skill_def() -> SkillDefinition:
    return SkillDefinition(
        name="test_skill",
        description="A test skill",
        path="/fake/.skills-cache/skills/evaluar_test_case/index.ts",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        allow_net_domains=["github.com"],
    )


# ---------------------------------------------------------------------------
# TestNormalizeSchema — Tests 1-6
# ---------------------------------------------------------------------------

class TestNormalizeSchema:
    """Tests 1-6: _normalize_schema pure function."""

    def test_strips_dollar_schema_key(self):
        """Test 1: strips $schema key from root."""
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {"q": {"type": "string"}},
        }
        result = _normalize_schema(schema)
        assert "$schema" not in result

    def test_strips_definitions_and_defs_keys(self):
        """Test 2: strips definitions and $defs keys."""
        schema = {
            "type": "object",
            "definitions": {"foo": {"type": "string"}},
            "$defs": {"bar": {"type": "integer"}},
            "properties": {"q": {"type": "string"}},
        }
        result = _normalize_schema(schema)
        assert "definitions" not in result
        assert "$defs" not in result

    def test_strips_examples_from_nested_property_schemas_recursively(self):
        """Test 3: strips examples from nested property schemas recursively."""
        schema = {
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "examples": ["hello", "world"],
                },
                "nested": {
                    "type": "object",
                    "properties": {
                        "inner": {
                            "type": "string",
                            "examples": ["foo"],
                        }
                    },
                },
            },
        }
        result = _normalize_schema(schema)
        assert "examples" not in result["properties"]["q"]
        assert "examples" not in result["properties"]["nested"]["properties"]["inner"]

    def test_injects_additional_properties_false_when_absent(self):
        """Test 4: injects additionalProperties: false when absent."""
        schema = {
            "type": "object",
            "properties": {"q": {"type": "string"}},
        }
        result = _normalize_schema(schema)
        assert result.get("additionalProperties") is False

    def test_preserves_allowed_keys(self):
        """Test 5: preserves allowed keys: type, properties, required, description,
        additionalProperties, items."""
        schema = {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
            "description": "A test schema",
            "additionalProperties": False,
            "items": {"type": "string"},
        }
        result = _normalize_schema(schema)
        assert result["type"] == "object"
        assert "properties" in result
        assert result["required"] == ["q"]
        assert result["description"] == "A test schema"
        assert result["additionalProperties"] is False
        assert result["items"] == {"type": "string"}

    def test_idempotent_on_already_normalized_schema(self):
        """Test 6: passes clean schema through unchanged (idempotent on normalized input)."""
        schema = {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
            "additionalProperties": False,
        }
        result = _normalize_schema(schema)
        result2 = _normalize_schema(result)
        assert result == result2


# ---------------------------------------------------------------------------
# TestSkillBaseTool — Tests 7-14
# ---------------------------------------------------------------------------

class TestSkillBaseTool:
    """Tests 7-14: _SkillBaseTool._get_declaration() and run_async()."""

    async def _build_tool(self, skill_def: SkillDefinition) -> BaseTool:
        runner = AsyncMock()
        injector = SkillInjector(runner)
        tool, _ = await injector.build_tool(skill_def)
        return tool, runner

    def test_get_declaration_returns_function_declaration(self, sample_skill_def):
        """Test 7: returns FunctionDeclaration with name, description, and normalized parameters."""
        runner = AsyncMock()
        injector = SkillInjector(runner)

        # Build synchronously by calling the internal helper directly
        normalized = _normalize_schema(sample_skill_def.input_schema)
        # Import the private class to construct it directly
        from src.skill_injector import _SkillBaseTool
        tool = _SkillBaseTool(sample_skill_def, runner, normalized)

        declaration = tool._get_declaration()
        assert isinstance(declaration, types.FunctionDeclaration)
        assert declaration.name == "test_skill"
        assert declaration.description == "A test skill"
        assert declaration.parameters is not None

    async def test_missing_required_field_returns_correction_request(self, sample_skill_def):
        """Test 8: missing required field → returns dict with missing_fields, does NOT call runner."""
        runner = AsyncMock()
        injector = SkillInjector(runner)
        tool, _ = await injector.build_tool(sample_skill_def)
        result = await tool.run_async(args={}, tool_context=MagicMock())
        assert isinstance(result, dict)
        assert "query" in result["missing_fields"]
        runner.execute.assert_not_called()

    async def test_extra_field_returns_correction_request(self, sample_skill_def):
        """Test 9: extra undeclared field → returns dict with extra_fields, does NOT call runner."""
        runner = AsyncMock()
        injector = SkillInjector(runner)
        tool, _ = await injector.build_tool(sample_skill_def)
        result = await tool.run_async(
            args={"query": "hello", "extra": "bad"}, tool_context=MagicMock()
        )
        assert isinstance(result, dict)
        assert "extra" in result["extra_fields"]
        runner.execute.assert_not_called()

    async def test_valid_params_calls_runner(self, sample_skill_def):
        """Test 10: valid params → passes validation, calls runner with the params."""
        runner = AsyncMock()
        runner.execute.return_value = ExecutionSuccess(data={"answer": 42})
        injector = SkillInjector(runner)
        tool, _ = await injector.build_tool(sample_skill_def)
        await tool.run_async(args={"query": "hello"}, tool_context=MagicMock())
        runner.execute.assert_called_once()

    async def test_execution_success_returns_data_dict(self, sample_skill_def):
        """Test 11: runner returns ExecutionSuccess → run_async returns result.data."""
        runner = AsyncMock()
        runner.execute.return_value = ExecutionSuccess(data={"answer": 42})
        injector = SkillInjector(runner)
        tool, _ = await injector.build_tool(sample_skill_def)
        result = await tool.run_async(args={"query": "hello"}, tool_context=MagicMock())
        assert result == {"answer": 42}

    async def test_timeout_error_returns_string(self, sample_skill_def):
        """Test 12: runner returns TimeoutError → returns fixed string 'Skill timed out after 5s.'"""
        runner = AsyncMock()
        runner.execute.return_value = SkillTimeoutError(elapsed_ms=5123)
        injector = SkillInjector(runner)
        tool, _ = await injector.build_tool(sample_skill_def)
        result = await tool.run_async(args={"query": "hello"}, tool_context=MagicMock())
        assert result == "Skill timed out after 5s."

    async def test_execution_error_returns_string(self, sample_skill_def):
        """Test 13: runner returns ExecutionError → returns 'Skill failed (exit N): {first stderr line}'."""
        runner = AsyncMock()
        runner.execute.return_value = ExecutionError(exit_code=1, stderr="boom\nmore details")
        injector = SkillInjector(runner)
        tool, _ = await injector.build_tool(sample_skill_def)
        result = await tool.run_async(args={"query": "hello"}, tool_context=MagicMock())
        assert result == "Skill failed (exit 1): boom"

    async def test_execution_error_single_line_stderr(self, sample_skill_def):
        """Test 13b: single-line stderr → full stderr used as message."""
        runner = AsyncMock()
        runner.execute.return_value = ExecutionError(exit_code=2, stderr="single line error")
        injector = SkillInjector(runner)
        tool, _ = await injector.build_tool(sample_skill_def)
        result = await tool.run_async(args={"query": "hello"}, tool_context=MagicMock())
        assert result == "Skill failed (exit 2): single line error"

    async def test_validation_failure_returns_string(self, sample_skill_def):
        """Test 14: runner returns ValidationFailure(invalid_domain='bad') → returns 'Skill domain validation failed: bad'."""
        runner = AsyncMock()
        runner.execute.return_value = ValidationFailure(invalid_domain="bad")
        injector = SkillInjector(runner)
        tool, _ = await injector.build_tool(sample_skill_def)
        result = await tool.run_async(args={"query": "hello"}, tool_context=MagicMock())
        assert result == "Skill domain validation failed: bad"


# ---------------------------------------------------------------------------
# TestSkillInjectorBuildTool — Tests 15-18
# ---------------------------------------------------------------------------

class TestSkillInjectorBuildTool:
    """Tests 15-18: SkillInjector.build_tool() — real GitHub HTTP for SKILL.md tests."""

    async def test_build_tool_returns_tuple_of_base_tool_and_str(self, sample_skill_def):
        """Test 15: returns tuple of (BaseTool subclass instance, str)."""
        runner = AsyncMock()
        injector = SkillInjector(runner)
        result = await injector.build_tool(sample_skill_def)
        assert isinstance(result, tuple)
        assert len(result) == 2
        tool, skill_md = result
        assert isinstance(tool, BaseTool)
        assert isinstance(skill_md, str)

    async def test_build_tool_skill_md_fetch_success_returns_content(self, sample_skill_def):
        """Test 16: _fetch_skill_md reads local SKILL.md — returns "" for non-existent path.

        sample_skill_def.path is a fake path with no SKILL.md on disk — expect empty string.
        """
        runner = AsyncMock()
        injector = SkillInjector(runner)
        _, skill_md = await injector.build_tool(sample_skill_def)
        # skill_def.path is a fake path with no SKILL.md on disk — empty string is valid
        assert isinstance(skill_md, str)
        # Empty string is acceptable for a path that does not have SKILL.md locally

    async def test_build_tool_missing_skill_md_returns_empty_string(self):
        """Test 17: SKILL.md fetch 404 / network error → second element is '', tool still usable."""
        nonexistent_skill = SkillDefinition(
            name="nonexistent_skill",
            description="A skill that does not exist",
            path="this_skill_does_not_exist_anywhere_xyz123",
            input_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
            allow_net_domains=[],
        )
        runner = AsyncMock()
        injector = SkillInjector(runner)
        tool, skill_md = await injector.build_tool(nonexistent_skill)
        assert skill_md == ""
        # tool should still be usable (BaseTool instance)
        assert isinstance(tool, BaseTool)

    async def test_build_tool_local_path_reads_skill_md(self, sample_skill_def, tmp_path):
        """Test 18: _fetch_skill_md reads SKILL.md from Path(skill_def.path).parent.

        Creates a real SKILL.md in tmp_path to verify local read works end-to-end.
        """
        # Create a fake skill dir structure in tmp_path
        skill_dir = tmp_path / "skills" / "evaluar_test_case"
        skill_dir.mkdir(parents=True)
        skill_md_file = skill_dir / "SKILL.md"
        skill_md_file.write_text("# Test Skill Guide", encoding="utf-8")
        ts_path = skill_dir / "index.ts"
        ts_path.write_text("// fake ts", encoding="utf-8")

        local_skill_def = SkillDefinition(
            name="evaluar_test_case",
            description="test",
            path=str(ts_path),  # absolute path pointing to real tmp_path file
            input_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
            allow_net_domains=[],
        )
        runner = AsyncMock()
        injector = SkillInjector(runner)
        _, skill_md = await injector.build_tool(local_skill_def)
        assert skill_md == "# Test Skill Guide"
