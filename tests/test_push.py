"""Push safety-rail tests (the gh subprocess is intentionally not mocked;
we only test the refusal paths since those don't touch the network)."""
from __future__ import annotations

from pathlib import Path

import pytest

from source_registry import PushError, SourceEntry, push_patch
from source_registry.contracts.install_kind import InstallKind


def _entry(*, auto_pr_push: bool = True, local_path: str = "/tmp") -> SourceEntry:
    return SourceEntry(
        name="kodo",
        upstream_url="https://github.com/ikamensh/kodo",
        fork_url="https://github.com/Velascat/kodo",
        local_path=local_path,
        branch="dev",
        expected_sha="abc1234",
        install_kind=InstallKind.CLI_TOOL,
        auto_pr_push=auto_pr_push,
    )


def _seed_patch(tmp_path: Path, *, push_enabled: bool = True,
                pushed: bool = False, fork_branch: str | None = "fix/x") -> Path:
    src_dir = tmp_path / "kodo"
    src_dir.mkdir(parents=True, exist_ok=True)
    yaml_text = (
        f"title: t\nstatus: pending_review\n"
        f"push_enabled: {str(push_enabled).lower()}\n"
        f"pushed: {str(pushed).lower()}\n"
    )
    if fork_branch:
        yaml_text += f"fork_branch: {fork_branch}\n"
    (src_dir / "PATCH-001.yaml").write_text(yaml_text, encoding="utf-8")
    return tmp_path


class TestSafetyRails:
    def test_refuses_when_id_format_wrong(self, tmp_path):
        with pytest.raises(PushError, match="<source>:<PATCH"):
            push_patch("no-colon", _entry(), patches_root=tmp_path)

    def test_refuses_when_source_mismatch(self, tmp_path):
        _seed_patch(tmp_path)
        with pytest.raises(PushError, match="doesn't match entry"):
            push_patch("other:PATCH-001", _entry(), patches_root=tmp_path)

    def test_refuses_when_patch_missing(self, tmp_path):
        with pytest.raises(PushError, match="not found"):
            push_patch("kodo:PATCH-999", _entry(), patches_root=tmp_path)

    def test_refuses_when_auto_pr_push_disabled(self, tmp_path):
        _seed_patch(tmp_path)
        with pytest.raises(PushError, match="auto_pr_push: false"):
            push_patch("kodo:PATCH-001", _entry(auto_pr_push=False), patches_root=tmp_path)

    def test_refuses_when_push_enabled_false(self, tmp_path):
        _seed_patch(tmp_path, push_enabled=False)
        with pytest.raises(PushError, match="push_enabled is false"):
            push_patch("kodo:PATCH-001", _entry(), patches_root=tmp_path)

    def test_refuses_when_already_pushed(self, tmp_path):
        _seed_patch(tmp_path, pushed=True)
        with pytest.raises(PushError, match="already pushed"):
            push_patch("kodo:PATCH-001", _entry(), patches_root=tmp_path)

    def test_refuses_when_fork_branch_missing(self, tmp_path):
        _seed_patch(tmp_path, fork_branch=None)
        with pytest.raises(PushError, match="fork_branch is required"):
            push_patch("kodo:PATCH-001", _entry(), patches_root=tmp_path)

    def test_refuses_when_local_path_missing(self, tmp_path):
        _seed_patch(tmp_path)
        with pytest.raises(PushError, match="does not exist"):
            push_patch(
                "kodo:PATCH-001",
                _entry(local_path="/tmp/definitely-does-not-exist-xyzzy"),
                patches_root=tmp_path,
            )


class TestDryRun:
    def test_dry_run_returns_planned_command(self, tmp_path):
        _seed_patch(tmp_path)
        result = push_patch(
            "kodo:PATCH-001", _entry(), patches_root=tmp_path, dry_run=True,
        )
        assert result.ok
        assert "git push" in result.detail
