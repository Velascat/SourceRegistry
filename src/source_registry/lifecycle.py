"""Source lifecycle: bump / rebase / sync / auto-sync.

These operate on the local clone resolved from ``SourceEntry.local_path``
(or ``local_clone_hint`` fallback) and update the registry's pinned
``expected_sha`` accordingly. Each operation returns a structured result
so the CLI can surface what happened.

Auto-sync silently applies safe reconcile actions:
- DROP_PATCH after upstream merge → caller drops the patch yaml
- Zero local patches + upstream HEAD changed → reset, push, bump, reinstall

Unsafe paths (rebase conflicts, PR creation) abort with a finding
instead of corrupting the source. Auto-sync never opens upstream PRs;
PR creation stays opt-in via ``push``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import yaml

from source_registry.contracts.install_kind import InstallKind, InstallMode
from source_registry.contracts.source_entry import SourceEntry
from source_registry.errors import SourceRegistryError
from source_registry.git import git_ops


class LifecycleError(SourceRegistryError):
    """Raised when a lifecycle operation hits a non-recoverable condition."""


# ── Result types ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BumpResult:
    name: str
    old_sha: str
    new_sha: str
    patches_at_risk: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RebaseResult:
    name: str
    upstream_remote: str
    upstream_ref: str
    rebase_ok: bool
    rebase_output: str
    patch_status: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SyncResult:
    name: str
    rebase: RebaseResult
    bump: Optional[BumpResult] = None
    install_ok: bool = False


@dataclass
class AutoSyncResult:
    """Outcome of one auto-sync pass on a single source."""
    name: str
    upstream_changed: bool = False
    actions_taken: list[str] = field(default_factory=list)
    actions_blocked: list[str] = field(default_factory=list)
    final_state: str = "no_op"   # "synced" | "blocked" | "no_op"

    @property
    def ok(self) -> bool:
        return not self.actions_blocked


# ── Bump ────────────────────────────────────────────────────────────────


def bump_source(
    entry: SourceEntry,
    *,
    to_sha: Optional[str] = None,
    on_pin_update: Optional[Callable[[str, str], None]] = None,
    patch_touched_files: Optional[Callable[[], dict[str, list[str]]]] = None,
) -> BumpResult:
    """Pin the registry to the source's current HEAD (or a specified SHA).

    The caller is responsible for persisting the new pin via
    ``on_pin_update(name, new_sha)``. SR doesn't write registry yamls
    itself — the canonical yaml lives in the consumer (e.g. OC).

    ``patch_touched_files`` (optional) returns ``{patch_id: [files]}``
    so we can flag patches whose touched_files are missing at the new SHA.
    """
    clone = Path(entry.local_path)
    if not clone.exists():
        raise LifecycleError(
            f"{entry.name}: cannot bump — local_path {clone} does not exist"
        )
    if not git_ops.is_clean(clone):
        raise LifecycleError(
            f"{entry.name}: clone at {clone} has uncommitted changes; "
            "commit or stash before bumping."
        )

    new_sha = to_sha or git_ops.head_sha(clone)[:7]
    old_sha = entry.expected_sha

    at_risk: list[str] = []
    if patch_touched_files is not None:
        for patch_id, files in patch_touched_files().items():
            for f in files:
                if not (clone / f).exists():
                    at_risk.append(patch_id)
                    break

    if on_pin_update is not None:
        on_pin_update(entry.name, new_sha)

    return BumpResult(name=entry.name, old_sha=old_sha, new_sha=new_sha,
                      patches_at_risk=at_risk)


# ── Rebase ──────────────────────────────────────────────────────────────


def rebase_source(
    entry: SourceEntry,
    *,
    upstream_remote: str = "upstream",
    upstream_ref: Optional[str] = None,
    patch_touched_files: Optional[Callable[[], dict[str, list[str]]]] = None,
) -> RebaseResult:
    """git fetch upstream, git rebase upstream/<branch>.

    Per-patch report: for each patch's touched_files, did the rebase
    leave them present and conflict-free?
    """
    clone = Path(entry.local_path)
    if not clone.exists():
        raise LifecycleError(f"{entry.name}: cannot rebase — local_path {clone} missing")
    if not git_ops.is_clean(clone):
        raise LifecycleError(
            f"{entry.name}: clone at {clone} has uncommitted changes; "
            "commit or stash before rebasing."
        )

    target = upstream_ref or f"{upstream_remote}/{entry.branch}"

    fetch = git_ops.fetch_upstream(clone, remote=upstream_remote)
    if not fetch.ok:
        return RebaseResult(
            name=entry.name, upstream_remote=upstream_remote, upstream_ref=target,
            rebase_ok=False,
            rebase_output=f"fetch failed: {fetch.stderr.strip()}",
        )

    rebase = git_ops.rebase_onto(clone, target)
    output = (rebase.stdout + "\n" + rebase.stderr).strip()

    patch_status: dict[str, str] = {}
    if patch_touched_files is not None:
        for patch_id, files in patch_touched_files().items():
            missing = [f for f in files if not (clone / f).exists()]
            patch_status[patch_id] = (
                f"missing_files:{missing}" if missing else "files_present"
            )

    return RebaseResult(
        name=entry.name, upstream_remote=upstream_remote, upstream_ref=target,
        rebase_ok=rebase.ok, rebase_output=output, patch_status=patch_status,
    )


# ── Sync ────────────────────────────────────────────────────────────────


def sync_source(
    entry: SourceEntry,
    *,
    mode: InstallMode = InstallMode.DEV,
    install_runner: Optional[Callable[[SourceEntry, InstallMode], bool]] = None,
    on_pin_update: Optional[Callable[[str, str], None]] = None,
) -> SyncResult:
    """rebase + bump + reinstall, in that order. Stops at first failure.

    ``install_runner`` is supplied by the caller; it accepts (entry, mode)
    and returns True on success. SR doesn't shell out to ``uv`` itself.
    """
    rebase = rebase_source(entry)
    if not rebase.rebase_ok:
        return SyncResult(name=entry.name, rebase=rebase)

    bump = bump_source(entry, on_pin_update=on_pin_update)

    install_ok = True
    if install_runner is not None:
        install_ok = install_runner(entry, mode)

    return SyncResult(name=entry.name, rebase=rebase, bump=bump, install_ok=install_ok)


# ── Auto-sync ───────────────────────────────────────────────────────────


def auto_sync_source(
    entry: SourceEntry,
    *,
    mode: InstallMode = InstallMode.DEV,
    dry_run: bool = False,
    has_local_patches: Optional[Callable[[str], bool]] = None,
    install_runner: Optional[Callable[[SourceEntry, InstallMode], bool]] = None,
    on_pin_update: Optional[Callable[[str, str], None]] = None,
) -> AutoSyncResult:
    """Silently apply safe reconcile actions for one source.

    Refuses to run when ``entry.auto_sync`` is False.

    Safe auto-actions:
      - Zero local patches + upstream HEAD changed → reset dev to upstream,
        force-push, bump, reinstall

    Blocked actions (emit finding, do nothing):
      - Local patches present + upstream changed → caller must rebase
      - Push failure (e.g. no creds) → reported, not retried
      - PUSH_PATCH (open upstream PR) → never auto-runs

    Patch-aware actions (DROP_PATCH after upstream merge) are driven
    by the caller's poll output, not by auto_sync directly. The caller
    drops the patch yaml + transitions gap status before calling
    auto_sync — at which point ``has_local_patches`` returns False
    and the reset path runs.
    """
    result = AutoSyncResult(name=entry.name)

    if not entry.auto_sync:
        result.actions_blocked.append(f"auto_sync disabled for {entry.name}")
        result.final_state = "blocked"
        return result

    clone = Path(entry.local_path)
    if not clone.exists():
        result.actions_blocked.append(
            f"{entry.name}: local_path {clone} missing"
        )
        result.final_state = "blocked"
        return result

    fetch = git_ops.fetch_upstream(clone, remote="upstream")
    if not fetch.ok:
        result.actions_blocked.append(
            f"{entry.name}: fetch upstream failed: {fetch.stderr.strip()[:120]}"
        )
        result.final_state = "blocked"
        return result

    upstream_head = git_ops.head_sha_at_ref(clone, f"upstream/{entry.branch}")
    if upstream_head is None:
        result.actions_blocked.append(
            f"{entry.name}: cannot resolve upstream/{entry.branch}"
        )
        result.final_state = "blocked"
        return result

    if not entry.expected_sha.startswith(upstream_head[:7]):
        result.upstream_changed = True

    has_patches = has_local_patches(entry.name) if has_local_patches else False
    if has_patches:
        # Caller must rebase manually; auto-sync stays no-op
        result.final_state = "no_op"
        return result

    if not result.upstream_changed:
        result.final_state = "no_op"
        return result

    if dry_run:
        result.actions_taken.append(
            f"<dry-run> would reset {entry.branch} to {upstream_head[:7]} + bump + reinstall"
        )
        result.final_state = "synced"
        return result

    co = git_ops.checkout(clone, entry.branch)
    if not co.ok:
        result.actions_blocked.append(
            f"{entry.name}: checkout {entry.branch} failed: {co.stderr.strip()[:120]}"
        )
        result.final_state = "blocked"
        return result

    rh = git_ops.reset_hard(clone, f"upstream/{entry.branch}")
    if not rh.ok:
        result.actions_blocked.append(
            f"{entry.name}: reset failed: {rh.stderr.strip()[:120]}"
        )
        result.final_state = "blocked"
        return result
    result.actions_taken.append(
        f"reset {entry.branch} to upstream/{entry.branch} ({upstream_head[:7]})"
    )

    push = git_ops.force_push_with_lease(clone, "origin", entry.branch)
    if push.ok:
        result.actions_taken.append(f"pushed {entry.branch} to origin")
    else:
        result.actions_blocked.append(
            f"{entry.name}: push failed: {push.stderr.strip()[:160]}"
        )
        result.final_state = "blocked"
        return result

    bump = bump_source(entry, on_pin_update=on_pin_update)
    result.actions_taken.append(f"bumped pin: {bump.old_sha} → {bump.new_sha}")

    if install_runner is not None:
        if install_runner(entry, mode):
            result.actions_taken.append(f"reinstalled (mode={mode.value})")
        else:
            result.actions_blocked.append(f"{entry.name}: reinstall failed")
            result.final_state = "blocked"
            return result

    result.final_state = "synced"
    return result


def auto_sync_all(
    entries: list[SourceEntry],
    *,
    mode: InstallMode = InstallMode.DEV,
    dry_run: bool = False,
    has_local_patches: Optional[Callable[[str], bool]] = None,
    install_runner: Optional[Callable[[SourceEntry, InstallMode], bool]] = None,
    on_pin_update: Optional[Callable[[str, str], None]] = None,
) -> list[AutoSyncResult]:
    """Run auto-sync for every entry."""
    return [
        auto_sync_source(
            e, mode=mode, dry_run=dry_run,
            has_local_patches=has_local_patches,
            install_runner=install_runner,
            on_pin_update=on_pin_update,
        )
        for e in entries
    ]
