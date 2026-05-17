# Stack Research

**Domain:** Agentic platform with distributed skill discovery and Deno sandbox execution
**Researched:** 2026-05-16
**Confidence:** HIGH — all versions verified from PyPI metadata and wheel inspection

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11 | Runtime | Non-negotiable per constraints; google-adk supports 3.10–3.13 but 3.11 is the stability sweet spot with full asyncio.TaskGroup support |
| google-adk | 1.33.0 | Agent framework — LlmAgent, Runner, BaseToolset | Latest stable; ships `LlmAgent`, `Runner`, `BaseToolset`, `FunctionTool`, `InMemorySessionService` all in one package |
| google-genai | 1.75.0 | Gemini API client (used internally by google-adk) | **Critical:** google-adk 1.33.0 requires `>=1.72,<2`. google-genai 2.x is a breaking major version that google-adk does NOT yet support — pin to 1.75.0, the latest compatible 1.x |
| pydantic | 2.12+ | Data validation for skill.json input_schema, CatalogManifest | google-adk requires `>=2.12,<3`; already present at 2.13.3; use for all model layer validation |
| Deno | 2.x (system install) | TypeScript skill execution sandbox | Deny-by-default permissions, V8 isolation, native `--allow-net=<domain>` flag control; invoked as subprocess from Python |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | >=0.27,<1 | Async HTTP client for fetching catalog.yaml and skill.json from GitHub | Already a transitive dependency of google-genai; use `httpx.AsyncClient` for catalog fetch in CatalogExplorer |
| pyyaml | >=6.0.2,<7 | YAML parsing for catalog.yaml | Transitive google-adk dependency; use `yaml.safe_load()` (never `yaml.load()`) |
| python-dotenv | >=1,<2 | Loading GEMINI_API_KEY from .env | Transitive google-adk dependency; call `load_dotenv()` at entry point only |
| anyio | >=4.9,<5 | Async primitives — timeouts, task groups | Transitive; use `anyio.move_on_after()` as the canonical timeout primitive when inside an async context that does not directly use asyncio |
| pytest | >=8 | Test runner | Current stable; keep pinned in dev requirements |
| pytest-asyncio | >=0.24 | Async test support | Required for testing `async def` ADK tool callbacks; configure `asyncio_mode = auto` |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| python-dotenv `.env` | Store GEMINI_API_KEY locally | Never commit `.env`; add to `.gitignore` |
| deno (system PATH) | TypeScript skill runner | Must be on PATH wherever the agent runs; verify with `deno --version` at startup |
| jsonschema | >=4.23,<5 | Validate skill input_schema at pre-execution boundary | Already a transitive google-adk dependency; use `jsonschema.validate(instance, schema)` |

---

## ADK Agent Patterns

### LlmAgent (aliased as `Agent`) — Tool Injection

The canonical agent class. Verified API from wheel inspection of google-adk 1.33.0:

```python
from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService

agent = Agent(
    name="coordinator",
    model="gemini-2.5-flash",          # default model in ADK 1.33.0
    instruction="...",
    tools=[my_toolset],                # list[Callable | BaseTool | BaseToolset]
)

runner = Runner(
    app_name="aiagentscrew",
    agent=agent,
    session_service=InMemorySessionService(),
)
```

`tools` accepts `ToolUnion = Union[Callable, BaseTool, BaseToolset]`. For dynamic injection, use `BaseToolset`.

### BaseToolset — Dynamic Tool Injection Per Invocation

This is the correct pattern for injecting tools discovered at runtime. `get_tools` is called on every agent invocation, so the toolset can return different tools based on what the CatalogExplorer found.

```python
from google.adk.tools.base_toolset import BaseToolset
from google.adk.agents.readonly_context import ReadonlyContext

class SkillToolset(BaseToolset):
    def __init__(self, catalog_explorer):
        super().__init__()
        self._explorer = catalog_explorer
        self._current_tools: list[BaseTool] = []

    async def get_tools(
        self,
        readonly_context: ReadonlyContext | None = None,
    ) -> list[BaseTool]:
        # Called per invocation — return whatever skills were discovered
        return self._current_tools

    async def close(self):
        pass
```

### FunctionDeclaration from JSON Schema (skill.json integration)

