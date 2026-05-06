"""Lifecycle tests — bump / rebase / sync / auto_sync.

Uses real local git repos in tmp_path so behavior matches production
without needing a remote. The "upstream" remote points at a sibling
local repo; "origin" can stay unset since no test pushes.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from source_registry import (
    AutoSyncResult,
    InstallMode,
    LifecycleError,
    SourceEntry,
    SourceRegistry,
    auto_sync_source,
    bump_source,
    rebase_source,
    sync_source,
)
from source_registry.contracts.install_kind import InstallKind


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout


def _init_repo(path: Path, *, files: dict[str, str] | None = None) -> str:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@test")
    _git(path, "config", "user.name", "test")
    files = files or {".keep": ""}
    for filename, content in files.items():
        target = path / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        _git(path, "add", filename)
    _git(path, "commit", "-q", "-m", "init")
    return _git(path, "rev-parse", "HEAD").strip()


def _setup_upstream_and_fork(tmp_path: Path) -> tuple[Path, Path, str]:
    """Build an upstream + a fork-clone tracking it on branch 'dev'."""
    upstream = tmp_path / "upstream"
    _init_repo(upstream, files={"file.py": "# upstream\n"})
    _git(upstream, "branch", "-m", "dev")

    clone = tmp_path / "fork"
    subprocess.run(["git", "clone", "-q", "-b", "dev", str(upstream), str(clone)], check=True)
    _git(clone, "config", "user.email", "t@t")
    _git(clone, "config", "user.name", "t")
    _git(clone, "remote", "add", "upstream", str(upstream))
    _git(clone, "fetch", "-q", "upstream")
    head = _git(clone, "rev-parse", "HEAD").strip()
    return upstream, clone, head


def _entry(name: str, clone: Path, sha: str, *, branch: str = "dev",
           kind: InstallKind = InstallKind.EXTERNAL,
           auto_sync: bool = True) -> SourceEntry:
    return SourceEntry(
        name=name,
        upstream_url="https://github.com/example/upstream",
        fork_url="https://github.com/example/fork",
        local_path=str(clone),
        branch=branch,
        expected_sha=sha,
        install_kind=kind,
        auto_sync=auto_sync,
    )


# ── Bump ────────────────────────────────────────────────────────────────


class TestBump:
    def test_bump_to_head(self, tmp_path):
        sha = _init_repo(tmp_path / "clone", files={"a.py": "1\n"})
        entry = _entry("s", tmp_path / "clone", sha[:7])
        # Add a commit so HEAD differs
        clone = tmp_path / "clone"
        (clone / "b.py").write_text("2\n", encoding="utf-8")
        _git(clone, "add", "b.py")
        _git(clone, "commit", "-q", "-m", "second")
        new = _git(clone, "rev-parse", "HEAD").strip()

        result = bump_source(entry)
        assert result.old_sha == sha[:7]
        assert result.new_sha == new[:7]

    def test_bump_calls_pin_update_callback(self, tmp_path):
        sha = _init_repo(tmp_path / "clone")
        entry = _entry("s", tmp_path / "clone", sha[:7])
        captured = []
        bump_source(entry, on_pin_update=lambda n, s: captured.append((n, s)))
        assert captured == [("s", sha[:7])]

    def test_bump_to_explicit_sha(self, tmp_path):
        sha = _init_repo(tmp_path / "clone")
        entry = _entry("s", tmp_path / "clone", sha[:7])
        result = bump_source(entry, to_sha="deadbee")
        assert result.new_sha == "deadbee"

    def test_bump_blocked_when_dirty(self, tmp_path):
        sha = _init_repo(tmp_path / "clone")
        clone = tmp_path / "clone"
        (clone / "x").write_text("dirty", encoding="utf-8")
        entry = _entry("s", clone, sha[:7])
        with pytest.raises(LifecycleError, match="uncommitted"):
            bump_source(entry)

    def test_bump_missing_clone_raises(self, tmp_path):
        entry = _entry("s", tmp_path / "absent", "abc1234")
        with pytest.raises(LifecycleError, match="does not exist"):
            bump_source(entry)


# ── Rebase ──────────────────────────────────────────────────────────────


class TestRebase:
    def test_rebase_no_op_against_unchanged_upstream(self, tmp_path):
        upstream, clone, head = _setup_upstream_and_fork(tmp_path)
        entry = _entry("s", clone, head[:7])
        result = rebase_source(entry)
        assert result.rebase_ok
        assert result.upstream_ref == "upstream/dev"


# ── Auto-sync ───────────────────────────────────────────────────────────


class TestAutoSync:
    def test_no_op_when_upstream_unchanged(self, tmp_path):
        upstream, clone, head = _setup_upstream_and_fork(tmp_path)
        entry = _entry("s", clone, head[:7])
        result = auto_sync_source(entry, dry_run=True)
        assert result.ok
        assert result.final_state == "no_op"

    def test_dry_run_pulls_when_upstream_changed(self, tmp_path):
        upstream, clone, head = _setup_upstream_and_fork(tmp_path)
        # Add upstream commit
        (upstream / "new.py").write_text("# new\n", encoding="utf-8")
        _git(upstream, "add", "new.py")
        _git(upstream, "commit", "-q", "-m", "upstream change")

        entry = _entry("s", clone, head[:7])
        result = auto_sync_source(entry, dry_run=True)
        assert result.ok
        assert result.final_state == "synced"
        assert result.upstream_changed
        assert any("would reset" in a for a in result.actions_taken)

    def test_disabled_flag_blocks(self, tmp_path):
        upstream, clone, head = _setup_upstream_and_fork(tmp_path)
        entry = _entry("s", clone, head[:7], auto_sync=False)
        result = auto_sync_source(entry, dry_run=True)
        assert not result.ok
        assert result.final_state == "blocked"
        assert any("auto_sync disabled" in b for b in result.actions_blocked)

    def test_blocks_when_local_path_missing(self, tmp_path):
        entry = _entry("s", tmp_path / "absent", "abc1234")
        result = auto_sync_source(entry, dry_run=True)
        assert not result.ok
        assert "missing" in result.actions_blocked[0]

    def test_local_patches_present_keeps_no_op(self, tmp_path):
        upstream, clone, head = _setup_upstream_and_fork(tmp_path)
        # Add an upstream change to make upstream_changed True
        (upstream / "u.py").write_text("u\n", encoding="utf-8")
        _git(upstream, "add", "u.py")
        _git(upstream, "commit", "-q", "-m", "u")

        entry = _entry("s", clone, head[:7])
        result = auto_sync_source(
            entry, dry_run=True,
            has_local_patches=lambda name: True,
        )
        # When patches exist auto-sync stays no_op (caller must rebase)
        assert result.ok
        assert result.final_state == "no_op"


# ── SourceRegistry facade ───────────────────────────────────────────────


class TestSourceRegistry:
    def test_facade_exposes_lifecycle(self, tmp_path):
        upstream, clone, head = _setup_upstream_and_fork(tmp_path)
        entry = _entry("s", clone, head[:7])
        reg = SourceRegistry([entry])
        result = reg.auto_sync("s", dry_run=True)
        assert isinstance(result, AutoSyncResult)
        assert result.final_state == "no_op"

    def test_auto_sync_all_iterates(self, tmp_path):
        u1, c1, h1 = _setup_upstream_and_fork(tmp_path / "a")
        # second source
        u2 = tmp_path / "b" / "upstream"
        c2 = tmp_path / "b" / "fork"
        u2.parent.mkdir(parents=True, exist_ok=True)
        _init_repo(u2, files={"f": "1\n"})
        _git(u2, "branch", "-m", "dev")
        subprocess.run(["git", "clone", "-q", "-b", "dev", str(u2), str(c2)], check=True)
        _git(c2, "remote", "add", "upstream", str(u2))
        _git(c2, "fetch", "-q", "upstream")
        h2 = _git(c2, "rev-parse", "HEAD").strip()

        reg = SourceRegistry([
            _entry("a", c1, h1[:7]),
            _entry("b", c2, h2[:7]),
        ])
        results = reg.auto_sync_all(dry_run=True)
        assert len(results) == 2
        assert all(r.ok and r.final_state == "no_op" for r in results)
