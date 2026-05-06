from pydantic import BaseModel, ConfigDict, Field, field_validator

from source_registry.contracts.install_kind import InstallKind


class SourceEntry(BaseModel):
    name: str
    upstream_url: str
    fork_url: str | None = None
    local_path: str
    branch: str
    expected_sha: str
    install_kind: InstallKind
    metadata: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "upstream_url", "local_path", "branch", "expected_sha")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be non-empty")
        return value
