import pytest

from source_registry.contracts.install_kind import InstallKind
from source_registry.contracts.source_entry import SourceEntry
from source_registry.errors import DuplicateSourceError, SourceNotFoundError
from source_registry.registry.resolver import SourceResolver


def _entry(name: str) -> SourceEntry:
    return SourceEntry(
        name=name,
        upstream_url="https://github.com/example/repo",
        local_path="/tmp/repo",
        branch="main",
        expected_sha="abc123",
        install_kind=InstallKind.EXTERNAL,
    )


def test_resolve_source_by_name() -> None:
    resolver = SourceResolver([_entry("archon")])
    assert resolver.resolve("archon").name == "archon"


def test_resolve_unknown_source_raises() -> None:
    resolver = SourceResolver([_entry("archon")])
    with pytest.raises(SourceNotFoundError):
        resolver.resolve("missing")


def test_reject_duplicate_source_names() -> None:
    with pytest.raises(DuplicateSourceError):
        SourceResolver([_entry("archon"), _entry("archon")])
