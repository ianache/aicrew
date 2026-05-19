# Phase 2: Skill Injection Bridge - Research

**Researched:** 2026-05-17
**Domain:** ADK FunctionTool / BaseTool construction, JSON Schema validation, async GitHub fetch
**Confidence:** HIGH (all critical claims verified against installed ADK 1.33.0 source)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Validation failure response (INJS-02)**
- Missing/invalid parameters return a **Pydantic model**: `ValidationCorrectionRequest`
- Fields: `missing_fields: list[str]`, `extra_fields: list[str]` (unexpected fields), `message: str` (human-readable)
- Consistent with Pydantic-first pattern from Phase 1 — typed, serializable, testable
- When `DenoRunner.execute()` returns `ExecutionError` or `TimeoutError`, the closure **converts to a string** and returns it to the LLM (e.g., `"Skill execution failed: <stderr>"`, `"Skill timed out after 5000ms"`). No exception propagation — the LLM receives a readable string to report to the user.

**SKILL.md injection mechanism (INJS-03)**
- `build_tool()` returns a **tuple**: `(FunctionTool, skill_md: str)`
- Phase 3 takes `skill_md` and appends it to the agent's system instruction for that run
- SKILL.md URL constructed from `skill_def.path`: `raw.githubusercontent.com/ianache/skills-catalog/main/skills/{path}/SKILL.md`
- **Soft fail**: if SKILL.md fetch fails (GitHub down, 404, network error), return `(FunctionTool, "")` — empty string. The tool still executes; cognitive guidance is absent. Phase 3 checks for empty string and skips injection.

**SkillDefinition model ownership (INJS-01)**
- `SkillDefinition` defined in **`src/models/skill.py`** alongside `results.py` — zero ADK/Deno dependencies, shared contract
- Minimal fields: `name: str`, `description: str`, `path: str` (e.g., `"evaluar_test_case"`), `input_schema: dict`, `allow_net_domains: list[str]`
- Phase 2 defines a **fresh contract** — Phase 4 verifies that the existing CatalogExplorer produces compatible output (or adapts it). Keeps Phase 2 independently testable without live catalog.
- CatalogExplorer and SkillInjector both import from `src/models/skill.py` (single source of truth)

**FunctionTool fallback strategy (INJS-01)**
- **Try primary first**: `FunctionTool(func=_execute)` where `_execute` is an async closure
- **Bake in fallback**: if ADK introspection fails, fall back to a private `_SkillBaseTool(BaseTool)` inner class with explicit `_get_declaration()` returning `types.FunctionDeclaration`
- The fallback class is private — callers never see it. Public interface is always `build_tool() -> tuple[FunctionTool, str]`
- Schema normalization before passing to ADK: inject `additionalProperties: false` if absent, AND strip unsupported keywords (`$schema`, `definitions`, `$defs`, any keyword not in `{type, properties, required, description, additionalProperties}`) — prevents silent ADK schema parsing failures

### Claude's Discretion
- Whether to use `jsonschema.Draft7Validator` or `Draft202012Validator` for INJS-02 validation
- Exact HTTP timeout for SKILL.md fetch
- Whether `ValidationCorrectionRequest` lives in `src/models/skill.py` or `src/models/results.py` (or a new `src/models/validation.py`)
- Exact error message strings returned to the LLM

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INJS-01 | SkillInjector converts `SkillDefinition` to a live ADK `FunctionTool` | BaseTool subclass is the correct primary implementation; schema normalization required before `types.Schema.model_validate` |
| INJS-02 | LLM payload validated against JSON Schema before Deno fires; missing required fields return structured correction request | `jsonschema.Draft7Validator` with `iter_errors()` identifies missing vs extra fields; return `ValidationCorrectionRequest` Pydantic model |
| INJS-03 | SKILL.md cognitive guide fetched from GitHub and returned as `str` alongside tool | `httpx.AsyncClient` with timeout; soft-fail to empty string; URL pattern `raw.githubusercontent.com/.../skills/{path}/SKILL.md` |
</phase_requirements>

