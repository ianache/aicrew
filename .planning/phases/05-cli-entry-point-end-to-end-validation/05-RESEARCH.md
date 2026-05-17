# Phase 5: CLI Entry Point + End-to-End Validation — Research

**Researched:** 2026-05-17
**Domain:** Python CLI entry point, Rich terminal UI, asyncio REPL loop, E2E integration
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Session mode**
- REPL loop — program stays running and re-prompts after each response
- User exits via Ctrl+C or by typing `exit` (or `quit`) — both result in a clean shutdown
- Each prompt is fully independent — no session history or context carried between calls
- Empty or whitespace-only input is silently skipped — no error, cursor returns to `> `

**Progress indicator**
- Animated spinner with status text throughout all responses (even high-confidence direct answers)
- Two stages:
  1. `Thinking...` — shown during LLM routing (Pass 1 + Pass 2)
  2. `Running skill...` — shown when Deno execution is in progress
- Response is printed plain to stdout after spinner clears — no box, no label prefix
- Rich library used for spinner (already in requirements.txt)

**Error message format**
- All errors: plain one-liner in red via Rich — no tracebacks, no panels
- Timeout: `Skill timed out after 5s.`
- Validation failure: `Skill validation failed: missing fields: [x, y].` (uses ValidationCorrectionRequest field list)
- Execution error: `Skill failed (exit {N}): {first line of stderr}`
- Missing GEMINI_API_KEY at startup: `Error: GEMINI_API_KEY not set. Add it to .env or export it.` then exit — caught from Config.from_env() KeyError

**Startup & prompt experience**
- Short banner on startup: `AI Agents Crew v1.0\nType exit to quit.`
- Input prompt: `> ` (bare, no label)
- Response: printed directly with no `Agent:` prefix — blank line before response for visual separation
- Exit message: `Bye.` on clean exit (Ctrl+C or typing `exit`)

### Claude's Discretion
- Exact Rich spinner style (dots, braille, etc.)
- `asyncio.run()` vs `asyncio.get_event_loop()` for the run entry point
- Whether to use `python-dotenv` `load_dotenv()` placement (at top of `main.py` per CLAUDE.md)
- How to wire the two spinner-phase transitions into agent.run() output

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EXEC-03 | CLI shows a progress indicator during the Deno execution window so the user knows the skill is running | Rich `console.status()` with `status.update()` covers the two-phase spinner; research confirms `status.update()` works mid-context-manager while asyncio event loop is running |
| CLI-01 | User runs `python main.py` from terminal, enters a natural-language prompt, receives a result | REPL loop pattern: `asyncio.run(main())` at bottom of `main.py`, `while True` with `input("> ")`, `await agent.run(prompt)`, KeyboardInterrupt caught for clean exit |
| CLI-02 | End-to-end happy path verified with at least one real TypeScript skill from the GitHub catalog (`evaluar-test-case` or `especificar_user_story`) | Live catalog verified available; E2E test calls real agent with real Gemini API key — tests must hit live GitHub per project decision |
</phase_requirements>

---

## Summary

Phase 5 is the thinnest phase in the roadmap — all infrastructure (DenoRunner, SkillInjector, CoordinatingAgent, CatalogExplorer, Config) is fully implemented and tested. The only new file is `main.py`, which wires these existing components into a terminal REPL loop with a Rich animated spinner.

The key technical challenge is the two-phase spinner transition: `Thinking...` must change to `Running skill...` during the same `agent.run()` call. Since `agent.run()` is a single coroutine that returns a string, the cleanest solution is a **callback/status-reference approach** — pass a `Status` object into `agent.run()` or use a module-level status reference that the agent can call `status.update()` on. The alternative is to wrap `agent.run()` in a background task and manage the spinner from the outer loop, but this adds concurrency complexity not justified by the gain.

The E2E test (CLI-02) is a live integration test — the project has already established the pattern of hitting real GitHub URLs (see `tests/test_catalog_explorer.py` live fixtures). The same approach applies here: a real `GEMINI_API_KEY` is required, the test prompts the live agent, and the expected outcome is a non-empty response with `decision='catalog_route'` in the routing log.

Rich 15.0.0 (latest, April 2026) is the target version. It is **not currently installed** in the project venv — `rich` must be added to `pyproject.toml` dependencies and installed. `requirements.txt` lists it but the project does not use `requirements.txt` for the actual venv (which is managed by `pyproject.toml` + `uv`).

