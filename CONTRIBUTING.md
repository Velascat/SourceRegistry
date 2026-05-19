# Contributing to SourceRegistry

SourceRegistry is the source and fork tracking layer for external tools and framework repos. It resolves named source dependencies to local paths and verifies expected source state (initially via `git rev-parse HEAD` for `install_kind = external`).

## Before You Start

- Check open issues to avoid duplicate work
- For significant changes, open an issue first to discuss the approach
- All contributions must pass the test suite and linter before merging

## Development Setup

```bash
git clone https://github.com/ProtocolWarden/SourceRegistry.git
cd SourceRegistry
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest -q
```

## Linting

```bash
ruff check src/
```

## Scope Discipline

SourceRegistry intentionally has a narrow scope: **resolve named source dependencies to local paths and verify expected source state**. Do **not** add:

- Subprocess execution or runner logic (that lives in CoreRunner)
- Scheduling, queues, or workflow orchestration
- Routing decisions (that lives in SwitchBoard)
- Planning or proposal logic (that lives in OperationsCenter)
- Package manager replacement features (use `pip`/`uv`/`bun` for that)

If a feature requires reaching outside source resolution and verification, it probably belongs in another repo.

## Adding a New `install_kind`

The v1 seed is `install_kind = external` (verifies a local clone via `git rev-parse HEAD`). New kinds (e.g. `cli_tool`, `library`) should:

1. Define their verification semantics clearly (what is the source of truth?)
2. Live behind the `Verifier` protocol/abstract base
3. Ship with parity tests against `external` for shared semantics
4. Document deliberate behavior differences in the verifier's own module docstring

## Patch Records and Reconciliation

The patch-records and reconciliation layer (DROP_PATCH / REBASE_PATCH / PUSH_PATCH suggestions) is in scope for this repo. When extending it:

- Keep findings declarative (registry → suggestion); the *application* of suggestions stays caller-side
- Force-pushing or PR creation must remain opt-in via per-source flags

## Pull Request Checklist

- [ ] Tests added for new behavior
- [ ] Existing tests still pass (`pytest -q`)
- [ ] Linter passes (`ruff check src/`)
- [ ] Public API changes are reflected in the README
- [ ] Failure paths tested (missing clone, mismatched SHA, network failure, etc.)

## Code Style

- Type hints required on public functions
- Prefer dataclasses or frozen dataclasses for structured types
- No `from foo import *`
- Docstrings on public functions; comments only when the *why* is non-obvious