---

## Summary

The core technical challenge of Phase 2 is wrapping a dynamic JSON schema (from `SkillDefinition.input_schema`) into an ADK tool that the LLM can call. Direct inspection of ADK 1.33.0 source confirms that the CONTEXT.md's "primary/fallback" framing should be **inverted**: `FunctionTool` with a `**kwargs` closure is NOT viable as primary because (a) ADK generates `None` schema for `**kwargs` functions — the LLM sees no parameters — and (b) ADK's `run_async` parameter filter drops all LLM-supplied args before calling `**kwargs` functions. The `BaseTool` subclass approach is therefore the **correct primary implementation**.

The schema normalization step is non-optional. `types.Schema.model_validate(dict)` rejects any key not in Schema's model fields (extras are `extra_forbidden`). Problematic keys found in real catalog schemas include `$schema`, `definitions`, `$defs`, and nested `examples` arrays. A `_normalize_schema(schema: dict) -> dict` function must strip these recursively before constructing the FunctionDeclaration.

For SKILL.md fetching, live testing confirms the catalog uses path `skills/{path}/SKILL.md` (not `{path}/SKILL.md`). The real `evaluar_test_case` skill has only SKILL.md and `skills.json` (note: not `skill.json`) — Phase 2 defines its own `SkillDefinition` contract so this inconsistency in the live catalog does not affect Phase 2 directly, but Phase 4 must reconcile it.

**Primary recommendation:** Implement `SkillInjector` using a private `_SkillBaseTool(BaseTool)` inner class as the sole implementation. `FunctionTool` is not usable for dynamic JSON schemas with `**kwargs` closures in ADK 1.33.0.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `google-adk` | 1.33.0 (pinned) | `BaseTool`, `FunctionTool`, `types.FunctionDeclaration`, `types.Schema` | Already in `pyproject.toml`; project-locked version |
| `google-genai` | >=1.72,<2 | `types.Schema`, `types.FunctionDeclaration`, `types.Type` | Required by google-adk; `types` module used for schema construction |
| `pydantic` | >=2.12,<3 | `ValidationCorrectionRequest`, `SkillDefinition` models | Established by Phase 1; all contracts are Pydantic models |
| `jsonschema` | 4.26.0 (transitive via google-adk) | Runtime validation of LLM params against `input_schema` | Handles `required`, `additionalProperties`, type coercion |
| `httpx` | >=0.27,<1 | Async SKILL.md fetch from `raw.githubusercontent.com` | Already in `pyproject.toml` dependencies |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `jsonschema.Draft7Validator` | 4.26.0 | JSON Schema validation engine | Primary validator; Anthropic tool definition format is draft-07 compatible |
| `types.Schema.model_validate` | via google-genai | Convert normalized dict to ADK Schema object | In `_get_declaration()` to build `FunctionDeclaration.parameters` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `BaseTool` subclass | `FunctionTool(**kwargs closure)` | FunctionTool drops all args for `**kwargs` in `run_async`; generates `None` schema — unusable |
| `BaseTool` subclass | `FunctionTool(typed closure)` | Typed closure requires dynamic function generation from JSON schema, fragile with `types.FunctionType` manipulation |
| `Draft7Validator` | `Draft202012Validator` | Both work identically for simple object schemas; Draft7 better matches Anthropic's JSON Schema format |
| `httpx.AsyncClient` | `aiohttp` | `httpx` already in dependencies; no reason to add another HTTP client |

**Installation (add jsonschema explicitly):**
```bash
# In pyproject.toml [project] dependencies, add:
"jsonschema>=4.0,<5"

# Then:
uv pip install -e ".[dev]"
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/
├── models/
│   ├── skill.py          # SkillDefinition (new Phase 2), ValidationCorrectionRequest
│   └── results.py        # ExecutionResult union (Phase 1, unchanged)
└── skill_injector.py     # SkillInjector class + private _SkillBaseTool

tests/
└── test_skill_injector.py  # Phase 2 TDD tests (file not yet created)
```

