"""Source-state verification.

Routes by ``install_kind`` to the appropriate verifier. Returns a
``VerificationResult`` per source — never raises (callers expect to
get results back even for failures).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from source_registry.contracts.install_kind import InstallKind
from source_registry.contracts.source_entry import SourceEntry
from source_registry.contracts.verification import VerificationResult
from source_registry.git.git_ops import get_head_sha, is_git_repo


def verify_source(entry: SourceEntry) -> VerificationResult:
    """Verify one source against its registry pin."""
    path = Path(entry.local_path)

    if entry.install_kind in (InstallKind.NONE,):
        ok = path.exists()
        return VerificationResult(
            source_name=entry.name,
            ok=ok,
            install_kind=entry.install_kind,
            expected_sha=entry.expected_sha,
            actual_sha=None,
            local_path=entry.local_path,
            message="local_path exists" if ok else "local_path does not exist",
        )

    if entry.install_kind == InstallKind.EXTERNAL:
        return _verify_external(entry)

    if entry.install_kind in (InstallKind.CLI_TOOL, InstallKind.PYTHON_TOOL):
        return _verify_cli_tool(entry)

    return VerificationResult(
        source_name=entry.name,
        ok=False,
        install_kind=entry.install_kind,
        expected_sha=entry.expected_sha,
        actual_sha=None,
        local_path=entry.local_path,
        message=f"verification not implemented for install_kind={entry.install_kind.value!r}",
    )


def verify_all(entries: list[SourceEntry]) -> list[VerificationResult]:
    return [verify_source(e) for e in entries]


# ── External (git rev-parse) ────────────────────────────────────────────


def _verify_external(entry: SourceEntry) -> VerificationResult:
    path = Path(entry.local_path)
    if not path.exists():
        return VerificationResult(
            source_name=entry.name,
            ok=False,
            install_kind=entry.install_kind,
            expected_sha=entry.expected_sha,
            actual_sha=None,
            local_path=entry.local_path,
            message="local_path does not exist",
        )

    if not is_git_repo(entry.local_path):
        return VerificationResult(
            source_name=entry.name,
            ok=False,
            install_kind=entry.install_kind,
            expected_sha=entry.expected_sha,
            actual_sha=None,
            local_path=entry.local_path,
            message="local_path is not a git repository",
        )

    actual_sha = get_head_sha(entry.local_path)
    ok = actual_sha.startswith(entry.expected_sha) or entry.expected_sha.startswith(actual_sha)
    return VerificationResult(
        source_name=entry.name,
        ok=ok,
        install_kind=entry.install_kind,
        expected_sha=entry.expected_sha,
        actual_sha=actual_sha,
        local_path=entry.local_path,
        message="HEAD matches expected SHA" if ok else "HEAD does not match expected SHA",
    )


# ── cli_tool (uv tool / direct_url.json) ────────────────────────────────


def _uv_tool_dir() -> Path:
    """Best-effort: read uv tool directory. Falls back to default path."""
    try:
        proc = subprocess.run(
            ["uv", "tool", "dir"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return Path(proc.stdout.strip())
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return Path.home() / ".local" / "share" / "uv" / "tools"


def _read_direct_url(tool_name: str) -> Optional[dict]:
    base = _uv_tool_dir() / tool_name
    if not base.is_dir():
        return None
    site_packages_glob = list(base.glob("lib/python*/site-packages"))
    if not site_packages_glob:
        return None
    site_packages = site_packages_glob[0]
    dist_info_dirs = list(site_packages.glob(f"{tool_name.replace('-', '_')}-*.dist-info"))
    if not dist_info_dirs:
        dist_info_dirs = list(site_packages.glob(f"{tool_name}-*.dist-info"))
    if not dist_info_dirs:
        return None
    direct_url = dist_info_dirs[0] / "direct_url.json"
    if not direct_url.exists():
        return None
    try:
        return json.loads(direct_url.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _tool_name_for_entry(entry: SourceEntry) -> str:
    """Best-effort tool name guess from the fork URL.

    Assumes the package name matches the repo name. Override via
    ``metadata.tool_name`` for non-default cases.
    """
    if "tool_name" in entry.metadata:
        return entry.metadata["tool_name"]
    url = entry.fork_url or entry.upstream_url
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def _verify_cli_tool(entry: SourceEntry) -> VerificationResult:
    tool_name = _tool_name_for_entry(entry)
    metadata = _read_direct_url(tool_name)
    if metadata is None:
        return VerificationResult(
            source_name=entry.name,
            ok=False,
            install_kind=entry.install_kind,
            expected_sha=entry.expected_sha,
            actual_sha=None,
            local_path=entry.local_path,
            message=f"{tool_name} not installed via uv tool, or direct_url.json absent",
        )

    vcs_info = metadata.get("vcs_info") or {}
    actual_sha = vcs_info.get("commit_id") or vcs_info.get("requested_revision")

    if actual_sha is None:
        return VerificationResult(
            source_name=entry.name, ok=False,
            install_kind=entry.install_kind,
            expected_sha=entry.expected_sha,
            actual_sha=None,
            local_path=entry.local_path,
            message="direct_url.json present but vcs_info missing commit_id",
        )

    ok = actual_sha.startswith(entry.expected_sha) or entry.expected_sha.startswith(actual_sha)
    return VerificationResult(
        source_name=entry.name, ok=ok,
        install_kind=entry.install_kind,
        expected_sha=entry.expected_sha,
        actual_sha=actual_sha,
        local_path=entry.local_path,
        message="installed sha matches pin" if ok else "installed sha != pin",
    )
