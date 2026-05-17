# Phase 3: Coordinating Agent + Two-Pass Routing - Research

**Researched:** 2026-05-17
**Domain:** ADK LlmAgent two-pass routing, structured output, Runner/Session lifecycle, JSONL logging, Config externalization
**Confidence:** HIGH (all critical claims verified by direct inspection of ADK 1.33.0 source and live constructor tests)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DISC-01 | CoordinatingAgent routes via confidence-gated fallback — if confidence < configurable threshold (default 0.72), delegates to CatalogExplorer | Two LlmAgent instances per run(): Pass 1 uses `output_schema=TagExtractionResult`, reads `session.state['routing']['confidence']`; threshold read from `Config.confidence_threshold`; Pass 2 runs with injected tool |
| DISC-02 | Pass 1 tag extraction constrains output to the catalog's actual tag vocabulary | Pass 1 system prompt explicitly lists available tags from `catalog_explorer.get_all_tags()`; `output_schema=TagExtractionResult` forces structured JSON with `tags: list[str]` constrained to that vocabulary |
| RELI-03 | Confidence threshold is externalized to config (env var or config file) — re-calibratable without code change | `src/config.py` reads `CONFIDENCE_THRESHOLD` env var with `float(os.environ.get("CONFIDENCE_THRESHOLD", "0.72"))`; `Config` dataclass injected into `CoordinatingAgent.__init__` — never hardcoded |
| RELI-04 | Each routing decision logged to JSONL (prompt hash, extracted tags, confidence score, routing decision, matched skill name if any) | `hashlib.sha256(prompt.encode()).hexdigest()[:12]` for prompt hash; `datetime.now(timezone.utc).isoformat()` for timestamp; `open(logs_path, "a")` append mode; `json.dumps(record) + "\n"` for JSONL format |
</phase_requirements>

---

## Summary

Phase 3 implements `CoordinatingAgent` in `src/agent.py` — the ADK-backed orchestrator that wires the Phase 1 (DenoRunner) and Phase 2 (SkillInjector) layers into a two-pass routing loop. Pass 1 runs a structured-output `LlmAgent` that extracts `{confidence: float, tags: list[str]}` from the user prompt, constrained to the catalog's tag vocabulary. If confidence falls below the externalized threshold, Pass 2 runs a fresh `LlmAgent` with the skill tool injected and SKILL.md appended to the system instruction.

The ADK 1.33.0 mechanics for this pattern are fully verified: `LlmAgent(output_schema=TagExtractionResult, output_key='routing', include_contents='none')` stores the structured result in `session.state['routing']` as a `dict`. `runner.agent` is mutable — swapping it between passes is safe and is the correct pattern (one `Runner` per `CoordinatingAgent`, two `LlmAgent` instances rebuilt fresh per `run()` call). Direct inspection of `InMemorySessionService.append_event()` confirms that `state_delta` is applied to session storage during iteration, so `session_service.get_session()` returns the updated state immediately after the `async for` loop completes.

Phase 3 also introduces `src/config.py` (a frozen dataclass reading all env vars) and the JSONL routing log written to `logs/routing.jsonl`. The `CatalogExplorer` is not implemented in Phase 3 — tests use an `AsyncMock` stub that exposes `find(tags) -> SkillDefinition | None` and `get_all_tags() -> list[str]`. Phase 4 will wire in the real `CatalogExplorer` and verify the interface contract matches.