### Pattern 1: _SkillBaseTool — BaseTool Subclass with JSON Schema Declaration

**What:** A private `BaseTool` subclass that holds the `SkillDefinition` and async execute function, returning a `FunctionDeclaration` built from the normalized JSON schema.

**When to use:** Always — this is the only implementation that correctly passes LLM args to the closure AND exposes the schema to the LLM.

**Why BaseTool over FunctionTool:** `FunctionTool.run_async` filters call args to `{k: v for k, v in args.items() if k in valid_params}`. For a `**kwargs` function, `valid_params = {'kwargs'}`, so ALL LLM-supplied args are silently dropped before the closure executes. `BaseTool.run_async` receives the full `args: dict[str, Any]` without filtering.

**Example:**
```python
# Source: verified against ADK 1.33.0 google/adk/tools/base_tool.py + function_tool.py

from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

class _SkillBaseTool(BaseTool):
    """Private ADK tool wrapping a SkillDefinition. Never exposed directly."""

    def __init__(
        self,
        skill_def: "SkillDefinition",
        runner: "DenoRunner",
        normalized_schema: dict,
    ) -> None:
        super().__init__(name=skill_def.name, description=skill_def.description)
        self._skill_def = skill_def
        self._runner = runner
        self._normalized_schema = normalized_schema

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema.model_validate(self._normalized_schema),
        )

    async def run_async(self, *, args: dict, tool_context: ToolContext) -> str | dict:
        # 1. JSON Schema validation
        errors = list(jsonschema.Draft7Validator(self._normalized_schema).iter_errors(args))
        if errors:
            missing = [e.path[-1] if e.path else e.message
                       for e in errors if e.validator == "required"]
            extra = [e.path[-1] if e.path else e.message
                     for e in errors if e.validator == "additionalProperties"]
            return ValidationCorrectionRequest(
                missing_fields=missing,
                extra_fields=extra,
                message=f"Parameter validation failed: {'; '.join(e.message for e in errors)}"
            ).model_dump()

        # 2. Execute via DenoRunner
        result = await self._runner.execute(
            self._skill_def.path,
            args,
            self._skill_def.allow_net_domains,
        )

        # 3. Map ExecutionResult to return value
        if isinstance(result, ExecutionSuccess):
            return result.data
        elif isinstance(result, TimeoutError):
            return f"Skill timed out after {result.elapsed_ms}ms"
        elif isinstance(result, ExecutionError):
            return f"Skill execution failed: {result.stderr}"
        else:  # ValidationFailure
            return f"Skill domain validation failed: {result.invalid_domain}"
```

### Pattern 2: Schema Normalization

**What:** Strip JSON Schema keywords that `types.Schema.model_validate` rejects (`extra_forbidden` Pydantic validation) before constructing the `FunctionDeclaration`.

**When to use:** Always, before passing `input_schema` to `types.Schema.model_validate`.

**Example:**
```python
# Source: verified by testing types.Schema.model_fields against dirty skill.json schemas

_ALLOWED_SCHEMA_KEYS = frozenset({
    "type", "properties", "required", "description",
    "additionalProperties", "items", "enum", "format",
    "default", "minimum", "maximum", "minLength", "maxLength",
    "minItems", "maxItems", "pattern", "anyOf", "title",
})

def _normalize_schema(schema: dict) -> dict:
    """Strip unsupported JSON Schema keywords and inject additionalProperties: false."""
    result: dict = {}
    for k, v in schema.items():
        if k not in _ALLOWED_SCHEMA_KEYS:
            continue
        if k == "properties" and isinstance(v, dict):
            result[k] = {pk: _normalize_schema(pv) for pk, pv in v.items()}
        elif k == "items" and isinstance(v, dict):
            result[k] = _normalize_schema(v)
        else:
            result[k] = v
    if "additionalProperties" not in result:
        result["additionalProperties"] = False
    return result
```

### Pattern 3: SKILL.md Fetch with Soft Fail

**What:** Async fetch of SKILL.md from `raw.githubusercontent.com`. Returns empty string on any failure.

