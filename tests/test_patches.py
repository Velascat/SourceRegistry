"""Patch loader tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from source_registry import PatchError, drop_patch, load_patches


_VALID = """
title: "Pass coach kwarg through orchestrator subclasses"
status: pending_review
contract_gap_ref: "kodo:G-004"
upstream_pr_url: "https://github.com/ikamensh/kodo/pull/49"
touched_files:
  - kodo/orchestrators/claude_code.py
"""


def _seed(root: Path, source: str = "kodo", patch_id: str = "PATCH-001",
          content: str = _VALID) -> Path:
    src_dir = root / source
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / f"{patch_id}.yaml").write_text(content, encoding="utf-8")
    return root


class TestLoad:
    def test_loads_one_patch(self, tmp_path):
        reg = load_patches(_seed(tmp_path))
        kodo = reg.for_source("kodo")
        assert len(kodo) == 1
        assert kodo[0].patch_id == "PATCH-001"
        assert kodo[0].source_name == "kodo"

    def test_returns_empty_when_root_absent(self, tmp_path):
        reg = load_patches(tmp_path / "nope")
        assert reg.by_source == {}

    def test_get_by_full_id(self, tmp_path):
        reg = load_patches(_seed(tmp_path))
        p = reg.get("kodo:PATCH-001")
        assert p is not None and p.patch_id == "PATCH-001"
        assert reg.get("nope:PATCH-001") is None
        assert reg.get("malformed-no-colon") is None

    def test_filename_must_match_id(self, tmp_path):
        # patch_id in yaml will be derived from filename when not present
        # if mismatched, error
        bad = _VALID + '\npatch_id: "PATCH-002"\n'
        with pytest.raises(PatchError, match="doesn't match"):
            load_patches(_seed(tmp_path, content=bad))


class TestDrop:
    def test_drop_removes_yaml(self, tmp_path):
        _seed(tmp_path)
        target = drop_patch(tmp_path, "kodo:PATCH-001")
        assert not target.exists()

    def test_drop_missing_raises(self, tmp_path):
        with pytest.raises(PatchError, match="not found"):
            drop_patch(tmp_path, "kodo:PATCH-999")

    def test_drop_invalid_id_format(self, tmp_path):
        with pytest.raises(PatchError, match="invalid patch id"):
            drop_patch(tmp_path, "no-colon")
