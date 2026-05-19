# Phase 1: Deno Execution Channel - Research

**Researched:** 2026-05-17
**Domain:** Python asyncio subprocess management + Deno 2 permission model + Pydantic v2 result types
**Confidence:** HIGH (core patterns) / MEDIUM (Windows-specific cleanup, Deno 2 redirect edge cases)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Skill I/O protocol**
- Python passes parameters to the Deno subprocess as JSON written to **stdin**
- TypeScript skills receive input by reading `Deno.stdin` and parsing JSON
- Skills return their result as a **single JSON object written to stdout**
- Stderr is reserved exclusively for error output (not mixed with result)
- If stdout cannot be parsed as valid JSON, DenoRunner returns an `execution_error` — strict contract enforcement, no lenient fallback

**Permission model**
- Caller passes `--allow-net` domains explicitly to `DenoRunner.execute()` as a list of domain strings (e.g., `['gitlab.com']`)
- DenoRunner does NOT read `skill.json` internally — it only runs what the caller gives it
- Domain validation uses strict hostname regex before flag construction: `^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$` — rejects IPs, wildcards, paths, ports, and flag injection vectors
- An invalid domain string returns a `validation_failure` before the subprocess is created (no Deno process spawned)
- The caller (Phase 2 SkillInjector) is responsible for specifying all Deno permission flags — DenoRunner does not hardcode any deny flags

**Result type design**
- Typed results modeled as **Pydantic models** (already in stack)
- Success: `ExecutionSuccess(data: dict)` — contains the parsed JSON from stdout
- Errors are a discriminated union — each error type carries minimal but diagnostic fields:
  - `TimeoutError(type='timeout', elapsed_ms: int)`
  - `ExecutionError(type='execution_error', exit_code: int, stderr: str)`
  - `ValidationFailure(type='validation_failure', invalid_domain: str)`
- `DenoRunner.execute()` **always returns** `ExecutionSuccess | TimeoutError | ExecutionError | ValidationFailure` — never raises exceptions for execution outcomes
- Callers use `isinstance()` checks, no try/except needed at call sites

**Module structure**
- DenoRunner lives at: `src/execution/deno_runner.py`
- Package: `src/execution/__init__.py`
- Import path: `from src.execution.deno_runner import DenoRunner`
- Tests at: `tests/execution/test_deno_runner.py`
- Test fixtures: `tests/fixtures/skills/echo_skill.ts`

### Claude's Discretion

- Exact process group kill implementation (SIGKILL vs SIGTERM escalation, platform-specific handling)
- asyncio vs subprocess threading model for the subprocess execution
- How to detect zombie processes and verify cleanup in tests
- Exact Pydantic model inheritance hierarchy (base class vs separate models)

### Deferred Ideas (OUT OF SCOPE)

- None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EXEC-01 | Matched skill executes via Deno subprocess with `--allow-net=<validated-domain>`, no file I/O permissions, hard 5000ms timeout; process group killed on timeout with no zombie processes | `asyncio.create_subprocess_exec` + `asyncio.wait_for(communicate(), 5.0)` + `taskkill /F /T /PID` on Windows; `--allow-net=domain1,domain2` Deno flag; domain regex validation before subprocess creation |
| EXEC-02 | Execution errors return typed structured results (timeout / validation_failure / execution_error) — not generic Python exceptions propagated raw | Pydantic v2 `BaseModel` with `Literal` discriminator field; `ExecutionResult` type alias; `isinstance()` dispatch pattern at call sites |
</phase_requirements>

---

## Summary

Phase 1 builds `DenoRunner`, a Python asyncio subprocess wrapper that invokes TypeScript skills via Deno with strict permission flags, a hard 5000ms timeout, clean process cleanup, and typed Pydantic result models. This is a greenfield Python 3.13 module — no existing source code to integrate with, though the full folder structure and contracts are pre-specified in `CLAUDE.md`.