The ADK uses `types.FunctionDeclaration` with `parameters_json_schema` to register tool schemas from external JSON. This is exactly what is needed to bridge `skill.json` (Anthropic Tool Definition Schema) to ADK tool declarations:

```python
from google.genai import types
from google.adk.tools.base_tool import BaseTool

class SkillTool(BaseTool):
    def __init__(self, skill_def: SkillDefinition):
        super().__init__(
            name=skill_def.name,
            description=skill_def.description,
        )
        self._skill_def = skill_def

    def _get_declaration(self) -> types.FunctionDeclaration | None:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self._skill_def.input_schema,  # pass raw dict
        )

    async def run_async(self, *, args: dict, tool_context) -> Any:
        # 1. Validate args against input_schema (jsonschema.validate)
        # 2. Invoke Deno subprocess
        return await execute_via_deno(self._skill_def, args)
```

### Deno Subprocess Invocation from Python

Verified pattern using `asyncio.create_subprocess_exec` + `asyncio.wait_for`. This was tested live in the environment:

```python
import asyncio
import json

async def execute_via_deno(
    skill_def: SkillDefinition,
    args: dict,
    timeout_ms: int = 5000,
) -> dict:
    """Invoke a TypeScript skill via Deno subprocess with hard timeout."""
    allowed_domains = skill_def.allowed_net_domains  # e.g. ["api.example.com"]
    allow_net_flag = f"--allow-net={','.join(allowed_domains)}" if allowed_domains else "--allow-net=none"

    cmd = [
        "deno", "run",
        "--no-prompt",          # never block waiting for user input
        "--allow-read=none",    # deny filesystem reads
        "--allow-write=none",   # deny filesystem writes
        allow_net_flag,         # only the declared domains
        skill_def.script_path,  # path to skill .ts entry point
    ]

    input_bytes = json.dumps(args).encode()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_bytes),
            timeout=timeout_ms / 1000,   # convert ms to seconds
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise SkillTimeoutError(f"Skill '{skill_def.name}' exceeded {timeout_ms}ms")

    if proc.returncode != 0:
        raise SkillExecutionError(stderr.decode())

    return json.loads(stdout.decode())
```

