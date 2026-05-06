import subprocess

from source_registry.errors import GitOperationError


def get_head_sha(local_path: str) -> str:
    result = subprocess.run(
        ["git", "-C", local_path, "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown git error"
        raise GitOperationError(f"failed to read HEAD for '{local_path}': {stderr}")
    return result.stdout.strip()


def is_git_repo(local_path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", local_path, "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0