**Primary recommendation:** Implement `CoordinatingAgent` by creating one `Runner` per instance, swapping `runner.agent` between Pass 1 (structured output) and Pass 2 (tool-injected) within each `run()` call, using fresh sessions per `run()` call and `include_contents='none'` on both agents to prevent cross-pass history contamination.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `google-adk` | 1.33.0 (pinned) | `LlmAgent`, `Runner`, `InMemorySessionService` | Already in pyproject.toml; exact version required |
| `google-genai` | >=1.72,<2 | `types.Content`, `types.Part` for `new_message` construction | Shared with ADK; `types.Content(role='user', parts=[types.Part(text=prompt)])` is the message format |
| `pydantic` | >=2.12,<3 | `TagExtractionResult` structured output model; `Config` frozen dataclass (or Pydantic model) | Established by Phases 1+2 |
| `hashlib` (stdlib) | Python 3.13 | `sha256` prompt hashing for JSONL log | Zero deps; `hashlib.sha256(prompt.encode()).hexdigest()[:12]` |
| `json` (stdlib) | Python 3.13 | JSONL record serialization | Zero deps; `json.dumps(record) + "\n"` |
| `datetime` (stdlib) | Python 3.13 | ISO timestamp for JSONL log | Zero deps; `datetime.now(timezone.utc).isoformat()` |
| `pathlib` (stdlib) | Python 3.13 | `logs/routing.jsonl` path construction | Zero deps; `Path("logs/routing.jsonl")` |
| `os` (stdlib) | Python 3.13 | Env var reads in `config.py` | Zero deps; `os.environ.get("CONFIDENCE_THRESHOLD", "0.72")` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `google.adk.sessions.InMemorySessionService` | 1.33.0 | Per-run session lifecycle | Always — development and test; production would use a persistent service but that is v2 scope |
| `google.adk.agents.LlmAgent` | 1.33.0 | Both Pass 1 and Pass 2 agents | One instance per pass, built fresh in `run()` |
| `google.adk.Runner` | 1.33.0 | Drives agent execution loop; holds session service | One `Runner` per `CoordinatingAgent` instance; `.agent` field is swapped per pass |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Two `LlmAgent` instances (fresh per run) | One `LlmAgent` mutating `.tools` | Mutating shared agent between concurrent REPL invocations causes tool carryover; CLAUDE.md explicitly forbids it |
| `include_contents='none'` on both agents | Default `include_contents='default'` | Default mode includes session history; Pass 1 residue would pollute Pass 2 with structured JSON output in the conversation history |
| Fresh `Session` per `run()` call | Reusing same session across all calls | Reuse builds up event history; combined with `include_contents='none'`, both work but fresh sessions are simpler to reason about |
| `dataclass(frozen=True)` for `Config` | Pydantic `BaseModel` | Both work; frozen dataclass is lighter-weight and has no external deps beyond stdlib; sufficient for env-var reads |

**Installation:** All dependencies already present in `pyproject.toml`. No new packages required for Phase 3.

---

## Architecture Patterns

### Recommended Project Structure

From `CLAUDE.md` (pre-specified), extended with Phase 3 additions:

```
src/
├── __init__.py
├── config.py           # Config frozen dataclass — all env var reads
├── agent.py            # CoordinatingAgent — two-pass routing, JSONL log
├── skill_injector.py   # Phase 2 (complete)
├── execution/
│   └── deno_runner.py  # Phase 1 (complete)
└── models/
    ├── skill.py        # SkillDefinition, ValidationCorrectionRequest (Phase 2, complete)
    └── results.py      # ExecutionResult union (Phase 1, complete)

logs/
└── .gitkeep            # routing.jsonl written here at runtime

tests/
├── conftest.py         # Add: sample_config fixture, mock CatalogExplorer fixture
└── test_agent.py       # Phase 3 TDD test suite (new file)
```

### Pattern 1: Two-Pass LlmAgent Run

**What:** Pass 1 uses `output_schema` for structured JSON extraction. Pass 2 uses a tool-injected agent. Both use `include_contents='none'` to prevent history contamination.

**When to use:** Every `CoordinatingAgent.run()` call where confidence is below threshold.

```python
# Source: verified against ADK 1.33.0 installed source + constructor tests

from pydantic import BaseModel
from google.adk.agents import LlmAgent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

class TagExtractionResult(BaseModel):
    confidence: float
    tags: list[str]

# Pass 1 agent — built once, reused each call (tools=[] by default)
_pass1_agent = LlmAgent(
    name='coordinating_agent_pass1',
    model='gemini-2.5-flash-001',
    instruction="""You are a routing agent. Extract intent tags from the user prompt.
Return a JSON object with:
- confidence: float between 0.0 and 1.0 (how confident you are you can answer directly)
- tags: list of 1-3 tags from this vocabulary ONLY: {tag_vocabulary}

If confidence >= 0.72, you can answer directly. If < 0.72, the system will fetch a skill.
Always return valid JSON matching the schema.""",
    output_schema=TagExtractionResult,
    output_key='routing',
    include_contents='none',
)

# Pass 2 agent — built fresh per run() when routing to a skill
def _build_pass2_agent(skill_tool, skill_md: str, model: str, base_instruction: str) -> LlmAgent:
    instruction = base_instruction
    if skill_md:
        instruction = f"{base_instruction}\n\n---\n{skill_md}"
    return LlmAgent(
        name='coordinating_agent_pass2',
        model=model,
        instruction=instruction,
        tools=[skill_tool],
        include_contents='none',
    )
```

