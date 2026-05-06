import subprocess

import pytest

from source_registry.errors import GitOperationError
from source_registry.git.git_ops import get_head_sha, is_git_repo


def _init_repo(path: str) -> None:
    subprocess.run(["git", "init", path], check=True, capture_output=True, text=True)


def _commit_file(path: str) -> None:
    subprocess.run(["git", "-C", path, "config", "user.email", "tests@example.com"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "Tests"], check=True)
    with open(f"{path}/README.md", "w", encoding="utf-8") as handle:
        handle.write("hello\n")
    subprocess.run(["git", "-C", path, "add", "README.md"], check=True)
    subprocess.run(["git", "-C", path, "commit", "-m", "init"], check=True)


def test_is_git_repo_true_for_repo(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(str(repo))
    _commit_file(str(repo))
    assert is_git_repo(str(repo)) is True


def test_is_git_repo_false_for_non_repo(tmp_path) -> None:
    non_repo = tmp_path / "dir"
    non_repo.mkdir()
    assert is_git_repo(str(non_repo)) is False


def test_get_head_sha_returns_current_head(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(str(repo))
    _commit_file(str(repo))
    expected = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    assert get_head_sha(str(repo)) == expected


def test_get_head_sha_raises_for_non_repo(tmp_path) -> None:
    non_repo = tmp_path / "dir"
    non_repo.mkdir()
    with pytest.raises(GitOperationError):
        get_head_sha(str(non_repo))
