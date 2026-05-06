from pydantic import BaseModel, ConfigDict, Field, field_validator

from source_registry.contracts.install_kind import InstallKind, InstallMode


class SourceEntry(BaseModel):
    """One source dependency tracked by the registry.

    Required:
      - ``name``: stable identifier (matches ``fork_id`` in OC's legacy schema)
      - ``upstream_url``: original repo URL (e.g. ``https://github.com/owner/repo``)
      - ``local_path``: where the local clone lives on disk
      - ``branch``: the working branch on the fork (or upstream if no fork)
      - ``expected_sha``: the registry pin — the SHA we're locked to
      - ``install_kind``: how to verify the install (see InstallKind)

    Optional:
      - ``fork_url``: only set when this source is forked
      - ``base_commit``: where the fork was branched from (for rebase reasoning)
      - ``install_modes``: per-mode install command templates (dev/ci/prod);
        commands may reference ``{expected_sha}`` and ``{local_path}``
      - ``local_clone_hint``: hint for clone-discovery fallbacks
      - ``poll_cadence_hours``: how often the poll loop should fire
      - ``auto_pr_push``: when true, ``push`` may open PRs against upstream
      - ``auto_sync``: when true, ``auto-sync`` may apply safe reconcile actions
        (DROP_PATCH on upstream merge, reset+bump+reinstall when no patches)
      - ``metadata``: free-form key/value pairs (no semantic meaning)
    """

    name: str
    upstream_url: str
    fork_url: str | None = None
    local_path: str
    branch: str
    expected_sha: str
    install_kind: InstallKind

    base_commit: str | None = None
    install_modes: dict[InstallMode, str] = Field(default_factory=dict)
    local_clone_hint: str | None = None
    poll_cadence_hours: int = 24
    auto_pr_push: bool = False
    auto_sync: bool = True
    metadata: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "upstream_url", "local_path", "branch", "expected_sha")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be non-empty")
        return value

    def render_install_command(self, mode: InstallMode) -> str:
        """Substitute ``{expected_sha}`` and ``{local_path}`` into the
        configured command for ``mode``.
        """
        if mode not in self.install_modes:
            available = sorted(m.value for m in self.install_modes)
            raise KeyError(
                f"install mode {mode.value!r} not configured for "
                f"{self.name!r}; have: {available}"
            )
        return self.install_modes[mode].format(
            expected_sha=self.expected_sha,
            local_path=self.local_path,
        )