### Pattern 2: Runner with Swappable Agent

**What:** One `Runner` per `CoordinatingAgent` instance. Swap `runner.agent` between Pass 1 and Pass 2. Verified: `runner.agent` is a plain attribute assignment.

**When to use:** Inside `CoordinatingAgent.run()` before each pass.

```python
# Source: verified by direct attribute assignment test against ADK 1.33.0 Runner

class CoordinatingAgent:
    def __init__(self, catalog_explorer, skill_injector, config):
        self._catalog_explorer = catalog_explorer
        self._skill_injector = skill_injector
        self._config = config
        self._session_service = InMemorySessionService()
        self._pass1_agent = LlmAgent(
            name='coordinating_agent_pass1',
            model=config.model_version,
            output_schema=TagExtractionResult,
            output_key='routing',
            include_contents='none',
        )
        self._runner = Runner(
            app_name='coordinating_agent',
            agent=self._pass1_agent,
            session_service=self._session_service,
        )

    async def run(self, prompt: str) -> str:
        user_id = 'default'
        session = await self._session_service.create_session(
            app_name='coordinating_agent',
            user_id=user_id,
        )
        session_id = session.id
        new_message = types.Content(
            role='user',
            parts=[types.Part(text=prompt)]
        )

        # Pass 1: structured tag + confidence extraction
        self._runner.agent = self._pass1_agent
        async for _event in self._runner.run_async(
            user_id=user_id, session_id=session_id, new_message=new_message
        ):
            pass  # state_delta applied during iteration

        # Read structured result from session state
        session = await self._session_service.get_session(
            app_name='coordinating_agent',
            user_id=user_id,
            session_id=session_id,
        )
        routing = session.state.get('routing', {})
        confidence = routing.get('confidence', 0.0)
        tags = routing.get('tags', [])

        final_text = ''
        skill_name = None
        decision = 'direct_answer'

        if confidence < self._config.confidence_threshold:
            # Pass 2: catalog route
            skill_def = await self._catalog_explorer.find(tags)
            if skill_def:
                tool, skill_md = await self._skill_injector.build_tool(skill_def)
                skill_name = skill_def.name
                pass2_agent = _build_pass2_agent(
                    tool, skill_md, self._config.model_version,
                    'You are an execution agent. Use the available tool to fulfill the request.'
                )
                self._runner.agent = pass2_agent
                async for event in self._runner.run_async(
                    user_id=user_id, session_id=session_id, new_message=new_message
                ):
                    if event.is_final_response() and event.content and event.content.parts:
                        text = ''.join(
                            p.text for p in event.content.parts
                            if p.text and not p.thought
                        )
                        if text.strip():
                            final_text = text
                decision = 'catalog_route'
            else:
                decision = 'no_skill_found'
                final_text = 'No matching skill found for your request.'
        else:
            # High-confidence: extract Pass 1 final response
            # Re-run or extract from events — see Pitfall 3 below for correct approach
            decision = 'direct_answer'
            final_text = _extract_final_text_from_session(session)

        # JSONL log — always, regardless of decision
        await self._write_routing_log(prompt, tags, confidence, decision, skill_name)
        return final_text
```

### Pattern 3: Structured Output Result Extraction

**What:** After Pass 1 `async for` loop completes, call `session_service.get_session()` to get the updated session. `session.state['routing']` is a `dict` (not a Pydantic model — `validate_schema` returns `dict`).

**When to use:** After every Pass 1 run.

```python
# Source: verified by inspecting InMemorySessionService.append_event() +
#         validate_schema() return type test

# After Pass 1 completes:
session = await session_service.get_session(
    app_name='coordinating_agent',
    user_id=user_id,
    session_id=session_id,
)
routing: dict = session.state.get('routing', {})
confidence: float = routing.get('confidence', 0.0)   # float
tags: list[str] = routing.get('tags', [])             # list[str]
```

