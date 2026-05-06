from source_registry.contracts.source_entry import SourceEntry
from source_registry.errors import DuplicateSourceError, SourceNotFoundError


class SourceResolver:
    def __init__(self, sources: list[SourceEntry]):
        self._sources_by_name: dict[str, SourceEntry] = {}
        for source in sources:
            if source.name in self._sources_by_name:
                raise DuplicateSourceError(f"duplicate source name: {source.name}")
            self._sources_by_name[source.name] = source

    def resolve(self, name: str) -> SourceEntry:
        source = self._sources_by_name.get(name)
        if source is None:
            raise SourceNotFoundError(f"source not found: {name}")
        return source
