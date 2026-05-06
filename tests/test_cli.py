"""CLI smoke tests using typer.testing.CliRunner."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from source_registry.cli import app


_RUNNER = CliRunner()


_REGISTRY_YAML = """\
sources:
  - name: archon
    upstream_url: https://github.com/coleam00/Archon
    fork_url: https://github.com/Velascat/Archon
    local_path: /tmp/archon-fake
    branch: main
    expected_sha: abc1234
    install_kind: external
"""


def _seed_registry(tmp_path: Path) -> Path:
    p = tmp_path / "registry.yaml"
    p.write_text(_REGISTRY_YAML, encoding="utf-8")
    return p


class TestStatus:
    def test_status_lists_entries(self, tmp_path):
        reg = _seed_registry(tmp_path)
        result = _RUNNER.invoke(app, ["status", "--registry", str(reg)])
        assert result.exit_code == 0
        assert "archon" in result.stdout
        assert "external" in result.stdout

    def test_status_handles_no_sources(self, tmp_path):
        reg = tmp_path / "empty.yaml"
        reg.write_text("sources: []\n", encoding="utf-8")
        result = _RUNNER.invoke(app, ["status", "--registry", str(reg)])
        assert result.exit_code == 0
        assert "No sources" in result.stdout


class TestVerify:
    def test_verify_all_runs(self, tmp_path):
        reg = _seed_registry(tmp_path)
        result = _RUNNER.invoke(app, ["verify", "--all", "--registry", str(reg)])
        # local_path doesn't exist → FAIL exit 1, but command runs
        assert result.exit_code == 1
        assert "archon" in result.stdout


class TestErrorPaths:
    def test_missing_registry_errors(self):
        result = _RUNNER.invoke(app, ["status"])
        assert result.exit_code == 2
        assert "registry is required" in result.stdout or "registry is required" in result.stderr or "ERROR" in result.output

    def test_unknown_source_errors(self, tmp_path):
        reg = _seed_registry(tmp_path)
        result = _RUNNER.invoke(app, ["verify", "missing", "--registry", str(reg)])
        assert result.exit_code == 2


class TestAutoSyncDryRun:
    def test_dry_run_blocks_when_clone_missing(self, tmp_path):
        reg = _seed_registry(tmp_path)
        result = _RUNNER.invoke(
            app, ["auto-sync", "archon", "--dry-run", "--registry", str(reg)],
        )
        # archon's local_path doesn't exist → blocked
        assert result.exit_code == 1
        assert "archon" in result.stdout
        assert "BLOCK" in result.stdout
