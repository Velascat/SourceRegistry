import pytest

from source_registry.errors import RegistryLoadError
from source_registry.registry.loader import load_sources


def test_load_sources_valid_yaml(tmp_path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(
        """
sources:
  - name: archon
    upstream_url: https://github.com/example/archon
    fork_url: https://github.com/Velascat/archon
    local_path: /repos/archon
    branch: main
    expected_sha: abc123
    install_kind: external
    metadata:
      runtime: bun
""".strip(),
        encoding="utf-8",
    )

    sources = load_sources(str(config))
    assert len(sources) == 1
    assert sources[0].name == "archon"


def test_load_sources_rejects_missing_sources_list(tmp_path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text("{}", encoding="utf-8")

    with pytest.raises(RegistryLoadError):
        load_sources(str(config))


def test_load_sources_rejects_invalid_entry(tmp_path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text("sources:\n  - {}\n", encoding="utf-8")

    with pytest.raises(RegistryLoadError):
        load_sources(str(config))
