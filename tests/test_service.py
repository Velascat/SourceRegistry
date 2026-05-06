import subprocess

from source_registry.contracts.install_kind import InstallKind
from source_registry.contracts.source_entry import SourceEntry
from source_registry.service import SourceRegistry


def _make_repo(path: str) -> str:
    subprocess.run(["git", "init", path], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "tests@example.com"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "Tests"], check=True)
    with open(f"{path}/file.txt", "w", encoding="utf-8") as handle:
        handle.write("data\n")
    subprocess.run(["git", "-C", path, "add", "file.txt"], check=True)
    subprocess.run(["git", "-C", path, "commit", "-m", "init"], check=True)
    return subprocess.run(
        ["git", "-C", path, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_service_resolve_returns_expected_source(tmp_path) -> None:
    repo = tmp_path / "repo"
    sha = _make_repo(str(repo))
    entry = SourceEntry(
        name="archon",
        upstream_url="https://github.com/example/archon",
        local_path=str(repo),
        branch="main",
        expected_sha=sha,
        install_kind=InstallKind.EXTERNAL,
    )
    registry = SourceRegistry([entry])
    assert registry.resolve("archon").local_path == str(repo)


def test_verify_external_success_when_head_matches(tmp_path) -> None:
    repo = tmp_path / "repo"
    sha = _make_repo(str(repo))
    registry = SourceRegistry(
        [
            SourceEntry(
                name="archon",
                upstream_url="https://github.com/example/archon",
                local_path=str(repo),
                branch="main",
                expected_sha=sha,
                install_kind=InstallKind.EXTERNAL,
            )
        ]
    )
    result = registry.verify("archon")
    assert result.ok is True


def test_verify_external_fails_when_head_differs(tmp_path) -> None:
    repo = tmp_path / "repo"
    _ = _make_repo(str(repo))
    registry = SourceRegistry(
        [
            SourceEntry(
                name="archon",
                upstream_url="https://github.com/example/archon",
                local_path=str(repo),
                branch="main",
                expected_sha="deadbeef",
                install_kind=InstallKind.EXTERNAL,
            )
        ]
    )
    result = registry.verify("archon")
    assert result.ok is False


def test_verify_returns_not_ok_for_missing_local_path(tmp_path) -> None:
    missing = tmp_path / "missing"
    registry = SourceRegistry(
        [
            SourceEntry(
                name="archon",
                upstream_url="https://github.com/example/archon",
                local_path=str(missing),
                branch="main",
                expected_sha="abc123",
                install_kind=InstallKind.EXTERNAL,
            )
        ]
    )
    result = registry.verify("archon")
    assert result.ok is False
    assert "does not exist" in result.message


def test_verify_python_tool_reports_when_not_uv_installed(tmp_path) -> None:
    """python_tool aliases cli_tool; verify reads direct_url.json from the
    uv-tool install. When the tool isn't uv-installed we surface that.
    """
    path = tmp_path / "tool"
    path.mkdir()
    registry = SourceRegistry(
        [
            SourceEntry(
                name="tool",
                upstream_url="https://github.com/example/some-uninstalled-tool-xyz",
                local_path=str(path),
                branch="main",
                expected_sha="abc123",
                install_kind=InstallKind.PYTHON_TOOL,
            )
        ]
    )
    result = registry.verify("tool")
    assert result.ok is False
    assert "not installed" in result.message or "direct_url.json" in result.message


# ── cli_tool dir_info fallback (dev-mode local install) ────────────────


def test_verify_cli_tool_falls_back_to_git_head_when_dir_info(tmp_path, monkeypatch):
    """When direct_url.json has dir_info (dev-mode local install) and
    no vcs_info, verify reads HEAD from the install dir directly.
    """
    import json
    import subprocess

    # Build a fake "local install dir" that's a git repo
    install_dir = tmp_path / "tool-clone"
    install_dir.mkdir()
    subprocess.run(["git", "-C", str(install_dir), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(install_dir), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(install_dir), "config", "user.name", "t"], check=True)
    (install_dir / "f").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(install_dir), "add", "f"], check=True)
    subprocess.run(["git", "-C", str(install_dir), "commit", "-q", "-m", "init"], check=True)
    head = subprocess.run(
        ["git", "-C", str(install_dir), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    # Build a fake uv-tool layout that points at install_dir
    uv_root = tmp_path / "uv-tools"
    tool_root = uv_root / "tool"
    site = tool_root / "lib" / "python3.12" / "site-packages"
    dist = site / "tool-1.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "direct_url.json").write_text(
        json.dumps({"url": f"file://{install_dir}", "dir_info": {}}),
        encoding="utf-8",
    )

    # Monkey-patch _uv_tool_dir to point at our fake
    from source_registry import verify as verify_mod
    monkeypatch.setattr(verify_mod, "_uv_tool_dir", lambda: uv_root)

    registry = SourceRegistry(
        [
            SourceEntry(
                name="tool",
                upstream_url="https://github.com/example/tool",
                local_path=str(install_dir),
                branch="main",
                expected_sha=head[:7],
                install_kind=InstallKind.CLI_TOOL,
            )
        ]
    )
    result = registry.verify("tool")
    assert result.ok is True
    assert result.actual_sha == head
    assert "git HEAD" in result.message
