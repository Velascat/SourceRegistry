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


def test_verify_python_tool_not_implemented(tmp_path) -> None:
    path = tmp_path / "tool"
    path.mkdir()
    registry = SourceRegistry(
        [
            SourceEntry(
                name="tool",
                upstream_url="https://github.com/example/tool",
                local_path=str(path),
                branch="main",
                expected_sha="abc123",
                install_kind=InstallKind.PYTHON_TOOL,
            )
        ]
    )
    result = registry.verify("tool")
    assert result.ok is False
    assert "not implemented" in result.message