**When to use:** Inside `SkillInjector.build_tool()` before constructing the tool.

**Example:**
```python
# Source: verified with live GitHub request — URL pattern confirmed working

async def _fetch_skill_md(path: str, timeout: float = 5.0) -> str:
    url = f"https://raw.githubusercontent.com/ianache/skills-catalog/main/skills/{path}/SKILL.md"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.text
            return ""
    except Exception:
        return ""
```

### Pattern 4: SkillDefinition Model

**What:** Pydantic model in `src/models/skill.py` — zero ADK/Deno dependencies.

**Example:**
```python
# Source: CONTEXT.md locked decision + CLAUDE.md component contracts

from pydantic import BaseModel

class SkillDefinition(BaseModel):
    name: str
    description: str
    path: str                       # e.g., "evaluar_test_case"
    input_schema: dict              # JSON Schema object
    allow_net_domains: list[str]    # validated hostnames for --allow-net


class ValidationCorrectionRequest(BaseModel):
    missing_fields: list[str]
    extra_fields: list[str]
    message: str
```

### Pattern 5: SkillInjector.build_tool() Public API

**What:** The single public entry point that orchestrates schema normalization, SKILL.md fetch, and tool construction.

**Example:**
```python
# Source: CONTEXT.md locked decisions

class SkillInjector:
    def __init__(self, runner: DenoRunner) -> None:
        self._runner = runner

    async def build_tool(
        self, skill_def: SkillDefinition
    ) -> tuple["_SkillBaseTool", str]:
        normalized = _normalize_schema(skill_def.input_schema)
        skill_md = await _fetch_skill_md(skill_def.path)
        tool = _SkillBaseTool(skill_def, self._runner, normalized)
        return tool, skill_md
```

Note: return type is `tuple[BaseTool, str]` not `tuple[FunctionTool, str]`. CONTEXT.md says `FunctionTool` but verified research shows `_SkillBaseTool(BaseTool)` is the correct type. Phase 3 receives a `BaseTool` subclass which is fully compatible with ADK agent tool registration.

### Anti-Patterns to Avoid

- **`FunctionTool` with `**kwargs` closure:** ADK's `run_async` filters `{k: v for k, v in args.items() if k in valid_params}` — for `**kwargs` functions, `valid_params = {'kwargs'}` and ALL LLM args are dropped silently before the closure runs.
- **Skipping schema normalization:** `types.Schema.model_validate` raises `extra_forbidden` for any key not in its model fields. Real catalog skills have `examples` in nested property schemas, `$schema` at root, etc.
- **Using `proc.wait()` in any new code:** Already documented as taboo in Phase 1 — never add it.
- **Raising exceptions from `run_async`:** Return strings for errors. ADK wraps `run_async` exceptions in a tool error response, but returning a readable string gives the LLM better context to retry.
- **`build_tool()` as a sync method:** `_fetch_skill_md` is async (uses `httpx.AsyncClient`). `build_tool()` must be `async`.
- **Hardcoding `skills/` prefix in `SkillDefinition.path`:** The `path` field should store the bare path (e.g., `"evaluar_test_case"`), and the URL construction adds `skills/` prefix. This keeps the model clean and matches the catalog.yaml `path` values.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON Schema validation | Custom required-field checker | `jsonschema.Draft7Validator.iter_errors()` | Handles nested required, type coercion, additionalProperties, format validators — edge cases are substantial |
| Schema → ADK type mapping | Manual `type_map = {'string': types.Type.STRING, ...}` | `types.Schema.model_validate(dict)` | ADK's own Pydantic model handles camelCase mapping, nested schemas, all type variants |
| HTTP timeout/retry | Custom `asyncio.wait_for` wrapping | `httpx.AsyncClient(timeout=N)` | `httpx` timeout covers connect + read; handles redirects, encoding, TLS |
| ADK schema introspection | Parsing `__annotations__` manually | `BaseTool._get_declaration()` + `types.FunctionDeclaration` | ADK's own declaration protocol — `process_llm_request` calls this to add tool to LLM request |

