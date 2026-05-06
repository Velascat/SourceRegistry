from pydantic import BaseModel, ConfigDict, Field, field_validator


class PatchRecord(BaseModel):
    patch_id: str
    source_name: str
    title: str
    status: str
    touched_files: list[str] = Field(default_factory=list)
    contract_gap_ref: str | None = None
    upstream_pr_url: str | None = None
    notes: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("patch_id", "source_name", "title", "status")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be non-empty")
        return value
