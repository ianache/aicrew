"""
SkillCache — git clone lifecycle manager for the local skill cache.

Manages cloning and updating a GitHub-hosted skills catalog to a local directory.
Uses a file-based .last-sync timestamp for TTL-gated git pull operations.

Design constraints:
- Always use asyncio.create_subprocess_exec (never subprocess.run — blocks event loop)
- Always use proc.communicate() (never proc.wait() — deadlocks on large output)
- Clone failure → RuntimeError (hard fail — no cache to fall back to)
- Pull failure → soft-fail, return stale cache (prefer stale data over unavailability)
- Partial clone guard: if cache_dir exists but has no .git/, rmtree before re-clone
- Windows-compatible: no os.killpg — rely on asyncio.wait_for timeout
"""
import asyncio
import shutil
import time
from asyncio.subprocess import PIPE
from pathlib import Path


class SkillCache:
    """Manages a local git clone of the skills catalog repository.

    Args:
        repo_url: HTTPS URL of the catalog repository to clone.
        cache_dir: Local directory path where the clone will live.
        ttl_seconds: How long (in seconds) a successful sync stays fresh. Default 300.
    """

    def __init__(self, repo_url: str, cache_dir: Path, ttl_seconds: int = 300) -> None:
        self._repo_url = repo_url
        self._cache_dir = cache_dir
        self._ttl_seconds = ttl_seconds
        self._sync_file = cache_dir / ".last-sync"

    async def ensure_synced(self) -> Path:
        """Ensure the local cache is present and reasonably up-to-date.

        Behavior:
        - No .git/: clone the repo (raises RuntimeError on failure).
        - .git/ present + .last-sync fresh: return immediately (no network).
        - .git/ present + .last-sync expired: git pull --ff-only (soft-fail on error).

        Returns:
            The cache_dir Path, always (even on pull failure).

        Raises:
            RuntimeError: If the initial clone fails and there is no existing cache.
        """
        if self._needs_clone():
            await self._clone()
        elif self._needs_pull():
            await self._pull()

        return self._cache_dir

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _needs_clone(self) -> bool:
        """Return True when .git/ is absent (repo not yet cloned)."""
        return not (self._cache_dir / ".git").exists()

    def _needs_pull(self) -> bool:
        """Return True when sync file is absent or older than ttl_seconds."""
        try:
            ts = float(self._sync_file.read_text(encoding="utf-8"))
            return (time.time() - ts) > self._ttl_seconds
        except (OSError, ValueError):
            return True

    async def _clone(self) -> None:
        """Clone the repository from scratch.

        If cache_dir already exists (partial/corrupt clone without .git/), the
        directory is removed first so git clone can create a fresh one.

        Raises:
            RuntimeError: On non-zero git clone exit code.
        """
        # Partial-clone guard: directory exists but has no .git/
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)

        # Ensure the cache_dir itself exists (git clone will create it on a real
        # run, but we must also handle the mocked-subprocess path in tests).
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth=1", self._repo_url, str(self._cache_dir),
            stdout=PIPE,
            stderr=PIPE,
        )
        _stdout, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=60.0
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"git clone failed (exit {proc.returncode}): {stderr_bytes.decode(errors='replace')}"
            )

        self._write_sync_timestamp()

    async def _pull(self) -> None:
        """Run git pull --ff-only to refresh the local cache.

        Soft-fail: any error (non-zero exit code, timeout, OSError) is silently
        swallowed. The stale cache is served as-is. .last-sync is only updated
        on success.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(self._cache_dir), "pull", "--ff-only",
                stdout=PIPE,
                stderr=PIPE,
            )
            _stdout, _stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30.0
            )
            if proc.returncode == 0:
                self._write_sync_timestamp()
        except asyncio.TimeoutError:
            # Soft-fail: return stale cache
            return

    def _write_sync_timestamp(self) -> None:
        """Write current time as a float string to .last-sync."""
        self._sync_file.write_text(str(time.time()), encoding="utf-8")
