"""
Phase 1 test suite for DenoRunner.

All tests are async (asyncio_mode = auto in pyproject.toml — no @pytest.mark.asyncio needed).
Tests run against real Deno subprocesses — no mocks per project decision.

Fixture paths:
  ECHO_SKILL  — echoes JSON stdin back to stdout
  SLOW_SKILL  — sleeps 10s (timeout test target)
"""
import subprocess
import time
from pathlib import Path

import pytest

from src.execution.deno_runner import DenoRunner
from src.models.results import (
    ExecutionError,
    ExecutionSuccess,
    TimeoutError,
    ValidationFailure,
)

# Absolute paths to fixture skills
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "skills"
ECHO_SKILL = str(FIXTURE_DIR / "echo_skill.ts")
SLOW_SKILL = str(FIXTURE_DIR / "slow_skill.ts")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_deno_processes() -> int:
    """Return the number of deno.exe processes currently running (Windows)."""
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq deno.exe", "/NH"],
        capture_output=True,
        text=True,
    )
    lines = [
        line for line in result.stdout.splitlines() if "deno.exe" in line.lower()
    ]
    return len(lines)


# ---------------------------------------------------------------------------
# Test 1: Successful execution returns ExecutionSuccess with echoed data
# ---------------------------------------------------------------------------


async def test_success_returns_execution_success():
    runner = DenoRunner()
    result = await runner.execute(ECHO_SKILL, {"hello": "world"}, [])
    assert isinstance(result, ExecutionSuccess), f"Expected ExecutionSuccess, got {result}"
    assert result.data == {"hello": "world"}


# ---------------------------------------------------------------------------
# Test 2: Skill exceeding 5000ms returns TimeoutError
# ---------------------------------------------------------------------------


async def test_timeout_returns_timeout_error():
    runner = DenoRunner()
    result = await runner.execute(SLOW_SKILL, {}, [])
    assert isinstance(result, TimeoutError), f"Expected TimeoutError, got {result}"
    assert result.elapsed_ms >= 5000, (
        f"elapsed_ms={result.elapsed_ms} should be >= 5000"
    )


# ---------------------------------------------------------------------------
# Test 3: After timeout, no zombie deno.exe processes remain
# ---------------------------------------------------------------------------


async def test_timeout_no_zombie_processes():
    runner = DenoRunner()
    result = await runner.execute(SLOW_SKILL, {}, [])
    assert isinstance(result, TimeoutError)
    # Give OS a short moment to fully reap the process tree
    time.sleep(0.5)
    count = _count_deno_processes()
    assert count == 0, f"Expected 0 deno.exe processes after timeout, found {count}"


# ---------------------------------------------------------------------------
# Test 4: Invalid domain (IP address) returns ValidationFailure
# ---------------------------------------------------------------------------


async def test_invalid_domain_returns_validation_failure():
    runner = DenoRunner()
    result = await runner.execute(ECHO_SKILL, {}, ["192.168.1.1"])
    assert isinstance(result, ValidationFailure), f"Expected ValidationFailure, got {result}"
    assert result.invalid_domain == "192.168.1.1"


# ---------------------------------------------------------------------------
# Test 5: ValidationFailure returned immediately — no subprocess spawned
# ---------------------------------------------------------------------------


async def test_invalid_domain_no_subprocess_spawned():
    runner = DenoRunner()
    t0 = time.monotonic()
    result = await runner.execute(ECHO_SKILL, {}, ["192.168.1.1"])
    elapsed_ms = (time.monotonic() - t0) * 1000
    assert isinstance(result, ValidationFailure)
    assert elapsed_ms < 100, (
        f"ValidationFailure should be returned in < 100ms (no subprocess), "
        f"but took {elapsed_ms:.1f}ms"
    )


# ---------------------------------------------------------------------------
# Test 6: Non-zero exit returns ExecutionError with correct exit code
# ---------------------------------------------------------------------------


async def test_nonzero_exit_returns_execution_error(tmp_path):
    # Inline fixture: exits non-zero, prints nothing to stdout
    fail_skill = tmp_path / "fail_skill.ts"
    fail_skill.write_text("Deno.exit(1);\n")
    runner = DenoRunner()
    result = await runner.execute(str(fail_skill), {}, [])
    assert isinstance(result, ExecutionError), f"Expected ExecutionError, got {result}"
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Test 7: Non-JSON stdout returns ExecutionError with exit_code=0
# ---------------------------------------------------------------------------


async def test_invalid_json_stdout_returns_execution_error(tmp_path):
    # Inline fixture: writes non-JSON to stdout, exits 0
    bad_json_skill = tmp_path / "bad_json_skill.ts"
    bad_json_skill.write_text('console.log("not json");\n')
    runner = DenoRunner()
    result = await runner.execute(str(bad_json_skill), {}, [])
    assert isinstance(result, ExecutionError), f"Expected ExecutionError, got {result}"
    assert result.exit_code == 0
    assert "not valid JSON" in result.stderr


# ---------------------------------------------------------------------------
# Test 8: Wildcard domain rejected
# ---------------------------------------------------------------------------


async def test_wildcard_domain_rejected():
    runner = DenoRunner()
    result = await runner.execute(ECHO_SKILL, {}, ["*.example.com"])
    assert isinstance(result, ValidationFailure), f"Expected ValidationFailure, got {result}"


# ---------------------------------------------------------------------------
# Test 9: IP address domain rejected
# ---------------------------------------------------------------------------


async def test_ip_address_domain_rejected():
    runner = DenoRunner()
    result = await runner.execute(ECHO_SKILL, {}, ["192.168.0.1"])
    assert isinstance(result, ValidationFailure), f"Expected ValidationFailure, got {result}"


# ---------------------------------------------------------------------------
# Test 10: Valid hostname passes validation and executes successfully
# ---------------------------------------------------------------------------


async def test_valid_domain_passes_validation():
    runner = DenoRunner()
    # echo_skill.ts makes no network calls — --allow-net=github.com is accepted but unused
    result = await runner.execute(ECHO_SKILL, {"x": 1}, ["github.com"])
    assert isinstance(result, ExecutionSuccess), f"Expected ExecutionSuccess, got {result}"
