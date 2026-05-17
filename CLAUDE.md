# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

CLI-based agentic platform that dynamically discovers and executes distributed skills without redeploying the core agent. A user types a prompt; the Coordinating Agent finds the right skill in a GitHub-hosted catalog and runs it via a Deno sandbox.

**Status:** Pre-implementation — no source files exist yet. All planning documents live in `.planning/`; the research notes in `.planning/research/` contain the verified ADK patterns and version constraints that inform implementation.

## Setup and Commands

```powershell
# Create venv with Python 3.13+ using uv
uv venv --python 3.13
.venv\Scripts\activate

# Install v1 dependencies (requirements.txt also contains v2 packages — install explicitly for v1)
uv pip install "google-adk==1.33.0" "google-genai>=1.72,<2" "pydantic>=2.12,<3" "pyyaml>=6.0.2,<7" "httpx>=0.27,<1" "python-dotenv>=1,<2" pytest pytest-asyncio

# Verify Deno is on PATH (required for skill execution)
deno --version

# Copy and populate .env with your keys
# GEMINI_API_KEY=...
# GITHUB_TOKEN=...   (optional, raises GitHub rate limit from 60 to 5000 req/hr)
```

Run the agent:
```powershell
uv run python main.py
```

Run tests:
```powershell
uv run pytest                                      # all tests
uv run pytest tests/path/test_foo.py::test_name    # single test
```

## Architecture

### Layer Diagram

```
┌──────────────────────────────────────────────┐
│  CLI Layer                                   │
│  main.py — asyncio.run(), spinner, env load  │
└──────────────────────┬───────────────────────┘
                       │ prompt: str
┌──────────────────────▼───────────────────────┐
│  Orchestration Layer                         │
│  src/agent.py — CoordinatingAgent            │
│  · Pass 1: structured JSON → confidence+tags │
│  · If confidence < threshold → discovery     │
│  · Pass 2: re-run with injected FunctionTool │
│  · Logs every routing decision to JSONL      │
└──────────┬────────────────────┬──────────────┘
           │ tags: list[str]    │ FunctionTool
┌──────────▼──────────┐  ┌─────▼──────────────┐
│  Discovery Layer    │  │  Injection Layer    │
│  src/catalog_       │  │  src/skill_         │
│  explorer.py        │  │  injector.py        │
│  · fetch catalog.   │  │  · SkillDefinition  │
│    yaml (TTL cache) │  │    → FunctionTool   │
│  · tag intersection │  │  · JSON Schema      │
│  · lazy-load   ─────┼─▶│    validation       │
│    skill.json       │  │  · SKILL.md inject  │
└─────────────────────┘  └──────────┬──────────┘
                                    │ validated params
                         ┌──────────▼──────────┐
                         │  Execution Layer     │
                         │  src/execution/      │
                         │    deno_runner.py    │
                         │  · asyncio subprocess│
                         │  · 5000ms timeout    │
                         │  · --allow-net guard │
                         │  · JSON stdin/stdout │
                         └─────────────────────┘
```

### Folder Structure

