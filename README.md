# SourceRegistry

## What this repo is

`SourceRegistry` is the source and fork tracking layer for external tools and framework repos. It resolves named source dependencies to local paths and verifies expected source state.

## What this repo is not

This repository is not:

- OperationsCenter
- SwitchBoard
- ExecutorRuntime
- CxRP
- RxP
- a scheduler
- an executor
- a subprocess runner
- a package manager replacement

## Initial supported verification mode

The main supported seed mode is:

- `install_kind = external`

This verifies a local clone by checking `git rev-parse HEAD` against `expected_sha`.

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
            fork_url="https://github.com/Velascat/archon",
            local_path="/repos/archon",
            branch="main",
            expected_sha="abc123",
            install_kind=InstallKind.EXTERNAL,
            metadata={"runtime": "bun", "language": "typescript"},
        )
    ]
)

entry = registry.resolve("archon")
verification = registry.verify("archon")

print(entry.local_path)
print(verification.ok)
```