**Important:** `validate_schema()` in `LlmAgent._save_output()` returns a `dict`, not a Pydantic model. Access fields with `.get()`, not attribute access.

### Pattern 4: Final Text Extraction from Pass 1 (High-Confidence Path)

**What:** For the direct-answer path (confidence >= threshold), extract the final text from Pass 1 session events. Since `output_schema` was set, the session's last event contains the JSON string, not a natural language answer. **High confidence direct answers should use a separate direct-answer agent without `output_schema`.**

**When to use:** High-confidence path only.

**Correct approach for direct-answer:**

```python
# Pass 1 with output_schema ONLY extracts tags+confidence — it always returns structured JSON.
# For high-confidence prompts that should be answered directly, run Pass 2 WITHOUT a skill tool.
# This means Pass 2 = natural language agent, no tools, no output_schema.

# Alternative: use a separate LlmAgent for direct answers
_direct_agent = LlmAgent(
    name='coordinating_agent_direct',
    model=config.model_version,
    instruction='Answer the user prompt directly and helpfully.',
    include_contents='none',
)
```

**Anti-pattern:** Trying to extract a natural language answer from a `output_schema`-constrained agent — it will always return JSON, not prose.

### Pattern 5: JSONL Routing Log

**What:** Append one JSON-lines record per `run()` call to `logs/routing.jsonl`.

**When to use:** Always, at the end of every `run()` call, regardless of routing decision.

```python
# Source: stdlib only — hashlib, json, datetime, pathlib

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

_ROUTING_LOG_PATH = Path('logs/routing.jsonl')

async def _write_routing_log(
    self,
    prompt: str,
    tags: list[str],
    confidence: float,
    decision: str,
    skill_name: str | None,
) -> None:
    record = {
        'prompt_hash': hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:12],
        'tags': tags,
        'confidence': confidence,
        'decision': decision,
        'skill_name': skill_name,
        'ts': datetime.now(timezone.utc).isoformat(),
    }
    # File I/O is fast; blocking open() is acceptable in an async context here
    _ROUTING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_ROUTING_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record) + '\n')
```

### Pattern 6: Config Dataclass

**What:** All env var reads centralized in `src/config.py`. Frozen dataclass — immutable after construction.

**When to use:** `Config.from_env()` called once at startup (in `main.py`), then injected into `CoordinatingAgent.__init__`.

```python
# Source: CLAUDE.md component contracts + RELI-03 requirement

import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    gemini_api_key: str
    github_token: str | None
    confidence_threshold: float
    model_version: str

    @classmethod
    def from_env(cls) -> 'Config':
        return cls(
            gemini_api_key=os.environ['GEMINI_API_KEY'],
            github_token=os.environ.get('GITHUB_TOKEN'),
            confidence_threshold=float(
                os.environ.get('CONFIDENCE_THRESHOLD', '0.72')
            ),
            model_version=os.environ.get(
                'MODEL_VERSION', 'gemini-2.5-flash-001'
            ),
        )
```

### Pattern 7: CatalogExplorer Stub for Phase 3 Tests

**What:** A test double providing the two methods `CoordinatingAgent` needs from `CatalogExplorer`. No real GitHub calls.

**When to use:** All Phase 3 tests. Phase 4 replaces this with the real implementation.

```python
# tests/conftest.py addition for Phase 3

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.models.skill import SkillDefinition

@pytest.fixture
def sample_skill_def() -> SkillDefinition:
    return SkillDefinition(
        name='evaluar_test_case',
        description='Evaluates a test case',
        path='evaluar_test_case',
        input_schema={
            'type': 'object',
            'properties': {'test_case': {'type': 'string'}},
            'required': ['test_case'],
        },
        allow_net_domains=['github.com'],
    )

@pytest.fixture
def mock_catalog_explorer(sample_skill_def):
    explorer = MagicMock()
    explorer.find = AsyncMock(return_value=sample_skill_def)
    explorer.get_all_tags = AsyncMock(return_value=['evaluation', 'test', 'story', 'review'])
    return explorer
```

### Anti-Patterns to Avoid

