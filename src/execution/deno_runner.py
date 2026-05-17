"""
DenoRunner — asyncio subprocess wrapper for executing Deno/TypeScript skills.

Design constraints (from CLAUDE.md):
- NEVER use proc.wait() — deadlocks when stdout > ~4KB pipe buffer.
- NEVER use asyncio.create_subprocess_shell — injection risk.
- NEVER raise exceptions for execution outcomes — always return typed result.
- Windows: use taskkill /F /T /PID (os.killpg is POSIX-only).
- Always pass --no-prompt as first Deno flag after `run`.
- The second await proc.communicate() after kill is mandatory — drains pipes,
  collects exit code, prevents zombie processes.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from asyncio.subprocess import PIPE
from typing import Union

from src.models.results import (
    ExecutionError,
    ExecutionResult,
    ExecutionSuccess,
    TimeoutError,
    ValidationFailure,
)

# Pre-compiled domain validation regex.
# Accepts hostnames like "github.com", "api.example.org".
# Rejects IPs (192.168.1.1), wildcards (*.example.com), bare labels (localhost).
_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Hard timeout in seconds — matches the 5000ms requirement from EXEC-01.
_TIMEOUT_SECONDS = 5.0


def _kill_process_tree(pid: int) -> None:
    """Kill a process and all its children.

    Uses platform-appropriate method:
    - Windows: taskkill /F /T /PID (terminates entire tree)
    - POSIX: os.killpg with SIGKILL
    """
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
        )
    else:
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass  # Process already gone


class DenoRunner:
    """Executes TypeScript skills via Deno subprocesses with timeout enforcement.

    All execution outcomes are returned as typed Pydantic result objects.
    This class never raises exceptions for execution outcomes.
    """

    async def execute(
        self,
        skill_path: str,
        params: dict,
        allow_net_domains: list[str],
        extra_flags: list[str] = [],
    ) -> ExecutionResult:
        """Execute a TypeScript skill file via Deno.

        Args:
            skill_path: Absolute or relative path to the .ts skill file.
            params: Dict passed to the skill as JSON on stdin.
            allow_net_domains: Validated hostnames for --allow-net flag.
                Empty list means no network access. IPs and wildcards are rejected.
            extra_flags: Additional Deno CLI flags (caller owns all permissions).

        Returns:
            ExecutionResult — one of:
                ExecutionSuccess: stdout parsed as JSON dict
                TimeoutError: execution exceeded 5000ms
                ExecutionError: non-zero exit or invalid JSON stdout
                ValidationFailure: domain failed regex before subprocess spawn
        """
        # Step 1: Validate all domains before spawning any subprocess.
        for domain in allow_net_domains:
            if not _DOMAIN_RE.fullmatch(domain):
                return ValidationFailure(invalid_domain=domain)

        # Step 2: Build --allow-net flag if domains were provided.
        cmd: list[str] = ["deno", "run", "--no-prompt"]
        if allow_net_domains:
            cmd.append(f"--allow-net={','.join(allow_net_domains)}")

        # Step 3: Append caller-supplied extra flags then the skill path.
        cmd.extend(extra_flags)
        cmd.append(skill_path)

        # Step 4: Encode params as JSON bytes for stdin.
        json_bytes = json.dumps(params).encode("utf-8")

        # Step 5: Spawn the subprocess (non-shell — no injection risk).
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
        )

        # Step 6: Record start time immediately after spawn.
        start = time.monotonic()

        # Step 7: Communicate with the process under the hard timeout.
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=json_bytes),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            # Step 8a: Compute elapsed time.
            elapsed_ms = int((time.monotonic() - start) * 1000)

            # Step 8b: Kill the entire process tree to prevent zombies.
            _kill_process_tree(proc.pid)

            # Step 8c: Drain pipes and collect exit code — prevents zombie.
            # Called without input since we've already closed stdin via the
            # initial communicate() attempt.
            try:
                await asyncio.wait_for(proc.communicate(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                # Best-effort drain; process tree was already killed.
                pass

            return TimeoutError(elapsed_ms=elapsed_ms)

        # Step 9: Non-zero exit → ExecutionError.
        if proc.returncode != 0:
            return ExecutionError(
                exit_code=proc.returncode,
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
            )

        # Step 10: Parse stdout as JSON; failure → ExecutionError with exit_code=0.
        stdout_text = stdout_bytes.decode("utf-8").strip()
        try:
            data = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            return ExecutionError(
                exit_code=0,
                stderr=f"stdout not valid JSON: {exc}",
            )

        # Step 11: Return success with the parsed data dict.
        return ExecutionSuccess(data=data)