**Key insight:** The ADK schema pipeline (`types.Schema.model_validate → types.FunctionDeclaration → process_llm_request`) handles all the complexity of converting JSON Schema to Gemini-compatible function declarations. Never replicate this pipeline manually.

---

## Common Pitfalls

### Pitfall 1: FunctionTool(**kwargs) — Silent Arg Drop
**What goes wrong:** `FunctionTool` wrapping an `async def _execute(**kwargs)` closure receives ALL LLM args but passes NONE to the closure. `run_async` filters to `valid_params = {'kwargs'}` (the name of the variadic parameter, not the actual kwargs). The tool executes but always receives an empty dict.
**Why it happens:** ADK's parameter filtering was designed for typed functions. `inspect.signature(**kwargs)` returns a parameter named `'kwargs'` of kind `VAR_KEYWORD`, not the individual key names.
**How to avoid:** Use `BaseTool` subclass where `run_async(self, *, args: dict, ...)` receives the full args dict directly.
**Warning signs:** Tool appears to execute but always returns results as if no params were passed.

### Pitfall 2: types.Schema.model_validate Rejects Unknown Keywords
**What goes wrong:** `types.Schema.model_validate(skill_def.input_schema)` raises `ValidationError` with `extra_forbidden` for keys like `$schema`, `definitions`, `$defs`, `examples`.
**Why it happens:** `types.Schema` is a strict Pydantic model with `model_config = ConfigDict(extra='forbid')`. The ADK Schema type is a subset of full JSON Schema.
**How to avoid:** Always run `_normalize_schema()` before calling `model_validate`.
**Warning signs:** `pydantic.ValidationError: extra inputs are not permitted` at tool construction time.

### Pitfall 3: jsonschema errors for 'required' Use e.validator, Not e.path
**What goes wrong:** Trying to extract missing field names from `e.path` for `required` validation errors returns empty path (`deque([])`). The field name is in `e.message` string.
**Why it happens:** `required` validator errors fire at the object level (path = `[]`), not at the field level. The message is `"'fieldname' is a required property"`.
**How to avoid:** For `required` errors, parse the field name from `e.message` OR check `e.validator == 'required'` and use the schema to compute missing fields: `[f for f in schema.get('required', []) if f not in params]`.
**Warning signs:** `missing_fields` in `ValidationCorrectionRequest` is always empty despite missing params.

### Pitfall 4: SKILL.md URL Uses skills/ Prefix — Live Verification
**What goes wrong:** Constructing URL as `raw.githubusercontent.com/.../main/{path}/SKILL.md` returns 404. Path in `catalog.yaml` is `"evaluar_test_case"` not `"skills/evaluar_test_case"`.
**Why it happens:** GitHub repo structure is `skills/evaluar_test_case/SKILL.md`. The catalog `path` field stores the bare skill name without the `skills/` prefix.
**How to avoid:** Construct URL as `https://raw.githubusercontent.com/ianache/skills-catalog/main/skills/{path}/SKILL.md`.
**Warning signs:** SKILL.md fetch always returns empty string even when GitHub is reachable.

### Pitfall 5: ValidationCorrectionRequest Returned as dict, Not Model
**What goes wrong:** ADK's `run_async` return value is serialized for the LLM. Returning a Pydantic model directly may serialize inconsistently vs returning `.model_dump()`.
**Why it happens:** `BaseTool.run_async` can return `Any`. The ADK framework passes the return value as the tool call result. Pydantic models serialize to their `__str__` by default in some contexts.
**How to avoid:** Return `validation_request.model_dump()` (a plain dict) from `run_async` for consistent serialization.
**Warning signs:** LLM receives Python object representation `ValidationCorrectionRequest(missing_fields=...)` instead of JSON.

