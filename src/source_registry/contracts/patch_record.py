from pydantic import BaseModel, ConfigDict, Field, field_validator


class PatchRecord(BaseModel):
    """A locally-applied patch awaiting upstream resolution.

    Field semantics:
      - ``upstream_pr_url``: the upstream PR that, if merged, makes this
        patch obsolete (drives DROP_PATCH suggestions). May reference a
        third-party PR that contributes the equivalent fix.
      - ``pushed_pr_url``: the upstream PR *we* opened (set by ``push``).
        When set, the patch is being review-tracked.
      - ``pushed``: True iff we've opened our own upstream PR.
      - ``push_enabled``: opt-in flag — ``push`` refuses unless True.
      - ``fork_branch``: the branch on the fork carrying this patch.
        Required for ``push`` (which pushes that branch as the PR head).
    """
    patch_id: str
    source_name: str
    title: str
    status: str
    touched_files: list[str] = Field(default_factory=list)
    contract_gap_ref: str | None = None
    upstream_pr_url: str | None = None
    pushed_pr_url: str | None = None
    pushed: bool = False
    push_enabled: bool = False
    fork_branch: str | None = None
    notes: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("patch_id", "source_name", "title", "status")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be non-empty")
        return value