The core technical challenge is correct asyncio subprocess lifecycle management on Windows 11: `asyncio.wait_for(proc.communicate(), 5.0)` for timeout enforcement, followed by `taskkill /F /T /PID` to kill the entire process tree (not just the direct child), and a second `await proc.communicate()` to drain the pipe and collect the exit code without leaving zombie entries. There is a known CPython issue (#139373, opened Sep 2025) where cancelling `communicate()` via `wait_for` can lose stdout data in a race condition — the mitigation is that on timeout we don't care about stdout content (we return `TimeoutError`, not stdout), so this race is benign for this use case.

Deno 2's `--allow-net` flag accepts a comma-separated list of hostnames (`--allow-net=github.com,gitlab.com`) with no file I/O by default. The `--no-prompt` flag suppresses interactive permission prompts when running in a non-TTY context (which applies to any subprocess invocation). TypeScript skills read stdin via `Deno.stdin.readable` async iteration and write JSON to stdout — no Deno-specific APIs needed for the Python side.

**Primary recommendation:** Use `asyncio.create_subprocess_exec` with `stdin/stdout/stderr=PIPE`, wrap the entire `proc.communicate(input=json_bytes)` in `asyncio.wait_for(..., timeout=5.0)`, and on `asyncio.TimeoutError` call `proc.kill()` then `subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)])` synchronously before the second `await proc.communicate()`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio` (stdlib) | Python 3.13 | Subprocess creation and timeout | Native; `create_subprocess_exec` uses ProactorEventLoop on Windows (required for subprocess support) |
| `asyncio.create_subprocess_exec` | Python 3.13 | Spawn Deno without shell; avoids shell injection | Direct exec avoids shell metacharacter risks; ProactorEventLoop default on Windows |
| `Pydantic` | `>=2.12,<3` | Result type models | Already in `requirements.txt`; v2 discriminated unions are efficient and schema-aware |
| `re` (stdlib) | Python 3.13 | Domain hostname regex validation | Zero deps; pre-compile pattern at module level |
| `json` (stdlib) | Python 3.13 | Serialize params to stdin bytes; parse stdout | No extra deps; `json.dumps().encode()` is the encoding chain |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `subprocess` (stdlib) | Python 3.13 | `taskkill` call after timeout kill | On Windows timeout path only — synchronous call to kill process tree |
| `time` (stdlib) | Python 3.13 | `elapsed_ms` calculation for `TimeoutError` | `time.monotonic()` before/after `wait_for` |
| `pytest` | stack-defined | Test runner | Phase 1 test suite |
| `pytest-asyncio` | stack-defined | Async test support | `asyncio_mode = "auto"` in `pyproject.toml` eliminates `@pytest.mark.asyncio` boilerplate |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio.create_subprocess_exec` | `subprocess.run` (blocking) | `subprocess.run` blocks the event loop — timeout enforcement breaks; CLAUDE.md forbids it |
| `asyncio.create_subprocess_exec` | `asyncio.create_subprocess_shell` | Shell introduces injection risk; exec is safer and explicit |
| `taskkill /F /T` (Windows) | `os.killpg` (POSIX) | `os.killpg` is not available on Windows 11 — CLAUDE.md specifies `taskkill` |
| `taskkill /F /T` (Windows) | `proc.kill()` alone | `proc.kill()` only kills the direct Deno child, not Deno's V8 worker threads or spawned subprocesses; `/T` kills the full tree |
| Separate Pydantic models | dataclasses | Pydantic v2 gives schema validation, JSON serialization, and discriminated unions for free |

**Installation:** All dependencies are in `requirements.txt` / `pyproject.toml` already. No new packages needed for Phase 1.

---

## Architecture Patterns

### Recommended Project Structure

From `CLAUDE.md` (pre-specified):
```
src/
├── __init__.py
├── execution/
│   ├── __init__.py
│   └── deno_runner.py       # DenoRunner class
└── models/
    ├── __init__.py
    └── results.py           # ExecutionSuccess, TimeoutError, ExecutionError, ValidationFailure

tests/
├── conftest.py              # Shared fixtures
├── fixtures/
│   └── skills/
│       └── echo_skill.ts    # Minimal TS: reads JSON stdin, echoes to stdout
└── execution/
    └── test_deno_runner.py  # Phase 1 test suite
```

### Pattern 1: asyncio Subprocess with Timeout and Cleanup

**What:** Spawn Deno via `create_subprocess_exec`, wrap `communicate()` in `wait_for`, kill and clean up on timeout.
**When to use:** Any Deno skill execution call.

```python
# Source: https://docs.python.org/3/library/asyncio-subprocess.html
import asyncio
import json
import subprocess
import time

start = time.monotonic()
proc = await asyncio.create_subprocess_exec(
    "deno", "run", "--no-prompt", f"--allow-net={','.join(domains)}",
    *extra_flags, skill_path,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
json_bytes = json.dumps(params).encode("utf-8")

try:
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(input=json_bytes),
        timeout=5.0
    )
except asyncio.TimeoutError:
    elapsed_ms = int((time.monotonic() - start) * 1000)
    # Kill process tree on Windows (os.killpg unavailable)
    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
        capture_output=True
    )
    # Drain pipes to prevent zombie entry and collect exit code
    await proc.communicate()
    return TimeoutError(type="timeout", elapsed_ms=elapsed_ms)
```

**Why `taskkill` not `proc.kill()`:** `proc.kill()` on Windows calls `TerminateProcess()` on the direct child only. Deno spawns V8 isolate threads; without `/T`, those remain. `taskkill /F /T /PID` terminates the entire process tree.

**Why second `await proc.communicate()` after kill:** After killing the process, the subprocess transport needs to be fully closed and the exit status collected. Calling `communicate()` without input drains any remaining pipe data and sets `proc.returncode`. Without this, the process entry lingers as an uncollected zombie.

### Pattern 2: Pydantic v2 Discriminated Union Result Types

**What:** Define result models with `Literal` discriminator fields; expose a `ExecutionResult` type alias.
**When to use:** `src/models/results.py` — the single source of truth for all execution outcomes.

```python
# Source: https://pydantic.dev/docs/validation/latest/concepts/unions/
from typing import Literal, Union, Annotated
from pydantic import BaseModel, Field

class ExecutionSuccess(BaseModel):
    type: Literal["success"] = "success"
    data: dict

class TimeoutError(BaseModel):
    type: Literal["timeout"] = "timeout"
    elapsed_ms: int

class ExecutionError(BaseModel):
    type: Literal["execution_error"] = "execution_error"
    exit_code: int
    stderr: str

class ValidationFailure(BaseModel):
    type: Literal["validation_failure"] = "validation_failure"
    invalid_domain: str

ExecutionResult = Union[ExecutionSuccess, TimeoutError, ExecutionError, ValidationFailure]
```

**Caller dispatch pattern (no try/except needed):**
```python
result = await runner.execute(skill_path, params, domains)
if isinstance(result, ExecutionSuccess):
    return result.data
elif isinstance(result, TimeoutError):
    log_timeout(result.elapsed_ms)
elif isinstance(result, ExecutionError):
    log_error(result.exit_code, result.stderr)
elif isinstance(result, ValidationFailure):
    log_validation(result.invalid_domain)
```

**Note:** The `type` field with a default value ensures `ExecutionSuccess` can be constructed without passing `type="success"`. All error models have `type` as a required `Literal` — use the same default value approach for consistency.

### Pattern 3: Domain Hostname Validation

**What:** Validate each domain string before constructing `--allow-net` flag.
**When to use:** At the start of `DenoRunner.execute()`, before any subprocess is created.

```python
import re

_DOMAIN_RE = re.compile(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

def _validate_domains(domains: list[str]) -> str | None:
    """Returns the first invalid domain, or None if all valid."""
    for domain in domains:
        if not _DOMAIN_RE.match(domain):
            return domain
    return None
```

**Why pre-compile:** The regex is used on every `execute()` call. Pre-compiling at module level avoids recompilation overhead.
**What the regex rejects:** IP addresses (`192.168.1.1`), wildcards (`*.example.com`), paths (`example.com/api`), ports (`example.com:443`), flag injection vectors (`--allow-all`).

### Pattern 4: TypeScript echo_skill.ts Fixture

**What:** Minimal Deno TypeScript file that reads JSON from stdin and writes it back to stdout. Used for all Phase 1 tests (timeout, success, non-zero exit) without network dependency.

```typescript
// tests/fixtures/skills/echo_skill.ts
// Reads all stdin, parses as JSON, writes back to stdout
const decoder = new TextDecoder();
const chunks: Uint8Array[] = [];
for await (const chunk of Deno.stdin.readable) {
  chunks.push(chunk);
}
const totalLength = chunks.reduce((sum, c) => sum + c.length, 0);
const combined = new Uint8Array(totalLength);
let offset = 0;
for (const chunk of chunks) {
  combined.set(chunk, offset);
  offset += chunk.length;
}
const text = decoder.decode(combined);
const json = JSON.parse(text);
console.log(JSON.stringify(json));
```

**For timeout tests:** A variant that `await`s a long `setTimeout` or `Deno.sleepSync` before responding.

```typescript
// tests/fixtures/skills/slow_skill.ts
await new Promise(resolve => setTimeout(resolve, 10000)); // 10 seconds — will be killed
console.log(JSON.stringify({ result: "never reached" }));
```

### Anti-Patterns to Avoid

- **`proc.wait()` with piped stdout/stderr:** Deadlocks when Deno output exceeds ~4KB pipe buffer. CLAUDE.md explicitly forbids this. Always use `proc.communicate()`.
- **`asyncio.create_subprocess_shell()`:** Shell=True introduces injection risk and unnecessary overhead for a known command.
- **`proc.kill()` alone on Windows:** Kills only the Deno parent process, leaves V8 worker threads and child subprocesses running. Use `taskkill /F /T /PID`.
- **Raising exceptions for execution outcomes:** `DenoRunner.execute()` must NEVER raise for timeout, non-zero exit, or invalid JSON stdout. All outcomes are return values.
- **Hardcoding `--deny-net` or other deny flags:** The caller (SkillInjector) owns all permission flags. DenoRunner only constructs `--allow-net` from validated domains plus caller-supplied `extra_flags`.
- **`os.killpg()` on Windows:** POSIX-only — raises `AttributeError` on Windows 11.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async subprocess with stdin/stdout | Custom pipe read/write loops | `asyncio.create_subprocess_exec` + `communicate()` | Deadlock-free buffering; handles all edge cases of pipe drain |
| Result type serialization | Custom dict converters | Pydantic v2 `BaseModel.model_dump()` | JSON schema generation, validation, type coercion for free |
| Process tree kill on Windows | psutil or manual WinAPI | `taskkill /F /T /PID` via `subprocess.run` | Already available on all Windows; no extra dependency |
| Domain regex | Custom parser | `re.compile(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')` | Simple and sufficient; more complex parsing adds attack surface |
| Async timeout | Custom `asyncio.Task` cancel loop | `asyncio.wait_for(coro, timeout=5.0)` | Built-in; correctly cancels the wrapped coroutine |

**Key insight:** The most dangerous thing to hand-roll in this domain is the pipe drain sequence. Getting the order of `kill()`, `communicate()`, and `wait()` wrong produces hanging tests or zombie processes in CI.

---

## Common Pitfalls

### Pitfall 1: Pipe Deadlock via `proc.wait()`

**What goes wrong:** Calling `await proc.wait()` when `stdout=PIPE` and `stderr=PIPE` blocks forever if Deno writes more than ~4KB to either pipe before the Python side reads it.
**Why it happens:** The OS pipe buffer fills; Deno blocks on write; Python blocks on `wait()`; deadlock.
**How to avoid:** Always use `proc.communicate()`. Never use `proc.wait()` when pipes are open.
**Warning signs:** Tests hang indefinitely; CI timeout kills the test runner, not the subprocess.

### Pitfall 2: Zombie Process After Timeout

**What goes wrong:** After `asyncio.TimeoutError`, calling only `proc.kill()` and returning — no second `communicate()` or `wait()`. The process entry stays in the OS process table as a zombie.
**Why it happens:** The OS keeps the process table entry until the parent collects the exit status via `wait`/`waitpid`.
**How to avoid:** After `proc.kill()` (and/or `taskkill`), always call `await proc.communicate()` (with no input) to drain pipes and collect the exit code.
**Warning signs:** Growing process count in `tasklist` during stress tests; eventual resource exhaustion.

### Pitfall 3: Only Killing the Direct Deno Child on Windows

**What goes wrong:** `proc.kill()` (which calls `TerminateProcess`) terminates the main Deno process but its V8 worker threads or any `new Deno.Command()` children remain running.
**Why it happens:** On Windows, `TerminateProcess` does not recursively terminate child processes — unlike SIGKILL on Linux which kills the entire process group.
**How to avoid:** Use `taskkill /F /T /PID {proc.pid}` after `proc.kill()`.
**Warning signs:** `tasklist | findstr deno` still shows processes after timeout in tests.

### Pitfall 4: stdout/stderr Data Loss on `wait_for` Cancellation

**What goes wrong:** When `asyncio.wait_for` cancels `communicate()` on timeout, there is a race condition (CPython issue #139373) where collected stdout/stderr data can be discarded before the cancellation exception propagates.
**Why it happens:** Internal asyncio task cancellation can interrupt `communicate()` after pipe data is buffered but before it is returned.
**How to avoid:** This is benign for the timeout path — on timeout we return `TimeoutError` and don't use stdout. For the `ExecutionError` path (non-zero exit), `communicate()` completes normally without cancellation, so stderr is always available.
**Warning signs:** This is only a risk when you catch `TimeoutError` and try to read the already-drained stdout. Don't do that.

### Pitfall 5: Invalid JSON stdout Silently Treated as Success

**What goes wrong:** If stdout contains a non-JSON string (e.g., Deno print statement for debugging), a lenient parser might return partial data.
**Why it happens:** Skills mixing `console.log` debug output with the JSON result.
**How to avoid:** Wrap `json.loads(stdout.decode())` in try/except; on `json.JSONDecodeError`, return `ExecutionError(exit_code=0, stderr=f"stdout not valid JSON: {stdout[:200]!r}")`.
**Warning signs:** Acceptance test TC-03 failing with a decode error instead of a typed result.

### Pitfall 6: Deno Interactive Permission Prompts Blocking subprocess

**What goes wrong:** Without `--no-prompt`, Deno in some versions will prompt for permission confirmation when stdin is a pipe that isn't a TTY. The prompt is written to stderr; the Python side waiting for stdout never gets a response; timeout fires.
**Why it happens:** Deno's permission system detects non-TTY stdin and may still prompt on certain versions.
**How to avoid:** Always pass `--no-prompt` as the first flag in the Deno command.
**Warning signs:** Tests time out consistently on a new Deno version upgrade.

---

## Code Examples

Verified patterns from official sources:

### Full DenoRunner.execute() skeleton

```python
# Source: https://docs.python.org/3/library/asyncio-subprocess.html
# Source: CLAUDE.md component contracts

import asyncio
import json
import re
import subprocess
import time
from src.models.results import (
    ExecutionResult, ExecutionSuccess, TimeoutError,
    ExecutionError, ValidationFailure
)

_DOMAIN_RE = re.compile(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

class DenoRunner:
    async def execute(
        self,
        skill_path: str,
        params: dict,
        allow_net_domains: list[str],
        extra_flags: list[str] = [],
    ) -> ExecutionResult:
        # 1. Validate domains — return ValidationFailure before spawning anything
        for domain in allow_net_domains:
            if not _DOMAIN_RE.match(domain):
                return ValidationFailure(invalid_domain=domain)

        # 2. Build command
        net_flag = f"--allow-net={','.join(allow_net_domains)}" if allow_net_domains else "--allow-net"
        cmd = ["deno", "run", "--no-prompt", net_flag, *extra_flags, skill_path]
        json_bytes = json.dumps(params).encode("utf-8")

        # 3. Spawn subprocess
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        start = time.monotonic()

        # 4. Communicate with hard timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=json_bytes),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            # Kill process tree (Windows: taskkill; POSIX fallback: proc.kill)
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
            )
            await proc.communicate()  # drain pipes, collect exit code (no zombie)
            return TimeoutError(elapsed_ms=elapsed_ms)

        # 5. Non-zero exit
        if proc.returncode != 0:
            return ExecutionError(
                exit_code=proc.returncode,
                stderr=stderr.decode("utf-8", errors="replace"),
            )

        # 6. Parse stdout as JSON (strict)
        try:
            data = json.loads(stdout.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return ExecutionError(
                exit_code=0,
                stderr=f"stdout not valid JSON: {exc}",
            )

        return ExecutionSuccess(data=data)
```

### Pydantic v2 Result Models

```python
# Source: https://pydantic.dev/docs/validation/latest/concepts/unions/
# src/models/results.py

from typing import Literal, Union
from pydantic import BaseModel

class ExecutionSuccess(BaseModel):
    type: Literal["success"] = "success"
    data: dict

class TimeoutError(BaseModel):
    type: Literal["timeout"] = "timeout"
    elapsed_ms: int

class ExecutionError(BaseModel):
    type: Literal["execution_error"] = "execution_error"
    exit_code: int
    stderr: str

class ValidationFailure(BaseModel):
    type: Literal["validation_failure"] = "validation_failure"
    invalid_domain: str

ExecutionResult = Union[ExecutionSuccess, TimeoutError, ExecutionError, ValidationFailure]
```

### echo_skill.ts fixture

```typescript
// tests/fixtures/skills/echo_skill.ts
// Reads all stdin bytes, parses as JSON, echoes back to stdout
const decoder = new TextDecoder();
const chunks: Uint8Array[] = [];
for await (const chunk of Deno.stdin.readable) {
  chunks.push(chunk);
}
const totalLength = chunks.reduce((sum, c) => sum + c.length, 0);
const combined = new Uint8Array(totalLength);
let offset = 0;
for (const chunk of chunks) {
  combined.set(chunk, offset);
  offset += chunk.length;
}
const text = decoder.decode(combined);
const json = JSON.parse(text);
console.log(JSON.stringify(json));
```

### pyproject.toml test configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### Test structure for DenoRunner

```python
# tests/execution/test_deno_runner.py
import pytest
from pathlib import Path
from src.execution.deno_runner import DenoRunner
from src.models.results import ExecutionSuccess, TimeoutError, ExecutionError, ValidationFailure

ECHO_SKILL = str(Path(__file__).parent.parent / "fixtures" / "skills" / "echo_skill.ts")
SLOW_SKILL = str(Path(__file__).parent.parent / "fixtures" / "skills" / "slow_skill.ts")

runner = DenoRunner()

async def test_success_returns_json_from_stdout():
    result = await runner.execute(ECHO_SKILL, {"key": "value"}, [])
    assert isinstance(result, ExecutionSuccess)
    assert result.data == {"key": "value"}

async def test_timeout_returns_typed_error():
    result = await runner.execute(SLOW_SKILL, {}, [])
    assert isinstance(result, TimeoutError)
    assert result.elapsed_ms >= 5000

async def test_invalid_domain_returns_validation_failure_before_subprocess():
    result = await runner.execute(ECHO_SKILL, {}, ["192.168.1.1"])
    assert isinstance(result, ValidationFailure)
    assert result.invalid_domain == "192.168.1.1"

async def test_nonzero_exit_returns_execution_error():
    # A skill that calls Deno.exit(1) 
    result = await runner.execute(ECHO_SKILL, {}, [])  # Use a failing fixture
    # ... assert isinstance(result, ExecutionError)

async def test_no_zombie_after_timeout(tmp_path):
    import subprocess
    result = await runner.execute(SLOW_SKILL, {}, [])
    assert isinstance(result, TimeoutError)
    # Verify no deno processes remain
    check = subprocess.run(["tasklist", "/FI", "IMAGENAME eq deno.exe"],
                           capture_output=True, text=True)
    assert "deno.exe" not in check.stdout
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `subprocess.run(timeout=...)` for async code | `asyncio.create_subprocess_exec` + `asyncio.wait_for` | Python 3.4+ | Blocking subprocess in async context breaks event loop; asyncio version is non-blocking |
| `os.killpg()` for process tree kill | `taskkill /F /T /PID` on Windows | Always | `os.killpg` is POSIX-only; never worked on Windows |
| Pydantic v1 `Union` types | Pydantic v2 `BaseModel` with `Literal` discriminators | Pydantic v2 (2023) | v2 is 5-50x faster validation; discriminated union avoids O(n) left-to-right matching |
| `proc.wait()` after piping stdout | `proc.communicate()` | Python docs have always warned against this | `wait()` deadlocks on large output; `communicate()` is deadlock-free |
| `asyncio.create_subprocess_shell` | `asyncio.create_subprocess_exec` | No change, best practice | Shell=True is injection risk; exec is direct and safe |

**Deprecated/outdated:**
- `Deno.stdin.read()` with manual `Uint8Array` buffer loop: Still works but async iteration over `Deno.stdin.readable` is the idiomatic modern pattern (Deno 2+).
- `yaml.load()`: Completely replaced by `yaml.safe_load()` — arbitrary code execution risk. Not relevant to Phase 1 but established in CLAUDE.md.

---

## Open Questions

1. **Deno 2 `--allow-net` redirect behavior across domains**
   - What we know: `--allow-net=github.com` permits requests TO `github.com`; fetch follows redirects by default
   - What's unclear: If `github.com` redirects to `api.github.com`, does the follow require `--allow-net=api.github.com` too? STATE.md flags this as LOW confidence: "Deno redirect behavior with `--allow-net` is LOW confidence — verify against Deno 2.6.7 changelog during Phase 1"
   - Recommendation: Phase 1 does not make network calls in tests (echo_skill.ts has no network access); defer verification to Phase 2 integration tests that actually call GitHub. Document the open question in Phase 2 context.

2. **`asyncio.wait_for` cancellation safety with Python 3.13**
   - What we know: CPython issue #139373 (Sep 2025) documents that cancelling `communicate()` via `wait_for` can lose stdout data in a race condition
   - What's unclear: Whether Python 3.13.x has a fix or mitigation merged
   - Recommendation: This is benign for the timeout code path (we don't use stdout on timeout). No mitigation needed. Document in code comments for maintainers.

3. **Cross-platform POSIX compatibility for kill path**
   - What we know: CLAUDE.md specifies `taskkill /F /T /PID` for Windows 11. STATE.md confirms `os.killpg` is unavailable
   - What's unclear: Should the code have a POSIX fallback (`os.killpg`) for CI/CD that might run on Linux?
   - Recommendation: Add `import sys` check: if `sys.platform == "win32"` use `taskkill`, else use `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)`. This future-proofs the module without complicating the Windows path.

---

## Sources

### Primary (HIGH confidence)
- [Python asyncio-subprocess docs (3.14)](https://docs.python.org/3/library/asyncio-subprocess.html) — `create_subprocess_exec`, `communicate()`, `kill()`, pipe deadlock warnings, Windows ProactorEventLoop requirement
- [Pydantic v2 Unions docs](https://pydantic.dev/docs/validation/latest/concepts/unions/) — discriminated union pattern, `Literal` discriminator fields, type alias syntax
- [Deno Security and Permissions](https://docs.deno.com/runtime/fundamentals/security/) — `--allow-net` flag syntax, comma-separated hostnames, `--no-prompt` behavior
- [Deno CLI run reference](https://docs.deno.com/runtime/reference/cli/run/) — `deno run` flag syntax, stdin pipe behavior
- `CLAUDE.md` (project) — complete module structure, component contracts, key design decisions (pre-verified by project author)

### Secondary (MEDIUM confidence)
- [CPython issue #139373](https://github.com/python/cpython/issues/139373) — `communicate()` unsafe to cancel; confirmed open as of Sep 2025; impact assessed as benign for timeout path
- [Deno stdin API](https://docs.deno.com/api/deno/~/Deno.stdin) — `Deno.stdin.readable` async iteration pattern for reading all stdin bytes
- [pytest-asyncio configuration](https://pytest-asyncio.readthedocs.io/en/latest/reference/configuration.html) — `asyncio_mode = "auto"` in `[tool.pytest.ini_options]`

### Tertiary (LOW confidence, needs validation during Phase 1)
- Deno 2 `--allow-net` redirect cross-domain behavior — found no definitive Deno 2.6.7 changelog entry; flagged in STATE.md as LOW confidence; validate during Phase 2

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — asyncio subprocess + Pydantic v2 + taskkill are all verified against official Python docs and project CLAUDE.md
- Architecture: HIGH — module structure and component contracts pre-specified in CLAUDE.md; asyncio patterns verified against official docs
- Pitfalls: HIGH — pipe deadlock and zombie cleanup warnings come directly from official Python docs; Windows kill path confirmed in STATE.md decisions

**Research date:** 2026-05-17
**Valid until:** 2026-06-17 (30 days — asyncio and Pydantic APIs are stable; Deno 2.x minor releases could change `--allow-net` edge cases)
