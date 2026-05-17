"""
TDD test suite for SkillCache — Phase 6, Plan 06-01.

Tests cover:
- First-call git clone (no .git/ present)
- TTL-based skip (fresh .last-sync)
- TTL-expired pull trigger
- Clone failure → RuntimeError
- Pull failure → stale cache (soft-fail)
- .last-sync written after clone
- .last-sync updated after pull
- Partial-clone guard (dir exists, .git absent → rmtree + re-clone)

All tests use mocked asyncio.create_subprocess_exec — no real git subprocess called.
asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio needed.
"""
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.skill_cache import SkillCache


REPO_URL = "https://github.com/ianache/skills-catalog"


def _make_mock_proc(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    """Build a fake asyncio subprocess process."""
    mock_proc = MagicMock()
    mock_proc.returncode = returncode
    mock_proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return mock_proc


# ---------------------------------------------------------------------------
# Clone tests
# ---------------------------------------------------------------------------

async def test_ensure_synced_clones_when_git_absent(tmp_path):
    """When .git/ is absent, ensure_synced() clones the repo and writes .last-sync."""
    cache_dir = tmp_path / ".skills-cache"
    cache = SkillCache(REPO_URL, cache_dir, ttl_seconds=300)

    mock_proc = _make_mock_proc(returncode=0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await cache.ensure_synced()

    assert result == cache_dir
    assert (cache_dir / ".last-sync").exists()


async def test_ensure_synced_raises_on_clone_failure(tmp_path):
    """When git clone returns non-zero exit code, RuntimeError is raised."""
    cache_dir = tmp_path / ".skills-cache"
    cache = SkillCache(REPO_URL, cache_dir, ttl_seconds=300)

    mock_proc = _make_mock_proc(returncode=1, stderr=b"fatal: repository not found")
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(RuntimeError):
            await cache.ensure_synced()


async def test_last_sync_written_after_clone(tmp_path):
    """After a successful clone, .last-sync contains a parseable float timestamp."""
    cache_dir = tmp_path / ".skills-cache"
    cache = SkillCache(REPO_URL, cache_dir, ttl_seconds=300)

    mock_proc = _make_mock_proc(returncode=0)
    before = time.time()
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        await cache.ensure_synced()
    after = time.time()

    sync_file = cache_dir / ".last-sync"
    assert sync_file.exists()
    ts = float(sync_file.read_text(encoding="utf-8"))
    assert before <= ts <= after


async def test_partial_clone_guard(tmp_path):
    """If cache_dir exists but has no .git/, rmtree is called before cloning."""
    cache_dir = tmp_path / ".skills-cache"
    # Create directory without .git/
    cache_dir.mkdir(parents=True)
    leftover = cache_dir / "stale_file.txt"
    leftover.write_text("leftover")

    cache = SkillCache(REPO_URL, cache_dir, ttl_seconds=300)

    mock_proc = _make_mock_proc(returncode=0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as mock_exec:
        result = await cache.ensure_synced()

    # clone subprocess must have been called
    mock_exec.assert_called_once()
    args = mock_exec.call_args[0]
    assert "clone" in args

    # stale file must be gone (rmtree ran before clone)
    assert not leftover.exists()
    assert result == cache_dir


# ---------------------------------------------------------------------------
# TTL / pull tests
# ---------------------------------------------------------------------------

async def test_ensure_synced_skips_clone_when_git_present_within_ttl(tmp_path):
    """When .git/ exists and .last-sync is fresh, no subprocess is spawned."""
    cache_dir = tmp_path / ".skills-cache"
    cache_dir.mkdir(parents=True)
    git_dir = cache_dir / ".git"
    git_dir.mkdir()
    sync_file = cache_dir / ".last-sync"
    sync_file.write_text(str(time.time()), encoding="utf-8")

    cache = SkillCache(REPO_URL, cache_dir, ttl_seconds=300)

    with patch("asyncio.create_subprocess_exec", AsyncMock()) as mock_exec:
        result = await cache.ensure_synced()

    mock_exec.assert_not_called()
    assert result == cache_dir


async def test_ensure_synced_pulls_when_ttl_expired(tmp_path):
    """When .git/ exists and .last-sync is expired, git pull subprocess is called."""
    cache_dir = tmp_path / ".skills-cache"
    cache_dir.mkdir(parents=True)
    git_dir = cache_dir / ".git"
    git_dir.mkdir()
    sync_file = cache_dir / ".last-sync"
    # Expired: 400 seconds ago, ttl=300
    sync_file.write_text(str(time.time() - 400), encoding="utf-8")

    cache = SkillCache(REPO_URL, cache_dir, ttl_seconds=300)

    mock_proc = _make_mock_proc(returncode=0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as mock_exec:
        result = await cache.ensure_synced()

    mock_exec.assert_called_once()
    args = mock_exec.call_args[0]
    assert "pull" in args
    assert result == cache_dir


async def test_pull_failure_uses_stale_cache(tmp_path):
    """When git pull fails, ensure_synced() returns cache_dir and does NOT update .last-sync."""
    cache_dir = tmp_path / ".skills-cache"
    cache_dir.mkdir(parents=True)
    git_dir = cache_dir / ".git"
    git_dir.mkdir()
    sync_file = cache_dir / ".last-sync"
    old_ts = str(time.time() - 400)
    sync_file.write_text(old_ts, encoding="utf-8")

    cache = SkillCache(REPO_URL, cache_dir, ttl_seconds=300)

    mock_proc = _make_mock_proc(returncode=1, stderr=b"pull failed")
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await cache.ensure_synced()

    # Returns cache_dir (soft-fail, not raising)
    assert result == cache_dir
    # .last-sync must NOT be updated (still contains the old timestamp)
    assert sync_file.read_text(encoding="utf-8") == old_ts


async def test_last_sync_written_after_pull(tmp_path):
    """After a successful pull, .last-sync is updated with a newer float timestamp."""
    cache_dir = tmp_path / ".skills-cache"
    cache_dir.mkdir(parents=True)
    git_dir = cache_dir / ".git"
    git_dir.mkdir()
    sync_file = cache_dir / ".last-sync"
    old_ts = time.time() - 400
    sync_file.write_text(str(old_ts), encoding="utf-8")

    cache = SkillCache(REPO_URL, cache_dir, ttl_seconds=300)

    mock_proc = _make_mock_proc(returncode=0)
    before = time.time()
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        await cache.ensure_synced()
    after = time.time()

    new_ts = float(sync_file.read_text(encoding="utf-8"))
    assert new_ts > old_ts
    assert before <= new_ts <= after
