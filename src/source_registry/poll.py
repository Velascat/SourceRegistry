"""Upstream poll + reconcile suggestions.

Per registered source:
  - Read latest_release / latest_commit_sha from upstream
  - For each PATCH-NNN, check upstream PR status + recent commits
    touching ``touched_files``
  - Emit findings:
      DROP_PATCH               — upstream merged the equivalent fix
      REBASE_PATCH             — upstream changed our touched_files
      PUSH_PATCH               — auto_pr_push enabled but not pushed
      STALE_REVIEW             — pushed PR has no review activity for >30d
      REVIEW_REQUEST_ABANDONED — pushed PR closed without merge

The GitHub API client is pluggable (``UpstreamApiClient`` Protocol).
The default ``GhCliClient`` shells out to ``gh`` for unauth'd reads;
tests inject fakes.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol

from source_registry.contracts.patch_record import PatchRecord
from source_registry.contracts.source_entry import SourceEntry
from source_registry.patches import load_patches


_STALE_REVIEW_DAYS = 30


class ReconcileSuggestion(str, Enum):
    DROP_PATCH = "DROP_PATCH"
    REBASE_PATCH = "REBASE_PATCH"
    PUSH_PATCH = "PUSH_PATCH"
    STALE_REVIEW = "STALE_REVIEW"
    REVIEW_REQUEST_ABANDONED = "REVIEW_REQUEST_ABANDONED"


@dataclass(frozen=True)
class PrSnapshot:
    number: int
    state: str                          # open | closed
    merged: bool
    last_activity_iso: Optional[str]


@dataclass(frozen=True)
class UpstreamSnapshot:
    source_name: str
    upstream_repo: str
    latest_release: Optional[str] = None
    latest_commit_sha: Optional[str] = None
    cited_prs: dict[int, PrSnapshot] = field(default_factory=dict)
    pushed_prs: dict[str, PrSnapshot] = field(default_factory=dict)
    files_changed_since_base: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReconcileFinding:
    rule: str = "UPSTREAM_RECONCILE"
    patch_id: str = ""           # e.g. "kodo:PATCH-001" or "<source>:" for source-level
    suggestion: ReconcileSuggestion = ReconcileSuggestion.PUSH_PATCH
    reason: str = ""
    detected_at: str = ""
    action_link: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["suggestion"] = self.suggestion.value
        return d


# ── Pluggable API client ────────────────────────────────────────────────


class UpstreamApiClient(Protocol):
    def latest_release(self, repo: str) -> Optional[str]: ...
    def latest_commit_sha(self, repo: str, branch: str = "main") -> Optional[str]: ...
    def get_pr(self, repo: str, number: int) -> Optional[PrSnapshot]: ...
    def files_changed_between(self, repo: str, base_sha: str, head_sha: str) -> list[str]: ...


class GhCliClient:
    """Shells out to ``gh`` CLI. Returns None / [] on any failure
    (gh missing, network error, malformed json) — callers degrade gracefully.
    """

    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self._timeout = timeout_seconds

    def _gh_json(self, *args: str) -> Any:
        try:
            proc = subprocess.run(
                ["gh", *args], capture_output=True, text=True, timeout=self._timeout,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None

    def latest_release(self, repo: str) -> Optional[str]:
        data = self._gh_json("release", "view", "--repo", repo, "--json", "tagName")
        if isinstance(data, dict):
            tag = data.get("tagName")
            if isinstance(tag, str):
                return tag.lstrip("v")
        return None

    def latest_commit_sha(self, repo: str, branch: str = "main") -> Optional[str]:
        data = self._gh_json("api", f"repos/{repo}/commits/{branch}", "--jq", ".sha")
        if isinstance(data, str) and len(data) >= 7:
            return data
        return None

    def get_pr(self, repo: str, number: int) -> Optional[PrSnapshot]:
        data = self._gh_json(
            "pr", "view", str(number), "--repo", repo,
            "--json", "number,state,mergedAt,updatedAt",
        )
        if not isinstance(data, dict):
            return None
        merged_at = data.get("mergedAt")
        return PrSnapshot(
            number=int(data.get("number") or number),
            state=str(data.get("state") or "").lower(),
            merged=bool(merged_at),
            last_activity_iso=data.get("updatedAt") or merged_at,
        )

    def files_changed_between(self, repo: str, base_sha: str, head_sha: str) -> list[str]:
        data = self._gh_json(
            "api", f"repos/{repo}/compare/{base_sha}...{head_sha}",
            "--jq", "[.files[].filename]",
        )
        if isinstance(data, list):
            return [str(f) for f in data if isinstance(f, str)]
        return []


# ── Helpers ─────────────────────────────────────────────────────────────


def _extract_pr_number(url_or_number: str) -> Optional[int]:
    if url_or_number.isdigit():
        return int(url_or_number)
    if "/pull/" in url_or_number:
        tail = url_or_number.split("/pull/", 1)[1]
        digits = ""
        for ch in tail:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            return int(digits)
    return None


def _parse_iso_date(value: str) -> Optional[date]:
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _upstream_repo_id(entry: SourceEntry) -> str:
    """Best-effort owner/repo extraction from upstream_url."""
    url = entry.upstream_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    if "github.com/" in url:
        return url.split("github.com/", 1)[1].strip("/")
    return url


# ── Poll orchestration ──────────────────────────────────────────────────


def poll_source(
    entry: SourceEntry,
    patches: list[PatchRecord],
    *,
    client: UpstreamApiClient,
) -> UpstreamSnapshot:
    """Hit the upstream API and assemble a snapshot for one source."""
    repo = _upstream_repo_id(entry)

    cited_prs: dict[int, PrSnapshot] = {}
    pushed_prs: dict[str, PrSnapshot] = {}
    for p in patches:
        if p.upstream_pr_url:
            num = _extract_pr_number(p.upstream_pr_url)
            if num is not None and num not in cited_prs:
                snap = client.get_pr(repo, num)
                if snap is not None:
                    cited_prs[num] = snap
        if p.pushed and p.pushed_pr_url:
            num = _extract_pr_number(p.pushed_pr_url)
            if num is not None:
                snap = client.get_pr(repo, num)
                if snap is not None:
                    pushed_prs[p.patch_id] = snap

    files_changed: list[str] = []
    if entry.base_commit:
        upstream_head = client.latest_commit_sha(repo, entry.branch)
        if upstream_head and not upstream_head.startswith(entry.base_commit):
            files_changed = client.files_changed_between(
                repo, entry.base_commit, upstream_head,
            )

    return UpstreamSnapshot(
        source_name=entry.name,
        upstream_repo=repo,
        latest_release=client.latest_release(repo),
        latest_commit_sha=client.latest_commit_sha(repo, entry.branch),
        cited_prs=cited_prs,
        pushed_prs=pushed_prs,
        files_changed_since_base=files_changed,
    )


def reconcile(
    entry: SourceEntry,
    patches: list[PatchRecord],
    snapshot: UpstreamSnapshot,
    *,
    today: Optional[date] = None,
) -> list[ReconcileFinding]:
    today = today or date.today()
    detected = today.isoformat()
    out: list[ReconcileFinding] = []

    for p in patches:
        full_id = f"{entry.name}:{p.patch_id}"

        # 1. DROP_PATCH — upstream PR cited in upstream_pr_url merged
        if p.upstream_pr_url:
            num = _extract_pr_number(p.upstream_pr_url)
            if num is not None:
                snap = snapshot.cited_prs.get(num)
                if snap and snap.merged:
                    out.append(ReconcileFinding(
                        patch_id=full_id,
                        suggestion=ReconcileSuggestion.DROP_PATCH,
                        reason=(
                            f"upstream PR #{num} merged "
                            f"({snap.last_activity_iso or 'date unknown'})"
                        ),
                        detected_at=detected,
                        action_link=p.upstream_pr_url,
                    ))

        # 2. REBASE_PATCH — touched_files changed upstream
        if any(f in snapshot.files_changed_since_base for f in p.touched_files):
            overlapping = sorted(
                set(p.touched_files) & set(snapshot.files_changed_since_base)
            )
            out.append(ReconcileFinding(
                patch_id=full_id,
                suggestion=ReconcileSuggestion.REBASE_PATCH,
                reason=f"upstream changed touched files: {overlapping}",
                detected_at=detected,
            ))

        # 3. PUSH_PATCH — auto_pr_push enabled but unpushed
        if entry.auto_pr_push and p.push_enabled and not p.pushed:
            out.append(ReconcileFinding(
                patch_id=full_id,
                suggestion=ReconcileSuggestion.PUSH_PATCH,
                reason="auto_pr_push enabled but pushed_pr_url is unset",
                detected_at=detected,
            ))

        # 4. STALE_REVIEW / REVIEW_REQUEST_ABANDONED — for our pushed PRs
        pushed = snapshot.pushed_prs.get(p.patch_id)
        if pushed:
            if pushed.state == "closed" and not pushed.merged:
                out.append(ReconcileFinding(
                    patch_id=full_id,
                    suggestion=ReconcileSuggestion.REVIEW_REQUEST_ABANDONED,
                    reason="our pushed PR closed without merge",
                    detected_at=detected,
                    action_link=p.pushed_pr_url,
                ))
            elif pushed.state == "open" and pushed.last_activity_iso:
                last = _parse_iso_date(pushed.last_activity_iso)
                if last and (today - last) > timedelta(days=_STALE_REVIEW_DAYS):
                    out.append(ReconcileFinding(
                        patch_id=full_id,
                        suggestion=ReconcileSuggestion.STALE_REVIEW,
                        reason=(
                            f"our pushed PR has no activity since {last.isoformat()} "
                            f"(>{_STALE_REVIEW_DAYS} days)"
                        ),
                        detected_at=detected,
                        action_link=p.pushed_pr_url,
                    ))

    return out


def poll_all(
    entries: list[SourceEntry],
    *,
    patches_root: Path | str | None = None,
    client: Optional[UpstreamApiClient] = None,
    today: Optional[date] = None,
) -> list[ReconcileFinding]:
    """Run poll+reconcile for every entry. Returns flat list of findings."""
    api = client or GhCliClient()
    patch_reg = load_patches(patches_root) if patches_root else None

    findings: list[ReconcileFinding] = []
    for entry in entries:
        patches = patch_reg.for_source(entry.name) if patch_reg else []
        snapshot = poll_source(entry, patches, client=api)
        findings.extend(reconcile(entry, patches, snapshot, today=today))
    return findings