**Primary recommendation:** Add `rich>=13,<16` to `pyproject.toml`, pass a `Console` and live `Status` reference through `agent.run()` via an optional callback parameter, use `console.status()` context manager in the REPL loop with `status.update()` to transition phases.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `rich` | `>=13,<16` (latest: 15.0.0) | Animated spinner, colored error messages | Official terminal UI library for Python; already declared in requirements.txt; `Console.status()` is the canonical spinner API |
| `python-dotenv` | `>=1,<2` (already pinned) | `load_dotenv()` at entry point | Already in project; loads `.env` before `Config.from_env()` reads `os.environ` |
| `asyncio` (stdlib) | Python 3.13 stdlib | `asyncio.run()` entry point | Matches existing project pattern; no new dep |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `rich.console.Console` | same as above | Terminal output, `console.print()` with markup | All output — spinner, errors, response text, banner |
| `rich.console.Status` | same as above | Animated spinner context manager | Wrap `await agent.run()` call; `status.update()` to change message |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `console.status()` + `status.update()` | `rich.live.Live` | `Live` is designed for multi-line dynamic displays; overkill for a single-line spinner |
| Single spinner with `status.update()` | Two separate spinner context managers | Nesting spinners causes display conflicts; `status.update()` is the right API for phase transitions |
| `asyncio.run()` | `asyncio.get_event_loop().run_until_complete()` | `get_event_loop()` is deprecated in Python 3.10+; `asyncio.run()` is the standard since 3.7 |

**Installation (add to pyproject.toml):**
```bash
uv add "rich>=13,<16"
# or manually add to pyproject.toml [project] dependencies list
uv sync
```

---

## Architecture Patterns

### Recommended File Structure
```
main.py                  # NEW — entire Phase 5 deliverable
src/
├── agent.py             # EXISTING — add optional status_cb parameter to run()
├── config.py            # EXISTING — no changes
├── catalog_explorer.py  # EXISTING — no changes
├── skill_injector.py    # EXISTING — no changes
└── ...
tests/
└── test_e2e.py          # NEW — live E2E test for CLI-02
```

### Pattern 1: REPL Entry Point with Rich Spinner

**What:** `asyncio.run()` calls `async def main()`, which runs a `while True` REPL loop with `console.status()` wrapping each `await agent.run()` call.

**When to use:** All production CLI entry points in this project.

**Example:**
```python
# Source: project conventions (CLAUDE.md) + Rich docs
import asyncio
from dotenv import load_dotenv
from rich.console import Console

from src.config import Config
from src.agent import CoordinatingAgent
from src.catalog_explorer import CatalogExplorer
from src.skill_injector import SkillInjector
from src.execution.deno_runner import DenoRunner

console = Console()

async def main() -> None:
    # 1. Load env first — all os.environ reads happen after this
    load_dotenv()

    # 2. Fail fast if required keys missing
    try:
        config = Config.from_env()
    except KeyError:
        console.print("[red]Error: GEMINI_API_KEY not set. Add it to .env or export it.[/red]")
        return

    # 3. Wire dependencies
    runner = DenoRunner()
    injector = SkillInjector(runner)
    explorer = CatalogExplorer(config)
    agent = CoordinatingAgent(explorer, injector, config)

    # 4. Banner
    console.print("AI Agents Crew v1.0")
    console.print("Type exit to quit.")

    # 5. REPL loop
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nBye.")
            break

        if not prompt:
            continue
        if prompt.lower() in ("exit", "quit"):
            console.print("Bye.")
            break

        # 6. Two-phase spinner
        with console.status("Thinking...") as status:
            response = await agent.run(prompt, status_cb=status)

        # 7. Print response — blank line before for visual separation
        console.print("")
        console.print(response)

if __name__ == "__main__":
    asyncio.run(main())
```

### Pattern 2: Two-Phase Spinner via status_cb Parameter

**What:** `agent.run()` receives an optional `status_cb` argument (the live `Status` object). When the routing decision flips to `catalog_route` and Deno execution begins, the agent calls `status_cb.update("Running skill...")`.

**When to use:** When the spinner phase transition must happen inside the awaited coroutine.

**Example:**
```python
# In src/agent.py — add optional parameter
async def run(self, prompt: str, status_cb=None) -> str:
    # ... existing pass 1 code ...
    if confidence < self._config.confidence_threshold:
        skill_def = await self._catalog_explorer.find(tags)
        if skill_def is not None:
            if status_cb is not None:
                status_cb.update("Running skill...")
            # ... build tool and run pass 2 ...
```

**Why this pattern:**
- `Status` object is not async-aware but `status.update()` is safe to call from a coroutine running in the same event loop thread — Rich uses an internal `threading.RLock` and the update is a simple attribute assignment, not a blocking I/O operation.
- No callbacks, futures, or threading required.
- The `status_cb` parameter is `Optional[Any]` (duck-typed) — tests that do not use a spinner pass `None` and the existing behavior is unchanged.