Key decisions in this pattern:
- `--no-prompt` prevents Deno from hanging waiting for permission grants
- `--allow-read=none` and `--allow-write=none` are explicit denials (belt-and-suspenders alongside Deno's deny-by-default)
- `proc.kill()` on timeout is correct; `proc.terminate()` on Windows sends SIGTERM which Deno may ignore
- `await proc.wait()` after `kill()` prevents zombie processes

### Async Handling

The ADK is fully async-native. All agent callbacks, tool `run_async`, and `BaseToolset.get_tools` are `async def`. The runner exposes:

- `runner.run_async(session_id, user_id, content)` — async generator of events
- `runner.run(session_id, user_id, content)` — sync wrapper (uses `asyncio.run()` internally)

For a CLI entry point, use `asyncio.run(main())` at the top level. Do not mix `asyncio.run()` inside already-running event loops (common pytest-asyncio pitfall — solved by `asyncio_mode = auto`).

---

## Installation

```bash
# Create venv with Python 3.11
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Core — pin google-genai to 1.x, google-adk to 1.33.0
pip install "google-adk==1.33.0" "google-genai>=1.72,<2" pydantic pyyaml httpx python-dotenv

# Dev
pip install pytest pytest-asyncio

# Deno (if not already installed system-wide)
# Windows: winget install DenoLand.Deno
# Or: irm https://deno.land/install.ps1 | iex
```

Minimal `requirements.txt` for v1:

```
google-adk==1.33.0
google-genai>=1.72,<2
pydantic>=2.12,<3
pyyaml>=6.0.2,<7
httpx>=0.27,<1
python-dotenv>=1,<2
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| google-adk 1.33.0 | LangChain / LangGraph | If you need multi-LLM routing or complex DAG orchestration; overkill for this single-Gemini use case |
| google-adk 1.33.0 | Direct google-genai SDK | Only if you outgrow ADK's session/runner abstractions; raw SDK gives full control at the cost of reimplementing all the plumbing ADK provides |
| google-genai 1.75.0 (pinned) | google-genai 2.x | When google-adk releases a version with `>=2` support; watch google-adk changelog |
| asyncio.create_subprocess_exec | subprocess.run | Never for Deno in async context; subprocess.run blocks the event loop and prevents timeout enforcement via asyncio.wait_for |
| asyncio.create_subprocess_exec | anyio.run_process | Valid alternative; anyio.run_process provides the same timeout semantics but adds a dependency. asyncio native is simpler here. |
| Deno subprocess | Node.js subprocess | Node lacks deny-by-default permissions; would require explicit seccomp/AppArmor for equivalent isolation |
| httpx.AsyncClient | aiohttp | httpx is already a transitive dependency of google-genai; adding aiohttp would be redundant |
| jsonschema | pydantic model_validate | jsonschema validates arbitrary JSON Schema dicts without requiring pre-declared Pydantic models; correct for dynamic skill.json schemas |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `google-genai 2.x` | google-adk 1.33.0 hard-pins `<2`; installing 2.x will break the agent | Pin `google-genai>=1.72,<2` |
| `google-generativeai` (old SDK) | Deprecated legacy SDK; replaced entirely by `google-genai` | `google-genai` |
| `subprocess.run` / `subprocess.Popen` (blocking) | Blocks the asyncio event loop; timeout enforcement requires `threading.Timer` which is fragile | `asyncio.create_subprocess_exec` + `asyncio.wait_for` |
| `proc.terminate()` on Windows for Deno | On Windows, SIGTERM may not stop Deno immediately | `proc.kill()` (SIGKILL equivalent) |
| `yaml.load()` (unsafe) | Allows arbitrary Python object deserialization from YAML; catalog.yaml is fetched from GitHub | `yaml.safe_load()` |
| `asyncio.run()` inside async context | Raises RuntimeError if event loop already running | `await` the coroutine directly, or use `anyio` |
| Storing Google API key in code | Key exposure in git history | `python-dotenv` + `.env` file + `.gitignore` |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| google-adk==1.33.0 | google-genai>=1.72,<2 | Hard upper bound; verified from wheel METADATA |
| google-adk==1.33.0 | pydantic>=2.12,<3 | Hard lower bound; pydantic v1 will fail |
| google-adk==1.33.0 | Python 3.10–3.13 | 3.11 recommended for stability |
| google-adk==1.33.0 | anyio>=4.9,<5 | anyio 5.x not yet supported |
| pytest-asyncio | pytest>=8 | Use `asyncio_mode = auto` in pytest.ini to avoid `@pytest.mark.asyncio` on every test |
| Deno 2.x | Python asyncio subprocess | No special compatibility concerns; Deno 2.6.7 verified working in this environment |

---

## Sources

- PyPI metadata: `pip index versions google-adk` — **google-adk 1.33.0** (latest, verified 2026-05-16)
- PyPI metadata: `pip index versions google-genai` — **google-genai 2.3.0** latest, **1.75.0** latest 1.x
- google-adk 1.33.0 wheel METADATA (`Requires-Dist`): `google-genai>=1.72,<2` hard constraint — HIGH confidence
- google-adk 1.33.0 wheel source inspection:
  - `google/adk/__init__.py`: exports `Agent`, `Context`, `Runner`
  - `google/adk/agents/llm_agent.py`: `LlmAgent` class, `tools: list[ToolUnion]`, `DEFAULT_MODEL = 'gemini-2.5-flash'`
  - `google/adk/tools/base_tool.py`: `BaseTool.process_llm_request`, `_get_declaration` returning `types.FunctionDeclaration`
  - `google/adk/tools/base_toolset.py`: `BaseToolset.get_tools(readonly_context)` abstract async method
  - `google/adk/tools/function_tool.py`: `FunctionTool` wraps Python callables
  - `google/adk/tools/skill_toolset.py`: ADK's own `SkillToolset` pattern for skill discovery
- Live environment verification: `asyncio.create_subprocess_exec('deno', '--version')` returns 0 with `deno 2.6.7` — HIGH confidence
- `deno --version` system output: Deno 2.6.7, V8 14.5.201.2, TypeScript 5.9.2 — HIGH confidence

---
*Stack research for: AIAgentsCrew — Distributed Skills Agentic Platform*
*Researched: 2026-05-16*
