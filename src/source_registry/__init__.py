"""SourceRegistry — source and fork tracking for external tool repos.

Public API. Consumers should import only from this module.
"""
from source_registry.contracts.install_kind import InstallKind, InstallMode
from source_registry.contracts.patch_record import PatchRecord
from source_registry.contracts.source_entry import SourceEntry
from source_registry.contracts.verification import VerificationResult
from source_registry.errors import (
    DuplicateSourceError,
    GitOperationError,
    RegistryLoadError,
    SourceNotFoundError,
    SourceRegistryError,
)
from source_registry.lifecycle import (
    AutoSyncResult,
    BumpResult,
    LifecycleError,
    RebaseResult,
    SyncResult,
    auto_sync_all,
    auto_sync_source,
    bump_source,
    rebase_source,
    sync_source,
)
from source_registry.patches import (
    PatchError,
    PatchRegistry,
    drop_patch,
    load_patches,
)
from source_registry.poll import (
    GhCliClient,
    PrSnapshot,
    ReconcileFinding,
    ReconcileSuggestion,
    UpstreamApiClient,
    UpstreamSnapshot,
    poll_all,
    poll_source,
    reconcile,
)
from source_registry.push import PushError, PushResult, push_patch
from source_registry.service import SourceRegistry
from source_registry.verify import verify_all, verify_source

__all__ = [
    "SourceRegistry",
    "SourceEntry",
    "InstallKind",
    "InstallMode",
    "VerificationResult",
    "PatchRecord",
    "BumpResult",
    "RebaseResult",
    "SyncResult",
    "AutoSyncResult",
    "LifecycleError",
    "bump_source",
    "rebase_source",
    "sync_source",
    "auto_sync_source",
    "auto_sync_all",
    "verify_source",
    "verify_all",
    "PatchRegistry",
    "load_patches",
    "drop_patch",
    "PatchError",
    "PrSnapshot",
    "UpstreamSnapshot",
    "ReconcileFinding",
    "ReconcileSuggestion",
    "UpstreamApiClient",
    "GhCliClient",
    "poll_source",
    "poll_all",
    "reconcile",
    "PushResult",
    "PushError",
    "push_patch",
    "SourceRegistryError",
    "SourceNotFoundError",
    "DuplicateSourceError",
    "GitOperationError",
    "RegistryLoadError",
]