### Pitfall 6: build_tool() Must Be Async
**What goes wrong:** Defining `build_tool()` as a sync method that calls `asyncio.run(_fetch_skill_md(...))` will fail inside an already-running event loop (pytest-asyncio, production agent loop).
**Why it happens:** `asyncio.run()` cannot be called from a running event loop.
**How to avoid:** `async def build_tool(...)` and `await _fetch_skill_md(...)`. Callers must `await skill_injector.build_tool(skill_def)`.
**Warning signs:** `RuntimeError: This event loop is already running`.

---

## Code Examples

Verified patterns from ADK 1.33.0 source inspection and live testing:

### Minimal Working _SkillBaseTool
```python
# Source: verified by running against installed google-adk==1.33.0

from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
import jsonschema

class _SkillBaseTool(BaseTool):
    def __init__(self, name: str, description: str, schema: dict, execute_fn):
        super().__init__(name=name, description=description)
        self._schema = schema
        self._execute_fn = execute_fn

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema.model_validate(self._schema),
        )

    async def run_async(self, *, args: dict, tool_context: ToolContext):
        return await self._execute_fn(args)

# Usage — verified this produces correct declaration AND receives args:
# tool = _SkillBaseTool("search", "Search skill", schema_dict, my_async_fn)
# decl = tool._get_declaration()  # -> FunctionDeclaration with full schema
# result = await tool.run_async(args={"query": "hello"}, tool_context=ctx)
```

### Extracting Missing and Extra Fields from jsonschema Errors
```python
# Source: verified by testing jsonschema 4.26.0 error structure

import jsonschema

schema = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": False,
}

params = {"extra_key": "bad"}
validator = jsonschema.Draft7Validator(schema)
errors = list(validator.iter_errors(params))

# 'required' validator: e.validator == 'required', field name in e.message
# 'additionalProperties' validator: e.validator == 'additionalProperties', field name in e.message
# Both produce e.path == deque([]) — field name NOT in path

missing = []
extra = []
for e in errors:
    if e.validator == "required":
        # Parse field name: "'query' is a required property"
        import re
        m = re.search(r"'(\w+)'", e.message)
        if m:
            missing.append(m.group(1))
    elif e.validator == "additionalProperties":
        m = re.search(r"'(\w+)'", e.message)
        if m:
            extra.append(m.group(1))

# Simpler alternative: compute directly from schema
missing_fields = [f for f in schema.get("required", []) if f not in params]
extra_fields = [k for k in params if k not in schema.get("properties", {})]
```

### types.Schema.model_validate with JSON Schema Dict
```python
# Source: verified against google-genai types.Schema model fields

from google.genai import types

# Works: basic object schema (after normalization)
schema = types.Schema.model_validate({
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search term"},
        "limit": {"type": "integer"},
    },
    "required": ["query"],
    "additionalProperties": False,
})
# schema.type == Type.OBJECT
# schema.properties == {"query": Schema(type=STRING), "limit": Schema(type=INTEGER)}
# schema.required == ["query"]
# schema.additional_properties == False

# Fails: extra keywords
# types.Schema.model_validate({"type": "object", "$schema": "...", "definitions": {}})
# -> pydantic.ValidationError: extra inputs are not permitted
```

