# SourceRegistry

`SourceRegistry` (SR) is the source and fork tracking layer for external tools and framework repos. It resolves named source dependencies to local paths, tracks expected SHAs and lifecycle state, and records local fork patches and upstream-sync intent.

## What this repo is

- **Registry** — declarative source entries (`upstream_url`, `fork_url`, `local_path`, `branch`, `expected_sha`, `install_kind`, `metadata`)
- **Verification** — confirm a local source is at the expected SHA across multiple install kinds
- **Lifecycle** — track per-source state (`active`, `archived`, …) without conflating with verification
- **Patches** — load patch records from `<patches_root>/<source>/PATCH-NNN.yaml`; record local fixes and their upstream-PR status
- **Poll** — surface reconciliation suggestions when expected_sha drifts from local HEAD
- **Push** — describe upstream-push intent for fork branches
- **CLI** — `source-registry verify | list | patches | poll`

## What this repo is not

- OperationsCenter — orchestration, planning, policy
- SwitchBoard — lane/backend selection
- CoreRunner — runtime execution mechanics
- CxRP — orchestration contract
- RxP — runtime contract
- a scheduler / executor / subprocess runner
- a package manager replacement
- a fork synchronization daemon (SR records intent; the operator pushes)

## Quick start

```bash
pip install -e .
```

Verify a local source against its declared SHA:

```bash
source-registry --registry registry/source_registry.yaml verify <source_id>
source-registry --registry registry/source_registry.yaml list
source-registry --registry registry/source_registry.yaml poll
```

## Architecture

A YAML registry (`registry/source_registry.yaml`) declares each source dependency: upstream URL, fork URL, local path, expected SHA, `install_kind`, and lifecycle state. Five surfaces sit on top — verification (SHA-based), lifecycle tracking, patch records (`<patches_root>/<source>/PATCH-NNN.yaml`), poll-time reconciliation suggestions, and push-intent descriptors. The CLI (`source-registry verify | list | patches | poll`) is the single entry point. **Install kinds** below maps `install_kind` to its verification basis.

## Install kinds

| `install_kind` | Verification basis |
|---|---|
| `external` | Local clone — compares `git rev-parse HEAD` against `expected_sha` |
| `cli_tool` | Python CLI installed via `uv tool install` — reads `direct_url.json` from the tool's site-packages |
| `library` | Python library installed via pip (placeholder) |
| `binary` | Prebuilt binary (placeholder) |
| `none` | No verification beyond local-path existence |

`verify()` returns a structured `VerificationResult` (`ok`, `actual_sha`, `message`) regardless of kind.

## Example usage

```python
from source_registry import SourceRegistry
from source_registry.contracts.install_kind import InstallKind
from source_registry.contracts.source_entry import SourceEntry

registry = SourceRegistry(
    sources=[
        SourceEntry(
            name="archon",
            upstream_url="https://github.com/example/archon",
            fork_url="https://github.com/ProtocolWarden/archon",
            local_path="/repos/archon",
            branch="main",
            expected_sha="abc123",
            install_kind=InstallKind.EXTERNAL,
            metadata={"runtime": "bun", "language": "typescript"},
        )
    ]
)

entry = registry.resolve("archon")
result = registry.verify("archon")
print(entry.local_path, result.ok, result.actual_sha)
```

### Patches

```python
from source_registry.patches import load_patches

patches = load_patches("./patches")
for p in patches.for_source("archon"):
    print(p.patch_id, p.status, p.title)
```

### Poll (reconciliation)

```python
from source_registry.poll import poll_source

suggestion = poll_source(registry, "archon")
# ReconcileSuggestion.UP_TO_DATE | DRIFTED | UNREACHABLE
```

### CLI

```bash
source-registry list
source-registry verify archon
source-registry patches --source archon
source-registry poll archon
```

## Installation

```bash
pip install source-registry
```

Development:

```bash
git clone https://github.com/ProtocolWarden/SourceRegistry.git
cd SourceRegistry
pip install -e ".[dev]"
pytest -q
```

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
