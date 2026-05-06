"""Patch record loader.

Patch records are filesystem-based metadata describing local fixes
applied to a source's fork branch. Schema:

    patch_id: PATCH-NNN
    source_name: <source name>
    title: "<short description>"
    status: pending_review | merged | abandoned | local
    touched_files: [<path>, ...]
    contract_gap_ref: <namespace:gap_id>     # owned by consumer (e.g. OC)
    upstream_pr_url: <url>                   # optional
    notes: ""

Files live at ``<patches_root>/<source_name>/<PATCH-NNN>.yaml``. SR
loads them but is agnostic about ``contract_gap_ref`` semantics —
that's owned by the consumer.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from source_registry.contracts.patch_record import PatchRecord
from source_registry.errors import SourceRegistryError


class PatchError(SourceRegistryError):
    """Raised when a patch yaml is malformed."""


_PATCH_ID_RE = re.compile(r"^PATCH-\d{3,}$")


class PatchRegistry:
    """In-memory index of all patch records, grouped by source name."""

    def __init__(self, by_source: dict[str, list[PatchRecord]]):
        self._by_source = by_source

    @property
    def by_source(self) -> dict[str, list[PatchRecord]]:
        return self._by_source

    def for_source(self, source_name: str) -> list[PatchRecord]:
        return list(self._by_source.get(source_name, []))

    def all_patches(self) -> list[PatchRecord]:
        out: list[PatchRecord] = []
        for patches in self._by_source.values():
            out.extend(patches)
        return out

    def get(self, full_id: str) -> PatchRecord | None:
        """Lookup by ``<source>:<PATCH-NNN>`` identifier."""
        if ":" not in full_id:
            return None
        source, patch_id = full_id.split(":", 1)
        for p in self._by_source.get(source, []):
            if p.patch_id == patch_id:
                return p
        return None


def load_patches(patches_root: Path | str) -> PatchRegistry:
    """Load every patch yaml under ``patches_root/<source>/<PATCH-NNN>.yaml``.

    Returns an empty registry when the root doesn't exist (no patches yet).
    """
    root = Path(patches_root)
    if not root.exists() or not root.is_dir():
        return PatchRegistry({})

    by_source: dict[str, list[PatchRecord]] = {}

    for source_dir in sorted(root.iterdir()):
        if not source_dir.is_dir():
            continue
        source_name = source_dir.name
        records: list[PatchRecord] = []

        for patch_file in sorted(source_dir.glob("PATCH-*.yaml")):
            stem = patch_file.stem
            if not _PATCH_ID_RE.match(stem):
                raise PatchError(
                    f"{patch_file}: filename must match PATCH-NNN.yaml"
                )

            try:
                raw = yaml.safe_load(patch_file.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                raise PatchError(f"{patch_file}: invalid YAML: {exc}") from exc

            if not isinstance(raw, dict):
                raise PatchError(f"{patch_file}: top-level must be a mapping")

            raw.setdefault("source_name", source_name)
            raw.setdefault("patch_id", stem)

            if raw.get("patch_id") != stem:
                raise PatchError(
                    f"{patch_file}: filename {stem!r} doesn't match patch_id {raw.get('patch_id')!r}"
                )

            try:
                record = PatchRecord.model_validate(raw)
            except Exception as exc:
                raise PatchError(f"{patch_file}: invalid patch record: {exc}") from exc

            records.append(record)

        if records:
            by_source[source_name] = records

    return PatchRegistry(by_source)


def drop_patch(
    patches_root: Path | str, full_id: str,
) -> Path:
    """Remove a patch yaml from disk. Returns the deleted path.

    Raises ``PatchError`` if the patch isn't found.
    """
    if ":" not in full_id:
        raise PatchError(f"invalid patch id {full_id!r}; expected '<source>:<PATCH-NNN>'")
    source, patch_id = full_id.split(":", 1)

    target = Path(patches_root) / source / f"{patch_id}.yaml"
    if not target.exists():
        raise PatchError(f"patch yaml not found: {target}")

    target.unlink()
    return target