### Pattern 3: Error Message Display

**What:** Catch typed result variants after `agent.run()` returns; print plain red one-liners.

**When to use:** The agent surfaces errors as return strings from `_SkillBaseTool.run_async()` — they are returned back to `agent.run()` as the final text. Parse and re-format at the CLI boundary.

**Important note:** The agent already wraps all execution errors into human-readable strings (see `SkillInjector._SkillBaseTool.run_async()`). The CLI does not receive typed `ExecutionError` objects — it receives strings. The error messages defined in CONTEXT.md need to be generated within the tool layer or mapped at the CLI layer via string parsing.

**Cleaner approach — format errors in the tool layer:**
```python
# In _SkillBaseTool.run_async() — already returns strings like:
# "Skill timed out after 5000ms"   → CLI formats as "Skill timed out after 5s."
# "Skill execution failed: <stderr>" → CLI formats as "Skill failed (exit N): <first line>"
```

Since the exact format specified in CONTEXT.md differs from what the tool currently returns, main.py should detect error patterns and reformat, OR the planner should decide to align the tool output to the CLI-specified format directly in the tool (cleaner separation).

**Recommended approach:** Update `_SkillBaseTool.run_async()` to emit the exact CONTEXT.md error strings, then `main.py` simply prints them in red without parsing.

```python
# In main.py — after response = await agent.run(prompt)
ERROR_PREFIXES = ("Skill timed out", "Skill failed", "Skill validation failed", "No matching skill")
is_error = any(response.startswith(p) for p in ERROR_PREFIXES)
if is_error:
    console.print(f"[red]{response}[/red]")
else:
    console.print(response)
```

### Anti-Patterns to Avoid

- **Calling `input()` inside an async coroutine without `loop.run_in_executor()`:** Standard `input()` blocks the event loop. For a single-user REPL where prompting and execution are strictly sequential (never concurrent), synchronous `input()` in the outer `while True` loop — outside of any `await` — is safe and the intended pattern. Do NOT use `aioconsole` or `loop.run_in_executor(input, ...)` — that adds complexity the CONTEXT.md does not request.
- **Nesting `console.status()` inside another `console.status()`:** Rich does not support nested status contexts; the inner one will break the outer display.
- **Creating a new `Console()` instance per loop iteration:** `Console` holds terminal state; create once and reuse for the full session.
- **Calling `asyncio.get_event_loop().run_until_complete()`:** Deprecated in Python 3.10+. Use `asyncio.run()`.
- **Catching `Exception` broadly in the REPL loop without re-raising `KeyboardInterrupt`:** `KeyboardInterrupt` is not a subclass of `Exception` in Python — `except Exception` will NOT catch Ctrl+C. Use `except KeyboardInterrupt` separately or `except (EOFError, KeyboardInterrupt)` at the `input()` call.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Animated terminal spinner | Custom cursor/escape-code loop | `rich.console.Console.status()` | Handles terminal capability detection, Windows compatibility, refresh rate, thread safety; already a project dep |
| Colored terminal output | ANSI escape codes manually | `rich.console.Console.print()` with markup | Rich handles NO_COLOR, Windows Console API, piped output detection |
| REPL input handling | Custom readline loop | Python stdlib `input()` | Sufficient for single-user sequential REPL; `input()` provides basic line editing on all platforms |

**Key insight:** This is a thin wiring phase. Every complex problem (subprocess management, schema validation, LLM routing) is already solved. The only new code is glue — resist the urge to add features.

---

## Common Pitfalls

### Pitfall 1: Rich Not in pyproject.toml
**What goes wrong:** `import rich` fails at runtime with `ModuleNotFoundError` despite being in `requirements.txt`.
**Why it happens:** The project venv is managed by `uv` using `pyproject.toml`. `requirements.txt` is the v2 reference file, not the active install manifest.
**How to avoid:** Add `rich>=13,<16` to the `[project] dependencies` list in `pyproject.toml` and run `uv sync`.
**Warning signs:** `uv run python -c "import rich"` fails.

### Pitfall 2: KeyboardInterrupt Not Caught at input()
**What goes wrong:** Pressing Ctrl+C during `input("> ")` raises `KeyboardInterrupt` and crashes with a traceback instead of printing `Bye.`.
**Why it happens:** `input()` raises `KeyboardInterrupt` on SIGINT; if only `try/except Exception` wraps the loop, it is not caught.
**How to avoid:** Wrap `input()` in `except (EOFError, KeyboardInterrupt)` and print `Bye.` before breaking.
**Warning signs:** Ctrl+C during prompt shows Python traceback.

