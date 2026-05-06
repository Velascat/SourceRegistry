import pytest
from pydantic import ValidationError

from source_registry.contracts.install_kind import InstallKind
from source_registry.contracts.source_entry import SourceEntry


def _valid_payload() -> dict:
    return {
        "name": "archon",
        "upstream_url": "https://github.com/example/archon",
        "fork_url": None,
        "local_path": "/tmp/archon",
        "branch": "main",
        "expected_sha": "abc123",
        "install_kind": InstallKind.EXTERNAL,
    }


@pytest.mark.parametrize("field", ["name", "upstream_url", "local_path", "branch", "expected_sha"])
def test_source_entry_rejects_empty_required_fields(field: str) -> None:
    payload = _valid_payload()
    payload[field] = ""
    with pytest.raises(ValidationError):
        SourceEntry.model_validate(payload)


def test_source_entry_metadata_defaults_to_empty_dict() -> None:
    entry = SourceEntry.model_validate(_valid_payload())
    assert entry.metadata == {}