- **Mutating `self._pass1_agent.tools`:** Never append tools to an existing agent's list. Always create a new `LlmAgent` for Pass 2. CLAUDE.md: "Tools list rebuilt on every `agent.run()` call."
- **Using `include_contents='default'`:** Pass 1 structured JSON output appears in session history. Pass 2 would see it and try to interpret `{"confidence": 0.45, "tags": [...]}` as conversation history.
- **Reading `session.state['routing']` as Pydantic model:** `validate_schema()` returns a plain `dict`. Use `routing.get('confidence', 0.0)`, not `routing.confidence`.
- **Writing JSONL with `json.dump()` (no newline):** JSONL format requires one record per line. Always `json.dumps(record) + '\n'`.
- **Hardcoding the model version string:** Use `config.model_version` throughout. `'gemini-2.5-flash-001'` pinned in env, not in source.
- **Calling `asyncio.run()` inside `run()`:** Already running in an event loop (pytest-asyncio, production loop). Use `await` only.
- **Creating a new `Runner` per `run()` call:** `Runner.__init__` is expensive (plugin manager init, agent introspection). Create one `Runner` per `CoordinatingAgent` instance.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured JSON extraction from LLM | Parse LLM text with `re.search(r'\{.*\}', text)` | `LlmAgent(output_schema=Pydantic, output_key='key')` | ADK enforces response_mime_type=application/json + validates against schema; regex is fragile against whitespace/formatting variations |
| Confidence score evaluation | Logit probability calculations | `output_schema.confidence` as a self-reported float from the LLM | LLM self-reports confidence directly in structured output; external probability calculations add complexity without accuracy benefit for this use case |
| Session state management | Custom dict with event replay | `InMemorySessionService` + `session.state` | ADK handles event ordering, state_delta merging, append semantics — all correct behaviors are built in |
| Event stream text extraction | Parse `str(event)` | `event.is_final_response()` + `event.content.parts[n].text` | `is_final_response()` correctly excludes tool calls, partial events, and thought events |
| JSONL logging | Structured logging framework | `open(path, 'a') + json.dumps()` | Zero deps; JSONL is trivially parseable; no logging framework overhead for a simple append-only record |

**Key insight:** The ADK `output_schema` + `output_key` pattern eliminates ALL JSON parsing risk. The LLM is forced into a schema-constrained mode, the output is parsed by ADK, and the result is stored directly in session state as a validated `dict`. Never try to parse structured output from event text manually.

---

## Common Pitfalls

### Pitfall 1: Pass 1 Structured Output Contains JSON, Not a Direct Answer

**What goes wrong:** When confidence is >= 0.72, the developer tries to return the Pass 1 final response as a natural-language answer. But Pass 1 has `output_schema` set, so the LLM always returns `{"confidence": 0.85, "tags": ["..."]}`  — not a human-readable response.
**Why it happens:** Mistaking the structured-output agent for a dual-purpose agent.
**How to avoid:** Use a third, separate `LlmAgent` (or no `output_schema`) for the direct-answer path. Pass 1 is ONLY for extraction. If confidence is high, run a second lightweight pass with no tools and no schema.
**Warning signs:** High-confidence responses return raw JSON strings to the user instead of natural language.

### Pitfall 2: Session State Not Updated Until `async for` Loop Completes

**What goes wrong:** Reading `session.state['routing']` mid-iteration (inside the `async for event in runner.run_async(...)` loop) before the final event with `state_delta` is yielded. The `routing` key is absent from state until the final event is appended.
**Why it happens:** `InMemorySessionService.append_event()` applies `state_delta` only when the event is appended, which happens during iteration. The key is only available after the loop finishes.
**How to avoid:** Always read `session.state` using `await session_service.get_session(...)` AFTER the `async for` loop completely finishes.
**Warning signs:** `session.state.get('routing', {})` returns `{}` even after a successful Pass 1 run.

### Pitfall 3: `validate_schema()` Returns dict, Not Pydantic Model

**What goes wrong:** Code accesses `routing.confidence` (attribute access) instead of `routing['confidence']` (dict access). `AttributeError` raised at runtime.
**Why it happens:** `LlmAgent._save_output()` calls `validate_schema(self.output_schema, result)` which returns a `dict`, not an instance of `TagExtractionResult`.
**How to avoid:** Always use `.get()` dict access: `routing.get('confidence', 0.0)`, `routing.get('tags', [])`.
**Warning signs:** `AttributeError: 'dict' object has no attribute 'confidence'`.