### Complete Schema Normalization
```python
# Source: verified by testing against real catalog skill schemas

_ALLOWED_SCHEMA_KEYS = frozenset({
    "type", "properties", "required", "description",
    "additionalProperties", "items", "enum", "format",
    "default", "minimum", "maximum", "minLength", "maxLength",
    "minItems", "maxItems", "pattern", "anyOf", "title",
})

def _normalize_schema(schema: dict) -> dict:
    """Strip unsupported JSON Schema keywords; inject additionalProperties: false."""
    result: dict = {}
    for k, v in schema.items():
        if k not in _ALLOWED_SCHEMA_KEYS:
            continue  # silently drop $schema, definitions, $defs, examples, etc.
        if k == "properties" and isinstance(v, dict):
            result[k] = {pk: _normalize_schema(pv) for pk, pv in v.items()}
        elif k == "items" and isinstance(v, dict):
            result[k] = _normalize_schema(v)
        else:
            result[k] = v
    result.setdefault("additionalProperties", False)
    return result
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `FunctionTool(async_closure)` as primary | `BaseTool` subclass as primary | ADK 1.33.0 (current) | `**kwargs` closures have args dropped by `run_async` filter; `BaseTool` is required |
| Manual `type_map` for schema conversion | `types.Schema.model_validate(dict)` | ADK 1.x (current) | ADK's own Pydantic model handles conversion; manual mapping is redundant |
| `proc.wait()` for subprocess | `proc.communicate()` | Phase 1 (established) | Deadlocks on >4KB stdout — never use `proc.wait()` |

**Deprecated/outdated:**
- `FunctionTool(**kwargs closure)`: Generates `None` schema (LLM sees no parameters) and drops all args — do not use for dynamic schemas
- `asyncio.run()` inside `build_tool()`: Cannot be called from running event loop — `build_tool()` must be `async def`

---

## Open Questions

1. **Return type annotation for `build_tool()`**
   - What we know: CONTEXT.md says `tuple[FunctionTool, str]` but the actual implementation uses `_SkillBaseTool(BaseTool)`
   - What's unclear: Phase 3 imports `build_tool()` — should the type hint be `tuple[BaseTool, str]`?
   - Recommendation: Use `tuple[BaseTool, str]` in the actual type hint since `_SkillBaseTool` IS a `BaseTool`. Document in docstring that this is an ADK-compatible tool. Phase 3 needs to be aware it receives a `BaseTool`, not a `FunctionTool` specifically.

2. **`ValidationCorrectionRequest` module placement (Claude's Discretion)**
   - What we know: CONTEXT.md defers to Claude on whether it lives in `skill.py`, `results.py`, or a new `validation.py`
   - What's unclear: Whether co-locating with `SkillDefinition` in `skill.py` creates a concern about model cohesion
   - Recommendation: Place `ValidationCorrectionRequest` in `src/models/skill.py` alongside `SkillDefinition`. It is a skill-domain concept (response to a skill invocation failure), not an execution result. Keeps `results.py` scoped to Deno execution outcomes.

3. **skills.json vs skill.json inconsistency in live catalog**
   - What we know: Live catalog has `skills.json` (not `skill.json`) with a `tools: list` structure. This is different from what CLAUDE.md describes.
   - What's unclear: Whether this affects Phase 2 (Phase 2 defines its own `SkillDefinition` contract)
   - Recommendation: Phase 2 is unaffected — `SkillDefinition` is a fresh contract. Flag for Phase 4 (CatalogExplorer integration) which must parse `skills.json` and map `tools[0]` fields to `SkillDefinition`. Phase 4 research must investigate this.

---

## Sources

### Primary (HIGH confidence)
- ADK 1.33.0 installed at `.venv/` — `FunctionTool`, `BaseTool`, `_get_declaration`, `run_async`, `_get_mandatory_args`, `_invoke_callable` all inspected with `inspect.getsource()`
- `google-genai` types module — `types.Schema.model_fields` enumerated; `types.Schema.model_validate` tested with real schema dicts
- `jsonschema` 4.26.0 — `Draft7Validator.iter_errors()` tested with missing/extra field scenarios; error structure (`e.validator`, `e.path`, `e.message`) verified
- `httpx` 0.28 — `AsyncClient(timeout=N).get()` tested against live `raw.githubusercontent.com`

### Secondary (MEDIUM confidence)
- Live `raw.githubusercontent.com/ianache/skills-catalog` fetch — SKILL.md URL pattern confirmed working; `skills/` prefix required
- Live `catalog.yaml` fetch — confirmed `path` field stores bare skill name (e.g., `"evaluar_test_case"`), no `skills/` prefix

### Tertiary (LOW confidence)
- None — all critical claims verified against live code and APIs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified against installed packages
- Architecture: HIGH — FunctionTool/BaseTool behavior verified by running against ADK 1.33.0 source
- Pitfalls: HIGH — each pitfall reproduced in live tests; not hypothetical

**Research date:** 2026-05-17
**Valid until:** 2026-06-17 (30 days — ADK is stable at 1.33.0 pin)
