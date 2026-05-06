"""Open an upstream PR for one patch.

Pushes the patch's fork branch to ``origin`` and runs ``gh pr create``
against upstream. After success, rewrites the patch yaml so subsequent
polls track the PR's review state.

Opt-in per source (``auto_pr_push: true``) and per patch
(``push_enabled: true``). Refuses with ``PushError`` otherwise.
"""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from source_registry.contracts.patch_record import PatchRecord
from source_registry.contracts.source_entry import SourceEntry
from source_registry.errors import SourceRegistryError
from source_registry.patches import load_patches


class PushError(SourceRegistryError):
    """Raised when push refuses or the underlying git/gh call fails."""


@dataclass(frozen=True)
class PushResult:
    source_name: str
    patch_id: str
    branch: str
    pr_url: Optional[str]
    pushed_branch: bool
    pr_created: bool
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.pushed_branch and self.pr_created


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _upstream_repo_id(entry: SourceEntry) -> str:
    url = entry.upstream_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    if "github.com/" in url:
        return url.split("github.com/", 1)[1].strip("/")
    return url


def _fork_owner(entry: SourceEntry) -> str:
    """Extract owner from fork_url for the gh --head argument."""
    url = (entry.fork_url or entry.upstream_url).rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    if "github.com/" in url:
        return url.split("github.com/", 1)[1].strip("/").split("/", 1)[0]
    return ""


def push_patch(
    full_id: str,
    entry: SourceEntry,
    *,
    patches_root: Path | str,
    dry_run: bool = False,
) -> PushResult:
    """Push one patch's branch and open an upstream PR.

    ``full_id`` is ``<source>:<PATCH-NNN>``. Caller supplies the
    ``SourceEntry`` (resolved from the registry) and the patches root.
    """
    if ":" not in full_id:
        raise PushError(f"patch id must be '<source>:<PATCH-NNN>' (got {full_id!r})")
    source_name, patch_id = full_id.split(":", 1)

    if source_name != entry.name:
        raise PushError(
            f"patch source {source_name!r} doesn't match entry {entry.name!r}"
        )

    patch_reg = load_patches(patches_root)
    patch = patch_reg.get(full_id)
    if patch is None:
        raise PushError(f"patch {full_id!r} not found under {patches_root}")

    # Safety rails
    if not entry.auto_pr_push:
        raise PushError(
            f"{entry.name}: registry has auto_pr_push: false — refusing to push"
        )
    if not patch.push_enabled:
        raise PushError(
            f"{full_id}: push_enabled is false — refusing to push"
        )
    if patch.pushed:
        raise PushError(
            f"{full_id}: already pushed (pushed_pr_url={patch.pushed_pr_url})"
        )
    if not patch.fork_branch:
        raise PushError(f"{full_id}: fork_branch is required for push")

    clone = Path(entry.local_path)
    if not clone.exists():
        raise PushError(f"{entry.name}: local_path {clone} does not exist")

    # Push the branch to origin
    push_cmd = ["git", "push", "-u", "origin", patch.fork_branch]
    if dry_run:
        return PushResult(
            source_name=entry.name, patch_id=patch.patch_id, branch=patch.fork_branch,
            pr_url=None, pushed_branch=True, pr_created=True,
            detail=f"<dry-run> would: {' '.join(shlex.quote(c) for c in push_cmd)}",
        )

    rc, _stdout, stderr = _run(push_cmd, cwd=clone)
    if rc != 0:
        return PushResult(
            source_name=entry.name, patch_id=patch.patch_id, branch=patch.fork_branch,
            pr_url=None, pushed_branch=False, pr_created=False,
            detail=f"git push failed: {stderr.strip()[:200]}",
        )

    # Open the upstream PR via gh
    pr_body = _build_pr_body(patch, entry.name)
    upstream_repo = _upstream_repo_id(entry)
    fork_owner = _fork_owner(entry)
    head_arg = f"{fork_owner}:{patch.fork_branch}" if fork_owner else patch.fork_branch
    pr_cmd = [
        "gh", "pr", "create",
        "--repo", upstream_repo,
        "--head", head_arg,
        "--base", entry.branch,
        "--title", patch.title,
        "--body", pr_body,
    ]
    rc, stdout, stderr = _run(pr_cmd, cwd=clone)
    if rc != 0:
        return PushResult(
            source_name=entry.name, patch_id=patch.patch_id, branch=patch.fork_branch,
            pr_url=None, pushed_branch=True, pr_created=False,
            detail=f"gh pr create failed: {stderr.strip()[:200]}",
        )

    pr_url = stdout.strip().splitlines()[-1] if stdout.strip() else None

    if pr_url and not dry_run:
        _record_push(patches_root, entry.name, patch.patch_id, pr_url)

    return PushResult(
        source_name=entry.name, patch_id=patch.patch_id, branch=patch.fork_branch,
        pr_url=pr_url, pushed_branch=True, pr_created=True,
    )


def _build_pr_body(patch: PatchRecord, source_name: str) -> str:
    parts = [patch.notes or patch.title]
    if patch.contract_gap_ref:
        parts.append("")
        parts.append(f"Closes contract gap **{patch.contract_gap_ref}**.")
    parts.extend([
        "",
        f"Auto-pushed via SourceRegistry (auto_pr_push) for `{source_name}:{patch.patch_id}`.",
    ])
    if patch.upstream_pr_url:
        parts.extend([
            "",
            f"Related upstream PR: {patch.upstream_pr_url}",
        ])
    return "\n".join(parts)


def _record_push(
    patches_root: Path | str, source_name: str, patch_id: str, pr_url: str,
) -> None:
    target = Path(patches_root) / source_name / f"{patch_id}.yaml"
    if not target.exists():
        return
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    raw["pushed"] = True
    raw["pushed_pr_url"] = pr_url
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