### Pitfall 4: Tools Leak Across REPL Invocations If Agent Is Reused

**What goes wrong:** An agent's `tools` list is appended to (not replaced) between calls. In a REPL loop, the second prompt sees both the first skill's tool AND the second skill's tool. The LLM may call the wrong tool.
**Why it happens:** Mutating `self._runner.agent.tools.append(tool)` instead of creating a new `LlmAgent`.
**How to avoid:** Always create a new `LlmAgent` for Pass 2: `pass2_agent = LlmAgent(tools=[tool], ...)`. Then `self._runner.agent = pass2_agent`. Never mutate the tools list of an existing agent.
**Warning signs:** In a multi-turn REPL session, later prompts call tools registered for earlier prompts.

### Pitfall 5: Fresh Session Per Run Creates Unbounded InMemorySessionService Growth

**What goes wrong:** Creating a new session per `run()` call in a long-lived REPL fills `InMemorySessionService.sessions` with stale entries. Over hundreds of interactions, memory grows without bound.
**Why it happens:** `InMemorySessionService` never evicts sessions automatically.
**How to avoid:** For Phase 3 (and Phase 5 CLI), either (a) reuse one session per REPL lifetime (user_id + session_id fixed at startup), or (b) delete sessions after use via `session_service.delete_session()` if available, or (c) recreate `InMemorySessionService` each `run()` call (no stale data, but slight overhead). Given Phase 3 is not a long-lived production service, option (c) is the safest.
**Warning signs:** Memory growth during test runs that iterate `run()` many times.

### Pitfall 6: `output_schema` with `tools` in Pass 1

**What goes wrong:** If Pass 1 accidentally has tools registered, ADK may enter a tool-calling loop before producing the structured output. The `routing` key may not be set if tool calls occur.
**Why it happens:** ADK's docs say `output_schema` and `tools` can coexist — but that's for Pass 2, not Pass 1. For Pass 1, no tools should be registered.
**How to avoid:** Pass 1 agent always has `tools=[]` (the default). Verify this explicitly in the `__init__`.
**Warning signs:** Pass 1 runs longer than expected; `session.state.get('routing')` is None after Pass 1.

### Pitfall 7: Confidence Threshold Miscalibration After Model Pin Change

**What goes wrong:** Pinning `gemini-2.5-flash-001` and setting `CONFIDENCE_THRESHOLD=0.72` works at initial calibration. A later model upgrade to `gemini-2.5-flash-002` shifts the distribution; 0.72 now routes too aggressively or too conservatively.
**Why it happens:** Self-reported confidence scores from LLMs are not absolute probabilities; they are distribution-dependent.
**How to avoid:** Pin the model version explicitly. Externalize the threshold in `CONFIDENCE_THRESHOLD` env var (already done per RELI-03). Monitor the JSONL routing log for catalog fetch rate over time.
**Warning signs:** After any model version change, the `decision: catalog_route` rate in `routing.jsonl` changes significantly.

---

## Code Examples

Verified patterns from ADK 1.33.0 source inspection and constructor tests:

### Pass 1 Agent Construction
```python
# Source: verified against LlmAgent constructor, output_schema field, output_key field

from pydantic import BaseModel
from google.adk.agents import LlmAgent

class TagExtractionResult(BaseModel):
    confidence: float
    tags: list[str]

pass1_agent = LlmAgent(
    name='coordinating_agent_pass1',
    model='gemini-2.5-flash-001',
    instruction="""Extract intent from the user prompt.
Return JSON with:
- confidence: 0.0-1.0 (your confidence you can answer directly without a skill)
- tags: 1-3 tags from this vocabulary ONLY: {tag_vocabulary}""",
    output_schema=TagExtractionResult,
    output_key='routing',
    include_contents='none',  # No history contamination
)
# Verified: output_schema accepts type[BaseModel]
# Verified: validate_schema returns dict, not TagExtractionResult instance
# Verified: include_contents='none' is a valid Literal value
```

