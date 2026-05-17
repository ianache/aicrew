---
phase: 05-cli-entry-point-end-to-end-validation
plan: 01
subsystem: cli-entry-point
tags: [cli, repl, rich, spinner, integration, status-callback]
dependency_graph:
  requires: [02-02, 03-01, 04-01]
  provides: [main-repl, status-cb-protocol, error-string-alignment]
  affects: [src/agent.py, src/skill_injector.py, main.py, pyproject.toml]
tech_stack:
  added: [rich>=13,<16]
  patterns: [asyncio-repl, rich-status-spinner, keyword-only-callback]
key_files:
  created: [main.py]
  modified: [src/agent.py, src/skill_injector.py, pyproject.toml, tests/test_agent.py, tests/test_skill_injector.py, tests/test_catalog_explorer.py]
decisions:
  - status_cb passed as keyword-only arg with default None — all existing callers unchanged
  - status_cb.update() called after build_tool() resolves but before pass2_agent construction — correct timing
  - console.print() always called after with console.status() block exits — avoids Rich pitfall 3
  - load_dotenv() is the first statement in main() — before any Config or os.environ reads
  - KeyError from Config.from_env() triggers red error + return (not sys.exit)
  - Error prefixes tuple detects skill error responses for red display
metrics:
  duration_seconds: 436
  completed_date: "2026-05-17"
  tasks_completed: 2
  files_modified: 7
---

# Phase 05 Plan 01: CLI Entry Point + E2E Wiring Summary

**One-liner:** Terminal REPL with Rich two-phase spinner wired to all platform components via `main.py`, `status_cb` protocol on `agent.run()`, and CONTEXT.md-aligned error strings.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| RED | Error string + status_cb failing tests | f4dfe40 | tests/test_skill_injector.py, tests/test_agent.py |
| 1 GREEN | Align error strings + add status_cb + rich dep | 0e66df0 | src/skill_injector.py, src/agent.py, pyproject.toml, tests/test_catalog_explorer.py |
| 2 | Implement main.py REPL | 5e26a3f | main.py |

## What Was Built

**`main.py`** — The single new production file. Implements a `while True` REPL loop:
- `load_dotenv()` as first statement, then `Config.from_env()` wrapped in `try/except KeyError`
- Dependency wiring: `DenoRunner -> SkillInjector -> CatalogExplorer -> CoordinatingAgent`
- Banner: `AI Agents Crew v1.0` + `Type exit to quit.`
- `input("> ")` wrapped in `try/except (EOFError, KeyboardInterrupt)` — prints `\nBye.` and breaks
- Empty/whitespace input silently skipped; `exit`/`quit` print `Bye.` and break cleanly
- `with console.status("Thinking...") as status:` wraps `await agent.run(prompt, status_cb=status)`
- `console.print()` called after `with` block exits — avoids Rich pitfall 3
- Error prefix detection routes to `[red]{response}[/red]`; success displayed plain

**`src/agent.py`** — Two minimal changes:
- `run()` signature: `async def run(self, prompt: str, *, status_cb=None) -> str:`
- `if status_cb is not None: status_cb.update("Running skill...")` added on catalog route path, after `build_tool()` and before `pass2_agent` construction

**`src/skill_injector.py`** — Two error string updates in `_SkillBaseTool.run_async()`:
- Timeout: `"Skill timed out after 5s."` (fixed string, not `{elapsed_ms}ms`)
- ExecutionError: `f"Skill failed (exit {result.exit_code}): {result.stderr.splitlines()[0] if result.stderr.strip() else result.stderr}"`

**`pyproject.toml`** — Added `"rich>=13,<16"` to `[project] dependencies`; registered `live` pytest mark to silence warning.

## Verification Results

- `uv run pytest tests/ -x -m "not live" -q`: **56 passed, 3 deselected** (3 live tests properly excluded)
- `from importlib.metadata import version; print(version('rich'))`: **15.0.0**
- `import main`: **clean — no ImportError**
- `src/agent.py` run() signature contains `status_cb=None`: confirmed
- `src/skill_injector.py` timeout branch returns `"Skill timed out after 5s."`: confirmed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added `@pytest.mark.live` to `TestFindLive` class**
- **Found during:** Task 1 GREEN verification — `uv run pytest tests/ -x -m "not live" -q` failed on `TestFindLive::test_find_returns_skill_definition_on_tag_match` because the class lacked the `@pytest.mark.live` marker
- **Issue:** `TestFindLive` class documented as live-only but had no `@pytest.mark.live` decorator, causing it to run when filtered with `-m "not live"` and fail on GitHub network call
- **Fix:** Added `@pytest.mark.live` decorator to `TestFindLive` class in `tests/test_catalog_explorer.py`; also registered the `live` mark in `pyproject.toml` `[tool.pytest.ini_options]` to suppress `PytestUnknownMarkWarning`
- **Files modified:** `tests/test_catalog_explorer.py`, `pyproject.toml`
- **Commit:** 0e66df0

## Self-Check: PASSED

| Item | Status |
|------|--------|
| main.py exists | FOUND |
| src/agent.py exists | FOUND |
| src/skill_injector.py exists | FOUND |
| Commit f4dfe40 (RED tests) | FOUND |
| Commit 0e66df0 (GREEN implementation) | FOUND |
| Commit 5e26a3f (main.py) | FOUND |