### Pitfall 3: Spinner Not Stopping Before console.print()
**What goes wrong:** Response text appears overlapping or garbled with the spinner animation.
**Why it happens:** If `console.print()` is called while the `console.status()` context is still active, Rich may conflict.
**How to avoid:** Use the `with console.status(...) as status:` block correctly — `console.print()` must be called AFTER the `with` block exits. The `with` block must encompass the full `await agent.run()` call and nothing else.
**Warning signs:** Garbled output, duplicated lines, spinner character appearing in response text.

### Pitfall 4: status_cb Parameter Breaks Existing Tests
**What goes wrong:** Adding `status_cb` parameter to `agent.run()` causes existing mocked tests to fail if signature changes break mock expectations.
**Why it happens:** If the test patches `agent.run` and the real implementation changes signature, `AsyncMock` may produce unexpected results.
**How to avoid:** Add `status_cb=None` as a keyword-only argument with default `None`. All existing call sites (`await agent.run(prompt)`) continue working unchanged. Add `if status_cb is not None: status_cb.update(...)` guards.
**Warning signs:** Existing Phase 3 tests fail after adding status_cb.

### Pitfall 5: E2E Test Requires Live GEMINI_API_KEY
**What goes wrong:** E2E test fails with `KeyError: 'GEMINI_API_KEY'` in CI or on clean checkout.
**Why it happens:** The test exercises the full pipeline including Gemini API calls. `Config.from_env()` raises `KeyError` without the key.
**How to avoid:** Mark the E2E test with `@pytest.mark.live` (matching the existing catalog explorer pattern) and document that it requires `.env` with a real key. The test should load `.env` via `python-dotenv` in the fixture, same as `live_config` in `test_catalog_explorer.py`.
**Warning signs:** Test passes locally (`.env` present) but fails in CI.

### Pitfall 6: load_dotenv() Called After Config.from_env()
**What goes wrong:** `GEMINI_API_KEY not set` error even though `.env` has the key.
**Why it happens:** `Config.from_env()` reads `os.environ`; if `load_dotenv()` hasn't been called yet, the env vars are not populated.
**How to avoid:** Per CLAUDE.md: "`load_dotenv()` at entry point only" — call it as the FIRST statement in `main()`, before any `Config.from_env()` call.
**Warning signs:** Works when key is exported in shell but not when only in `.env`.

---

## Code Examples

### console.status() with update() — Verified API
```python
# Source: rich.readthedocs.io/en/stable/reference/status.html
from rich.console import Console

console = Console()

with console.status("Thinking...") as status:
    # ... LLM pass 1 + 2 ...
    status.update("Running skill...")
    # ... Deno execution ...

# After 'with' block: spinner is gone, safe to print
console.print("")
console.print(response_text)
```

### Rich Markup for Colored Error
```python
# Source: Rich docs - Console markup
console.print("[red]Skill timed out after 5s.[/red]")
console.print("[red]Error: GEMINI_API_KEY not set. Add it to .env or export it.[/red]")
```

### Clean REPL with KeyboardInterrupt Handling
```python
# Standard Python pattern — verified
while True:
    try:
        prompt = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print("\nBye.")
        break

    if not prompt:
        continue
    if prompt.lower() in ("exit", "quit"):
        console.print("Bye.")
        break
```

### asyncio.run() Entry Point — Standard Python Pattern
```python
# Source: Python 3.13 docs — asyncio.run is the standard since 3.7
if __name__ == "__main__":
    asyncio.run(main())
```

### agent.run() with Optional status_cb
```python
# Pattern for wiring the phase transition — add to agent.py
async def run(self, prompt: str, *, status_cb=None) -> str:
    # ... Pass 1 ...
    if confidence < self._config.confidence_threshold:
        skill_def = await self._catalog_explorer.find(tags)
        if skill_def is not None:
            if status_cb is not None:
                status_cb.update("Running skill...")
            # ... Pass 2 with injected tool ...
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.get_event_loop().run_until_complete()` | `asyncio.run()` | Python 3.10 (deprecated old) | Use `asyncio.run()` — cleaner, handles loop creation and cleanup |
| Manual ANSI codes for color | `rich.console.Console.print()` with markup | Rich 1.0+ | No manual ANSI; portable across Windows/Unix |
| `sys.exit()` after error | `return` from async `main()` | Project convention | `asyncio.run()` exits cleanly when `main()` returns |

**Note on Rich versioning:** Rich 15.0.0 was released 2026-04-12 (latest stable). The `Status` and `Console` APIs are stable and have not changed their public interface since Rich 10.x. Using `>=13,<16` as the version constraint is safe and future-proof for this project's lifetime.