```
aiagentscrew/
│
├── main.py                       # Entry: load_dotenv(), asyncio.run(main()),
│                                 #   Rich spinner, structured error messages
├── src/
│   ├── __init__.py
│   ├── config.py                 # All env reads: GEMINI_API_KEY, GITHUB_TOKEN,
│   │                             #   CONFIDENCE_THRESHOLD (0.72), MODEL_VERSION
│   ├── agent.py                  # CoordinatingAgent: wraps ADK LlmAgent + Runner,
│   │                             #   two-pass routing, tools reset per run() call,
│   │                             #   JSONL routing log to logs/routing.jsonl
│   ├── catalog_explorer.py       # CatalogExplorer: fetch catalog.yaml (5-min TTL
│   │                             #   in-memory cache), tag intersection, lazy-load
│   │                             #   skill.json — uses raw.githubusercontent.com
│   ├── skill_injector.py         # SkillInjector: SkillDefinition → ADK FunctionTool,
│   │                             #   injects additionalProperties:false, fetches
│   │                             #   SKILL.md for agent context
│   ├── execution/
│   │   ├── __init__.py
│   │   └── deno_runner.py        # DenoRunner: asyncio.create_subprocess_exec,
│   │                             #   proc.communicate() (never proc.wait()),
│   │                             #   allow_net domain regex validation,
│   │                             #   Windows: taskkill /F /T /PID on timeout
│   └── models/
│       ├── __init__.py
│       ├── skill.py              # CatalogManifest, CatalogSkill, SkillDefinition,
│       │                         #   InputSchema — zero ADK/Deno deps, shared contract
│       └── results.py            # ExecutionSuccess, TimeoutError, ExecutionError,
│                                 #   ValidationFailure — Pydantic models, Phase 1+
├── tests/
│   ├── conftest.py               # Fixtures: sample SkillDefinition, temp .ts files,
│   │                             #   mock CatalogExplorer responses
│   ├── fixtures/
│   │   └── skills/
│   │       └── echo_skill.ts     # Minimal TS fixture: reads JSON stdin, echoes it back
│   ├── execution/
│   │   └── test_deno_runner.py   # Phase 1: timeout kill, zombie cleanup, JSON I/O,
│   │                             #   allow_net injection guard, pipe deadlock check
│   ├── test_skill_injector.py    # Phase 2: FunctionTool shape, schema validation,
│   │                             #   missing required field rejection
│   ├── test_catalog_explorer.py  # Phase 4: live GitHub, TTL cache hit/miss,
│   │                             #   GITHUB_TOKEN auth, raw URL confirmed
│   └── test_agent.py             # Phase 5 E2E: prompt → skill output, routing log
│
├── logs/
│   └── .gitkeep                  # routing.jsonl written here at runtime (gitignored)
│
├── .env.example                  # GEMINI_API_KEY=, GITHUB_TOKEN=,
│                                 #   CONFIDENCE_THRESHOLD=0.72,
│                                 #   MODEL_VERSION=gemini-2.5-flash-001
├── .gitignore                    # .env, .venv/, logs/*.jsonl, __pycache__/
└── pyproject.toml                # [tool.pytest.ini_options] asyncio_mode = "auto"
```

### Component Contracts

**`src/models/results.py`** — Pydantic result types, imported by execution and injection layers

```python
class ExecutionSuccess(BaseModel):    # data: dict — parsed JSON from Deno stdout
class TimeoutError(BaseModel):        # type='timeout', elapsed_ms: int
class ExecutionError(BaseModel):      # type='execution_error', exit_code: int, stderr: str
class ValidationFailure(BaseModel):   # type='validation_failure', invalid_domain: str

ExecutionResult = ExecutionSuccess | TimeoutError | ExecutionError | ValidationFailure
```

**`src/execution/deno_runner.py`** — zero ADK dependency

```python
class DenoRunner:
    async def execute(self, skill_path: str, params: dict,
                      allow_net_domains: list[str], extra_flags: list[str] = []) -> ExecutionResult
    # 1. Validate each domain against r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    #    → return ValidationFailure(invalid_domain=...) — no subprocess spawned
    # 2. Caller-supplied extra_flags appended (caller owns all permission flags)
    # 3. asyncio.create_subprocess_exec(
    #      "deno", "run", "--no-prompt",
    #      f"--allow-net={','.join(domains)}", *extra_flags, skill_path,
    #      stdin=PIPE, stdout=PIPE, stderr=PIPE)
    # 4. asyncio.wait_for(proc.communicate(input=json_bytes), timeout=5.0)
    #    TimeoutError → proc.kill() → await proc.wait() → return TimeoutError(elapsed_ms=...)
    #    On Windows: taskkill /F /T /PID (os.killpg unavailable)
    # 5. returncode != 0 → return ExecutionError(exit_code=..., stderr=...)
    # 6. stdout not valid JSON → return ExecutionError (strict stdout contract)
    # Always returns ExecutionResult — never raises for execution outcomes
```

**`src/skill_injector.py`** — depends on DenoRunner + models; minimal ADK surface

```python
class SkillInjector:
    def build_tool(self, skill_def: SkillDefinition) -> FunctionTool
    # 1. Fetch SKILL.md from GitHub → returned separately for agent context injection
    # 2. Copy input_schema, inject additionalProperties:false if absent
    # 3. Build async closure _execute(**kwargs):
    #      jsonschema.Draft7Validator(schema).iter_errors(kwargs) → raise SkillValidationError
    #      result = await deno_runner.execute(skill_def.path, kwargs, skill_def.allow_net_domains)
    #      isinstance check on result: re-raise or return data
    # 4. _execute.__name__ = skill_def.name; __doc__ = skill_def.description
    # 5. return FunctionTool(func=_execute)
    # Fallback if FunctionTool introspection fails: BaseTool subclass with
    #   explicit _get_declaration() returning types.FunctionDeclaration
```

**`src/agent.py`** — ADK-heavy; wires all layers

