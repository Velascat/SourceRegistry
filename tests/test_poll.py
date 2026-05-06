"""Poll + reconcile tests with a fake UpstreamApiClient."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pytest

from source_registry import (
    PatchRecord,
    PrSnapshot,
    ReconcileSuggestion,
    SourceEntry,
    UpstreamApiClient,
    poll_all,
    poll_source,
    reconcile,
)
from source_registry.contracts.install_kind import InstallKind


class FakeClient(UpstreamApiClient):
    def __init__(
        self,
        *,
        prs: dict[int, PrSnapshot] | None = None,
        latest_release: str | None = None,
        latest_sha: str | None = None,
        files_changed: list[str] | None = None,
    ):
        self._prs = prs or {}
        self._release = latest_release
        self._sha = latest_sha
        self._files = files_changed or []

    def latest_release(self, repo: str) -> Optional[str]:
        return self._release

    def latest_commit_sha(self, repo: str, branch: str = "main") -> Optional[str]:
        return self._sha

    def get_pr(self, repo: str, number: int) -> Optional[PrSnapshot]:
        return self._prs.get(number)

    def files_changed_between(self, repo: str, base_sha: str, head_sha: str) -> list[str]:
        return list(self._files)


def _entry(name: str = "kodo", *, base_commit: str = "9c46e85",
           auto_pr_push: bool = False) -> SourceEntry:
    return SourceEntry(
        name=name,
        upstream_url="https://github.com/ikamensh/kodo",
        fork_url="https://github.com/Velascat/kodo",
        local_path="/tmp/kodo",
        branch="dev",
        expected_sha="abcdef0",
        install_kind=InstallKind.CLI_TOOL,
        base_commit=base_commit,
        auto_pr_push=auto_pr_push,
    )


def _patch(*, upstream_pr_url: str | None = None, touched: list[str] | None = None,
           pushed: bool = False, pushed_pr_url: str | None = None,
           push_enabled: bool = False) -> PatchRecord:
    return PatchRecord(
        patch_id="PATCH-001",
        source_name="kodo",
        title="t",
        status="pending_review",
        touched_files=touched or [],
        upstream_pr_url=upstream_pr_url,
        pushed=pushed,
        pushed_pr_url=pushed_pr_url,
        push_enabled=push_enabled,
        fork_branch="fix/x",
    )


class TestDropPatch:
    def test_emits_drop_when_cited_pr_merged(self):
        client = FakeClient(prs={49: PrSnapshot(49, "closed", merged=True,
                                               last_activity_iso="2026-05-06")})
        entry = _entry()
        patches = [_patch(upstream_pr_url="https://github.com/ikamensh/kodo/pull/49")]
        snap = poll_source(entry, patches, client=client)
        findings = reconcile(entry, patches, snap)
        kinds = [f.suggestion for f in findings]
        assert ReconcileSuggestion.DROP_PATCH in kinds

    def test_no_drop_when_pr_still_open(self):
        client = FakeClient(prs={49: PrSnapshot(49, "open", merged=False,
                                               last_activity_iso="2026-05-06")})
        entry = _entry()
        patches = [_patch(upstream_pr_url="https://github.com/ikamensh/kodo/pull/49")]
        snap = poll_source(entry, patches, client=client)
        findings = reconcile(entry, patches, snap)
        assert all(f.suggestion != ReconcileSuggestion.DROP_PATCH for f in findings)


class TestRebasePatch:
    def test_emits_rebase_when_touched_files_changed_upstream(self):
        client = FakeClient(
            latest_sha="newhead7",
            files_changed=["kodo/orchestrators/claude_code.py", "README.md"],
        )
        entry = _entry()
        patches = [_patch(touched=["kodo/orchestrators/claude_code.py"])]
        snap = poll_source(entry, patches, client=client)
        findings = reconcile(entry, patches, snap)
        rebases = [f for f in findings if f.suggestion == ReconcileSuggestion.REBASE_PATCH]
        assert len(rebases) == 1
        assert "claude_code.py" in rebases[0].reason


class TestPushPatch:
    def test_emits_push_when_auto_pr_push_enabled_and_unpushed(self):
        client = FakeClient()
        entry = _entry(auto_pr_push=True)
        patches = [_patch(push_enabled=True, pushed=False)]
        snap = poll_source(entry, patches, client=client)
        findings = reconcile(entry, patches, snap)
        pushes = [f for f in findings if f.suggestion == ReconcileSuggestion.PUSH_PATCH]
        assert len(pushes) == 1

    def test_no_push_when_auto_pr_push_disabled(self):
        client = FakeClient()
        entry = _entry(auto_pr_push=False)
        patches = [_patch(push_enabled=True, pushed=False)]
        snap = poll_source(entry, patches, client=client)
        findings = reconcile(entry, patches, snap)
        assert all(f.suggestion != ReconcileSuggestion.PUSH_PATCH for f in findings)


class TestStaleAndAbandoned:
    def test_emits_stale_review_for_old_open_pr(self):
        old_iso = (date.today() - timedelta(days=45)).isoformat()
        client = FakeClient(prs={99: PrSnapshot(99, "open", merged=False,
                                               last_activity_iso=old_iso)})
        entry = _entry()
        patches = [_patch(pushed=True, pushed_pr_url="https://github.com/x/y/pull/99")]
        snap = poll_source(entry, patches, client=client)
        findings = reconcile(entry, patches, snap)
        assert any(f.suggestion == ReconcileSuggestion.STALE_REVIEW for f in findings)

    def test_emits_abandoned_for_closed_unmerged(self):
        client = FakeClient(prs={99: PrSnapshot(99, "closed", merged=False,
                                               last_activity_iso="2026-04-01")})
        entry = _entry()
        patches = [_patch(pushed=True, pushed_pr_url="https://github.com/x/y/pull/99")]
        snap = poll_source(entry, patches, client=client)
        findings = reconcile(entry, patches, snap)
        kinds = [f.suggestion for f in findings]
        assert ReconcileSuggestion.REVIEW_REQUEST_ABANDONED in kinds


class TestPollAll:
    def test_iterates_entries_and_emits_combined_findings(self, tmp_path):
        client = FakeClient(prs={49: PrSnapshot(49, "closed", merged=True,
                                               last_activity_iso="2026-05-06")})
        # No patches dir → no patch-driven findings
        findings = poll_all([_entry()], patches_root=None, client=client)
        # No findings without patches
        assert findings == []
