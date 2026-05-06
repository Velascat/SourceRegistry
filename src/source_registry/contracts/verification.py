from pydantic import BaseModel, ConfigDict, field_validator

from source_registry.contracts.install_kind import InstallKind


class VerificationResult(BaseModel):
    source_name: str
    ok: bool
    install_kind: InstallKind
    expected_sha: str
    actual_sha: str | None = None
    local_path: str
    message: str = ""

    model_config = ConfigDict(extra="forbid")

    @field_validator("source_name", "expected_sha", "local_path")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be non-empty")
        return value