---

## Open Questions

1. **Spinner phase transition: status_cb vs. module-level reference**
   - What we know: `status.update()` is synchronous and safe to call from within an async coroutine in the same thread. The `Status` object is obtained from `with console.status(...) as status:`.
   - What's unclear: Whether to thread `status_cb` through `agent.run()` (cleaner, testable) or use a module-level `_current_status` variable (simpler but impure).
   - Recommendation: Use `status_cb=None` keyword argument on `agent.run()`. It is the cleanest approach, backward-compatible, and matches the dependency-injection pattern already used throughout the codebase.

2. **Error string format: tool layer vs. CLI layer**
   - What we know: `_SkillBaseTool.run_async()` currently returns strings like `"Skill timed out after 5000ms"`. CONTEXT.md specifies `"Skill timed out after 5s."`.
   - What's unclear: Whether to update the tool layer to emit CONTEXT.md-exact strings, or parse/reformat in `main.py`.
   - Recommendation: Update `_SkillBaseTool.run_async()` in Phase 5 to emit the exact CONTEXT.md strings. This avoids fragile string parsing in `main.py` and keeps error formatting close to its source.

3. **E2E test prompt selection**
   - What we know: `evaluar-test-case` and `especificar_user_story` are the two candidate skills in the live catalog. The catalog uses description-word matching (no explicit tags field per 04-01 decision).
   - What's unclear: Which prompt reliably triggers a `catalog_route` decision vs. a `direct_answer` from Gemini.
   - Recommendation: Use a prompt that is clearly a domain-specific task, e.g., `"Evalúa este test case: cuando el usuario hace clic en login con credenciales válidas, el sistema debe redirigir al dashboard"`. This is unlikely to score high-confidence as a direct answer.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode = auto) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_e2e.py -x -m "not live"` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-03 | Spinner visible during Deno execution window | manual-only | Manual: observe terminal output during `python main.py` | N/A — visual |
| CLI-01 | `python main.py` starts REPL, accepts prompt, returns result | e2e/live | `uv run pytest tests/test_e2e.py::test_repl_run_single_prompt -x` | ❌ Wave 0 |
| CLI-02 | Full pipeline with real skill completes end-to-end | e2e/live | `uv run pytest tests/test_e2e.py::test_e2e_live_skill -x -m live` | ❌ Wave 0 |

**Note on EXEC-03:** The spinner being visible is a terminal UI property that cannot be asserted programmatically via pytest (pytest captures stdout, which hides Rich's live display). EXEC-03 is verified manually during CLI-01 or CLI-02 execution. If the implementation follows the research pattern, EXEC-03 is satisfied by construction.

### Sampling Rate
- **Per task commit:** `uv run pytest -x -m "not live"` (fast, skips live API calls)
- **Per wave merge:** `uv run pytest` (all tests including live — requires `.env` with real keys)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_e2e.py` — covers CLI-01 (smoke) and CLI-02 (live E2E)
- [ ] `rich>=13,<16` added to `pyproject.toml` `[project] dependencies`

---

## Sources

### Primary (HIGH confidence)
- Rich official docs `https://rich.readthedocs.io/en/stable/reference/status.html` — Status constructor, `update()`, `start()`, `stop()` signatures confirmed
- Rich PyPI `https://pypi.org/project/rich/` — version 15.0.0 (latest, released 2026-04-12), Python >=3.9 confirmed
- Project source code `src/agent.py`, `src/config.py`, `src/skill_injector.py`, `src/catalog_explorer.py`, `tests/conftest.py` — all read and analyzed directly
- Python docs — `asyncio.run()` standard since Python 3.7, preferred over `get_event_loop()`

### Secondary (MEDIUM confidence)
- Rich GitHub discussion #1401 `https://github.com/Textualize/rich/discussions/1401` — single Live instance pattern for asyncio, maintainer recommendation
- `sderev.com/notes/132/` — `status.update()` usage pattern with async error handling example
- `brianlinkletter.com` — `console.status()` context manager pattern confirmed

### Tertiary (LOW confidence)
- None — all critical claims are verified by official docs or source code

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Rich version and API verified against official docs; all other deps already in project
- Architecture: HIGH — based on direct code reading of all existing src modules; REPL pattern is stdlib-standard
- Pitfalls: HIGH — most pitfalls derived from code reading (rich not in pyproject.toml, KeyboardInterrupt handling) plus confirmed project decisions (load_dotenv ordering)

**Research date:** 2026-05-17
**Valid until:** 2026-06-17 (Rich API is stable; 30-day window)