### Runner + Session Lifecycle
```python
# Source: verified Runner.__init__ signature + InMemorySessionService.create_session signature

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

session_service = InMemorySessionService()
runner = Runner(
    app_name='coordinating_agent',
    agent=pass1_agent,
    session_service=session_service,
)

# Per run() call:
session = await session_service.create_session(
    app_name='coordinating_agent',
    user_id='default',
)

# Run Pass 1
async for _event in runner.run_async(
    user_id='default',
    session_id=session.id,
    new_message=types.Content(
        role='user',
        parts=[types.Part(text=prompt)]
    ),
):
    pass  # Drain events; state_delta applied during iteration

# Read state AFTER loop (not during)
updated_session = await session_service.get_session(
    app_name='coordinating_agent',
    user_id='default',
    session_id=session.id,
)
routing: dict = updated_session.state.get('routing', {})
confidence: float = routing.get('confidence', 0.0)
tags: list[str] = routing.get('tags', [])
```

### Swapping Runner Agent for Pass 2
```python
# Source: verified by direct attribute assignment test on ADK 1.33.0 Runner instance

from google.adk.agents import LlmAgent

# runner.agent is a plain attribute — direct assignment works
pass2_agent = LlmAgent(
    name='coordinating_agent_pass2',
    model='gemini-2.5-flash-001',
    instruction=f'Use the available tool to fulfill the request.\n\n{skill_md}',
    tools=[skill_tool],         # Fresh list with single tool
    include_contents='none',
)
runner.agent = pass2_agent     # Safe: no side effects on previous agent

# Extract final text from Pass 2
final_text = ''
async for event in runner.run_async(
    user_id='default',
    session_id=session.id,
    new_message=types.Content(role='user', parts=[types.Part(text=prompt)]),
):
    if event.is_final_response() and event.content and event.content.parts:
        text = ''.join(
            p.text for p in event.content.parts
            if p.text and not p.thought
        )
        if text.strip():
            final_text = text
```

### JSONL Routing Log Write
```python
# Source: stdlib — hashlib, json, datetime, pathlib

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

_LOG_PATH = Path('logs/routing.jsonl')

def _write_routing_log(
    prompt: str,
    tags: list[str],
    confidence: float,
    decision: str,
    skill_name: str | None,
) -> None:
    record = {
        'prompt_hash': hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:12],
        'tags': tags,
        'confidence': confidence,
        'decision': decision,
        'skill_name': skill_name,
        'ts': datetime.now(timezone.utc).isoformat(),
    }
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record) + '\n')
```