```python
class CoordinatingAgent:
    # __init__ receives: CatalogExplorer, SkillInjector, Config (injected, no globals)
    async def run(self, prompt: str) -> str
    # Pass 1: system prompt includes catalog tag vocabulary for constrained extraction
    #   → structured output {confidence: float, tags: list[str]}
    # If confidence < config.threshold:
    #   skill_def = await catalog_explorer.find(tags)
    #   tool, skill_md = skill_injector.build_tool(skill_def)
    #   Rebuild tools list fresh (never mutate shared list between calls)
    # Pass 2: run with injected tool + SKILL.md appended to system instruction
    # Always: append JSONL record to logs/routing.jsonl
    #   {prompt_hash, tags, confidence, decision, skill_name, ts}
```

**`src/catalog_explorer.py`** — verify these contracts are met by existing code

```python
class CatalogExplorer:
    async def find(self, tags: list[str]) -> SkillDefinition | None
    # Must use raw.githubusercontent.com (not api.github.com)
    # Must cache catalog.yaml with 5-min TTL (time.monotonic)
    # Must pass Authorization: Bearer {GITHUB_TOKEN} when env var is set
    # Must fetch skill.json files concurrently (asyncio.gather) when >1 candidate
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `models/results.py` as separate module | All layers import Pydantic result types; prevents circular deps |
| `config.py` centralizes all env reads | Threshold and model version never hardcoded; one place to change |
| Tools list rebuilt on every `agent.run()` | Prevents injected tools from leaking across REPL invocations |
| `proc.communicate()` mandatory, never `proc.wait()` | `proc.wait()` deadlocks when Deno stdout exceeds ~4KB pipe buffer on Windows |
| `taskkill /F /T /PID` on timeout (Windows) | `os.killpg` is POSIX-only; this environment is Windows 11 |
| `BaseTool._get_declaration()` as fallback | `FunctionTool` closure introspection is Phase 2's highest-risk unknown |
| `raw.githubusercontent.com` for catalog fetches | CDN-backed, no API rate limit; `api.github.com` costs quota |
| Tag vocabulary passed in Pass 1 system prompt | Constrains Gemini to catalog terms — prevents open-vocabulary tag mismatch |

### GitHub SSOT (`https://github.com/ianache/skills-catalog`)

- `catalog.yaml` — lightweight tag index (fetched with 5-min TTL cache)
- `skills/<name>/skill.json` — Anthropic Tool Definition Schema (`name`, `description`, `input_schema`)
- `skills/<name>/SKILL.md` — cognitive guide + few-shot examples, injected into agent context alongside the tool

## Critical Constraints

| Constraint | Detail |
|------------|--------|
| `google-genai` version | Must be `>=1.72,<2`. Version 2.x breaks `google-adk==1.33.0` (hard upper bound in wheel METADATA) |
| Deno subprocess | Use `asyncio.create_subprocess_exec` — `subprocess.run` blocks the event loop and breaks timeout enforcement |
| YAML parsing | Always `yaml.safe_load()` — `yaml.load()` allows arbitrary Python deserialization |
| pytest async | Configure `asyncio_mode = auto` in `pytest.ini` — eliminates `@pytest.mark.asyncio` boilerplate |
| Tests | Tests hit the live GitHub repo (`https://github.com/ianache/skills-catalog`) — no mocks per project decision |
| ADK default model | `gemini-2.5-flash` (ADK 1.33.0 default) |

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GEMINI_API_KEY` | Yes | Gemini API access |
| `GITHUB_TOKEN` | Recommended | Authenticated catalog fetches (5000 req/hr vs 60) |
| `CONFIDENCE_THRESHOLD` | No | Override default 0.72 routing threshold |

Load with `python-dotenv` at entry point only (`load_dotenv()` in `main.py`). Never commit `.env`.

## Roadmap (5 Phases)

Phases execute sequentially — each phase is independently testable before the next begins.

1. **Deno Execution Channel** — `src/execution/deno_runner.py` + `src/models/results.py`, Pydantic Union return, zombie cleanup
2. **Skill Injection Bridge** — `src/skill_injector.py`, JSON Schema validation, FunctionTool construction
3. **Coordinating Agent + Routing** — `src/agent.py`, two-pass loop, confidence threshold, JSONL log
4. **CatalogExplorer Integration** — wire `src/catalog_explorer.py` into agent with 5-min TTL cache
5. **CLI Entry Point + E2E** — `main.py` + `src/config.py`, verified with one real TypeScript skill

v2 scope (out of scope for v1): WebAssembly/Extism channel, MCP/Qdrant channel, multi-skill DAG chaining, vector cache, ISO 27001 logging, FastAPI endpoint.
