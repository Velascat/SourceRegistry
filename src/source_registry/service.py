"""Public ``SourceRegistry`` facade.

Wraps the resolver, verifier, and lifecycle helpers behind a single
class. Consumers should depend only on this surface (and the typed
result classes) — never on the internal modules.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from source_registry.contracts.install_kind import InstallMode
from source_registry.contracts.source_entry import SourceEntry
from source_registry.contracts.verification import VerificationResult
from source_registry.lifecycle import (
    AutoSyncResult,
    BumpResult,
    RebaseResult,
    SyncResult,
    auto_sync_all,
    auto_sync_source,
    bump_source,
    rebase_source,
    sync_source,
)
from source_registry.registry.loader import load_sources
from source_registry.registry.resolver import SourceResolver
from source_registry.verify import verify_source


class SourceRegistry:
    def __init__(self, sources: list[SourceEntry]):
        self._sources = list(sources)
        self._resolver = SourceResolver(sources)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SourceRegistry":
        return cls(load_sources(str(path)))

    # ── Resolution ──────────────────────────────────────────────────────

    def resolve(self, name: str) -> SourceEntry:
        return self._resolver.resolve(name)

    def all(self) -> list[SourceEntry]:
        return list(self._sources)

    # ── Verify ──────────────────────────────────────────────────────────

    def verify(self, name: str) -> VerificationResult:
        return verify_source(self.resolve(name))

    def verify_all(self) -> list[VerificationResult]:
        return [verify_source(e) for e in self._sources]

    # ── Lifecycle ───────────────────────────────────────────────────────

    def bump(
        self,
        name: str,
        *,
        to_sha: Optional[str] = None,
        on_pin_update: Optional[Callable[[str, str], None]] = None,
    ) -> BumpResult:
        return bump_source(
            self.resolve(name), to_sha=to_sha, on_pin_update=on_pin_update,
        )

    def rebase(
        self,
        name: str,
        *,
        upstream_remote: str = "upstream",
    ) -> RebaseResult:
        return rebase_source(self.resolve(name), upstream_remote=upstream_remote)

    def sync(
        self,
        name: str,
        *,
        mode: InstallMode = InstallMode.DEV,
        install_runner: Optional[Callable[[SourceEntry, InstallMode], bool]] = None,
        on_pin_update: Optional[Callable[[str, str], None]] = None,
    ) -> SyncResult:
        return sync_source(
            self.resolve(name), mode=mode,
            install_runner=install_runner, on_pin_update=on_pin_update,
        )

    def auto_sync(
        self,
        name: str,
        *,
        mode: InstallMode = InstallMode.DEV,
        dry_run: bool = False,
        has_local_patches: Optional[Callable[[str], bool]] = None,
        install_runner: Optional[Callable[[SourceEntry, InstallMode], bool]] = None,
        on_pin_update: Optional[Callable[[str, str], None]] = None,
    ) -> AutoSyncResult:
        return auto_sync_source(
            self.resolve(name), mode=mode, dry_run=dry_run,
            has_local_patches=has_local_patches,
            install_runner=install_runner, on_pin_update=on_pin_update,
        )

    def auto_sync_all(
        self,
        *,
        mode: InstallMode = InstallMode.DEV,
        dry_run: bool = False,
        has_local_patches: Optional[Callable[[str], bool]] = None,
        install_runner: Optional[Callable[[SourceEntry, InstallMode], bool]] = None,
        on_pin_update: Optional[Callable[[str, str], None]] = None,
    ) -> list[AutoSyncResult]:
        return auto_sync_all(
            self._sources, mode=mode, dry_run=dry_run,
            has_local_patches=has_local_patches,
            install_runner=install_runner, on_pin_update=on_pin_update,
        )
