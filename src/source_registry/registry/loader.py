from source_registry.contracts.source_entry import SourceEntry
from source_registry.errors import RegistryLoadError
from source_registry.io.yaml_io import read_yaml


def load_sources(path: str) -> list[SourceEntry]:
    payload = read_yaml(path)
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise RegistryLoadError("registry YAML must contain a 'sources' list")

    try:
        return [SourceEntry.model_validate(item) for item in sources]
    except Exception as exc:  # pydantic raises validation exceptions
        raise RegistryLoadError(f"invalid source entry: {exc}") from exc