### Config from Environment
```python
# Source: CLAUDE.md component contracts + RELI-03

import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    gemini_api_key: str
    github_token: str | None
    confidence_threshold: float
    model_version: str

    @classmethod
    def from_env(cls) -> 'Config':
        return cls(
            gemini_api_key=os.environ['GEMINI_API_KEY'],
            github_token=os.environ.get('GITHUB_TOKEN'),
            confidence_threshold=float(
                os.environ.get('CONFIDENCE_THRESHOLD', '0.72')
            ),
            model_version=os.environ.get(
                'MODEL_VERSION', 'gemini-2.5-flash-001'
            ),
        )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Parsing LLM JSON output from event text with regex | `output_schema` + `output_key` on `LlmAgent` | ADK 1.x (current feature) | Eliminates manual JSON parsing; ADK validates schema and stores in session state automatically |
| `global_instruction` on `LlmAgent` | Per-agent `instruction` field | ADK 1.33.0 (deprecated) | `global_instruction` is deprecated; use `instruction` on each agent |
| Mutable tools list between REPL turns | Fresh `LlmAgent` per routing invocation | ADK best practice | Prevents tool carryover bugs in multi-turn sessions |
| `proc.wait()` for subprocess | `proc.communicate()` | Phase 1 (established) | Never revisit; deadlocks on large Deno stdout |

**Deprecated/outdated:**
- `LlmAgent.global_instruction`: Marked deprecated in ADK 1.33.0 source with comment "Use GlobalInstructionPlugin instead." Use `instruction` field on each agent.
- `FunctionTool(**kwargs closure)`: Phase 2 confirmed this drops all args in ADK 1.33.0. Use `_SkillBaseTool(BaseTool)` from Phase 2.

---

## Open Questions

1. **Direct Answer Path: Two-Pass or Three-Pass?**
   - What we know: Pass 1 with `output_schema` always returns JSON, not natural language. For confidence >= 0.72, a natural language answer requires a separate agent run without `output_schema`.
   - What's unclear: Does the CLAUDE.md architecture intend that high-confidence prompts are answered by Pass 1 itself (with the structured JSON as the "answer") or by a third pass? The `agent.py` contract says "Pass 2: run with injected tool + SKILL.md" — high confidence path is not described.
   - Recommendation: For Phase 3, implement a "Pass 1.5" — a lightweight `LlmAgent` without `output_schema` run only on the high-confidence path. This adds one more LLM call for high-confidence prompts but is architecturally clean. Alternatively, the planner may choose to return a "I can answer this directly" message and skip the natural language response in Phase 3 scope (since the primary goal is routing, not user-facing quality).

2. **`catalog_explorer.get_all_tags()` — Interface Not in CLAUDE.md**
   - What we know: Pass 1 system prompt "includes catalog tag vocabulary" per CLAUDE.md. This requires getting the tag list from somewhere.
   - What's unclear: CLAUDE.md's `CatalogExplorer` contract only specifies `async def find(tags: list[str]) -> SkillDefinition | None`. There is no `get_all_tags()` specified.
   - Recommendation: Phase 3 adds `get_all_tags() -> list[str]` to the `CatalogExplorer` protocol definition (as an informal contract) and uses it in `CoordinatingAgent.__init__` or `run()`. Phase 4 implements the real method (reads from cached `catalog.yaml`). The stub for Phase 3 tests returns a hardcoded list.

3. **Session-per-run vs Session-per-lifetime**
   - What we know: Creating a session per `run()` call prevents state leakage. Reusing a session across calls allows conversation history (disabled by `include_contents='none'` anyway).
   - What's unclear: For the Phase 5 CLI REPL, should a single session persist for the entire REPL session?
   - Recommendation: Phase 3 uses fresh session per `run()` call (simplest). Phase 5 can introduce session persistence if conversational context becomes valuable.

---

## Validation Architecture

> `workflow.nyquist_validation` is not set in `.planning/config.json` (the key is absent). Skipping Validation Architecture section.

> Note: `.planning/config.json` has `"workflow": {"research": true, "plan_check": true, "verifier": true}` but no `nyquist_validation` key. Treating as false per spec.

---

## Sources

### Primary (HIGH confidence)
- ADK 1.33.0 installed at `.venv/` — `LlmAgent` source (`llm_agent.py`): all fields (`model`, `instruction`, `output_schema`, `output_key`, `include_contents`, `tools`) verified by source read and constructor tests
- ADK 1.33.0 installed at `.venv/` — `Runner` source (`runners.py`): `__init__` signature, `run_async` signature, `runner.agent` attribute mutability confirmed by assignment test
- ADK 1.33.0 installed at `.venv/` — `InMemorySessionService` source: `create_session`, `get_session`, `append_event` signatures; `state_delta` application timing (applied during `append_event`, not at end of loop) verified by source read
- ADK 1.33.0 installed at `.venv/` — `Event` source: `is_final_response()` method implementation; `content.parts[n].text` access pattern; `thought` field exclusion pattern
- ADK 1.33.0 installed at `.venv/` — `_schema_utils.validate_schema()`: confirmed return type is `dict`, not Pydantic model
- Phases 1+2 RESEARCH.md — established patterns for subprocess, SkillInjector, BaseTool

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` (2026-05-16) — confidence threshold drift warning, tag vocabulary constraint importance, JSONL logging recommendations
- `.planning/STATE.md` accumulated decisions — "Rebuild tools list fresh (never mutate shared list between calls)", "JSONL routing log to logs/routing.jsonl", "two-pass routing"

### Tertiary (LOW confidence)
- None — all critical claims verified against live ADK 1.33.0 source

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in pyproject.toml; no new dependencies
- Architecture: HIGH — LlmAgent fields, Runner mutation, session state timing all verified by direct source inspection and constructor tests
- Pitfalls: HIGH — Pitfalls 1-4 verified from ADK source; Pitfalls 5-7 verified from Phase 1+2 experience and PITFALLS.md

**Research date:** 2026-05-17
**Valid until:** 2026-06-17 (30 days — ADK is pinned at 1.33.0; patterns are stable)
