# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
"""Git primitives for SourceRegistry.

Thin wrappers over ``git`` subprocesses. Returns structured ``GitResult``
for callers that want to surface stderr; raises ``GitOperationError``
only for the simple ``get_head_sha`` helper that's expected to succeed.
"""
import subprocess
from dataclasses import dataclass
from pathlib import Path

from source_registry.errors import GitOperationError


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _git(repo: str | Path, *args: str) -> GitResult:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
        timeout=60,
    )
    return GitResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def get_head_sha(local_path: str) -> str:
    result = _git(local_path, "rev-parse", "HEAD")
    if not result.ok:
        stderr = result.stderr.strip() or "unknown git error"
        raise GitOperationError(f"failed to read HEAD for '{local_path}': {stderr}")
    return result.stdout.strip()


def is_git_repo(local_path: str) -> bool:
    return _git(local_path, "rev-parse", "HEAD").ok


def head_sha(repo: str | Path) -> str:
    """Alias for ``get_head_sha`` accepting Path or str."""
    return get_head_sha(str(repo))


def head_sha_at_ref(repo: str | Path, ref: str) -> str | None:
    """Resolve ``ref`` to a SHA, or None if ``git rev-parse`` fails."""
    res = _git(repo, "rev-parse", ref)
    return res.stdout.strip() if res.ok else None


def fetch_upstream(repo: str | Path, *, remote: str = "upstream") -> GitResult:
    return _git(repo, "fetch", "--quiet", remote)


def rebase_onto(repo: str | Path, target_ref: str) -> GitResult:
    return _git(repo, "rebase", target_ref)


def reset_hard(repo: str | Path, ref: str) -> GitResult:
    return _git(repo, "reset", "--hard", ref)


def checkout(repo: str | Path, branch: str) -> GitResult:
    return _git(repo, "checkout", branch)


def force_push_with_lease(repo: str | Path, remote: str, branch: str) -> GitResult:
    return _git(repo, "push", "--force-with-lease", remote, branch)


def is_clean(repo: str | Path) -> bool:
    res = _git(repo, "status", "--porcelain")
    return res.ok and res.stdout.strip() == ""


def remote_url(repo: str | Path, remote: str) -> str | None:
    res = _git(repo, "remote", "get-url", remote)
    return res.stdout.strip() if res.ok else None


def list_files_changed_between(
    repo: str | Path, base_ref: str, head_ref: str,
) -> list[str]:
    res = _git(repo, "diff", "--name-only", f"{base_ref}..{head_ref}")
    if not res.ok:
        return []
    return [line for line in res.stdout.splitlines() if line.strip()]
