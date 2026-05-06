from pathlib import Path

from source_registry.contracts.install_kind import InstallKind
from source_registry.contracts.source_entry import SourceEntry
from source_registry.contracts.verification import VerificationResult
from source_registry.git.git_ops import get_head_sha, is_git_repo
from source_registry.registry.resolver import SourceResolver


class SourceRegistry:
    def __init__(self, sources: list[SourceEntry]):
        self._resolver = SourceResolver(sources)

    def resolve(self, name: str) -> SourceEntry:
        return self._resolver.resolve(name)

    def verify(self, name: str) -> VerificationResult:
        source = self.resolve(name)

        if source.install_kind == InstallKind.PYTHON_TOOL:
            return VerificationResult(
                source_name=source.name,
                ok=False,
                install_kind=source.install_kind,
                expected_sha=source.expected_sha,
                actual_sha=None,
                local_path=source.local_path,
                message="python_tool verification is not implemented in this seed repo",
            )

        path = Path(source.local_path)
        if not path.exists():
            return VerificationResult(
                source_name=source.name,
                ok=False,
                install_kind=source.install_kind,
                expected_sha=source.expected_sha,
                actual_sha=None,
                local_path=source.local_path,
                message="local_path does not exist",
            )

        if source.install_kind == InstallKind.NONE:
            actual_sha = get_head_sha(source.local_path) if is_git_repo(source.local_path) else None
            return VerificationResult(
                source_name=source.name,
                ok=True,
                install_kind=source.install_kind,
                expected_sha=source.expected_sha,
                actual_sha=actual_sha,
                local_path=source.local_path,
                message="local_path exists",
            )

        if source.install_kind == InstallKind.EXTERNAL:
            if not is_git_repo(source.local_path):
                return VerificationResult(
                    source_name=source.name,
                    ok=False,
                    install_kind=source.install_kind,
                    expected_sha=source.expected_sha,
                    actual_sha=None,
                    local_path=source.local_path,
                    message="local_path is not a git repository",
                )

            actual_sha = get_head_sha(source.local_path)
            ok = actual_sha == source.expected_sha
            message = "HEAD matches expected SHA" if ok else "HEAD does not match expected SHA"
            return VerificationResult(
                source_name=source.name,
                ok=ok,
                install_kind=source.install_kind,
                expected_sha=source.expected_sha,
                actual_sha=actual_sha,
                local_path=source.local_path,
                message=message,
            )

        return VerificationResult(
            source_name=source.name,
            ok=False,
            install_kind=source.install_kind,
            expected_sha=source.expected_sha,
            actual_sha=None,
            local_path=source.local_path,
            message=f"unsupported install_kind: {source.install_kind}",
        )
