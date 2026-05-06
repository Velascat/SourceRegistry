"""``source-registry`` CLI entrypoint.

Subcommands:
    verify [name|--all]                  read installed state, compare to pin
    bump <name> [--to SHA]               update pin to HEAD or explicit SHA
    rebase <name>                        fetch upstream + rebase fork branch
    sync <name>                          rebase + bump + reinstall
    auto-sync [name|--all] [--dry-run]   silent reconcile when safe
    poll [--patches PATH] [--json]       upstream-aware findings
    push <source>:<PATCH-NNN>            open upstream PR (opt-in)
    drop <source>:<PATCH-NNN>            remove patch yaml after upstream merge
"""
from __future__ import annotations

import json as _json
import sys
from pathlib import Path
from typing import Optional

import typer

from source_registry.contracts.install_kind import InstallMode
from source_registry.errors import SourceRegistryError
from source_registry.lifecycle import LifecycleError
from source_registry.patches import drop_patch as _drop_patch
from source_registry.poll import poll_all
from source_registry.push import PushError, push_patch
from source_registry.service import SourceRegistry


app = typer.Typer(
    help="Source and fork tracking — verify, bump, rebase, sync, auto-sync, poll, push.",
    no_args_is_help=True,
)


def _resolve(path: Optional[Path]) -> Optional[Path]:
    return path.expanduser().resolve() if path else None


def _load_registry(registry_path: Optional[Path]) -> SourceRegistry:
    if registry_path is None:
        typer.echo("ERROR: --registry is required (no default registry path)", err=True)
        raise typer.Exit(2)
    try:
        return SourceRegistry.from_yaml(registry_path)
    except SourceRegistryError as exc:
        typer.echo(f"ERROR: failed to load registry: {exc}", err=True)
        raise typer.Exit(2)


# ── Read commands ───────────────────────────────────────────────────────


@app.command("verify")
def verify(
    name: Optional[str] = typer.Argument(None, help="Source name (omit if --all)"),
    all_sources: bool = typer.Option(False, "--all", help="Verify every entry"),
    registry: Optional[Path] = typer.Option(None, "--registry"),
) -> None:
    reg = _load_registry(_resolve(registry))
    if all_sources or name is None:
        results = reg.verify_all()
    else:
        try:
            results = [reg.verify(name)]
        except SourceRegistryError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(2)

    for r in results:
        marker = "[OK]   " if r.ok else "[FAIL] "
        typer.echo(f"{marker} {r.source_name}: {r.message}")
    raise typer.Exit(0 if all(r.ok for r in results) else 1)


@app.command("status")
def status(
    registry: Optional[Path] = typer.Option(None, "--registry"),
) -> None:
    """Per-source registry summary."""
    reg = _load_registry(_resolve(registry))
    entries = reg.all()
    if not entries:
        typer.echo("No sources registered.")
        raise typer.Exit(0)
    for e in entries:
        typer.echo(e.name)
        typer.echo(f"  upstream:    {e.upstream_url}")
        if e.fork_url:
            typer.echo(f"  fork:        {e.fork_url}@{e.expected_sha[:8]} (branch={e.branch})")
        else:
            typer.echo(f"  pin:         {e.expected_sha[:8]} (branch={e.branch})")
        if e.base_commit:
            typer.echo(f"  base:        {e.base_commit[:8]}")
        typer.echo(
            f"  install:     kind={e.install_kind.value}; "
            f"modes={sorted(m.value for m in e.install_modes)}"
        )
        typer.echo(
            f"  poll:        every {e.poll_cadence_hours}h; "
            f"auto_pr_push={e.auto_pr_push}; auto_sync={e.auto_sync}"
        )
        typer.echo("")
    raise typer.Exit(0)


# ── Lifecycle commands ──────────────────────────────────────────────────


@app.command("bump")
def bump(
    name: str = typer.Argument(..., help="Source name to bump"),
    to_sha: Optional[str] = typer.Option(None, "--to", help="SHA to pin (omit = HEAD)"),
    registry: Optional[Path] = typer.Option(None, "--registry"),
) -> None:
    reg = _load_registry(_resolve(registry))
    try:
        result = reg.bump(name, to_sha=to_sha)
    except (LifecycleError, SourceRegistryError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(f"[OK] {name}: pinned {result.old_sha} -> {result.new_sha}")
    typer.echo("     Note: caller is responsible for persisting the new pin to disk.")
    raise typer.Exit(0)


@app.command("rebase")
def rebase(
    name: str = typer.Argument(..., help="Source name to rebase"),
    upstream_remote: str = typer.Option("upstream", "--upstream-remote"),
    registry: Optional[Path] = typer.Option(None, "--registry"),
) -> None:
    reg = _load_registry(_resolve(registry))
    try:
        result = reg.rebase(name, upstream_remote=upstream_remote)
    except (LifecycleError, SourceRegistryError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2)
    marker = "[OK]" if result.rebase_ok else "[FAIL]"
    typer.echo(f"{marker} {name}: rebased onto {result.upstream_ref}")
    if not result.rebase_ok:
        typer.echo(f"     output: {result.rebase_output[-400:]}")
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command("sync")
def sync(
    name: str = typer.Argument(...),
    mode: str = typer.Option("dev", "--mode", "-m"),
    registry: Optional[Path] = typer.Option(None, "--registry"),
) -> None:
    reg = _load_registry(_resolve(registry))
    try:
        install_mode = InstallMode(mode)
    except ValueError:
        typer.echo(f"ERROR: invalid mode {mode!r}", err=True)
        raise typer.Exit(2)
    try:
        result = reg.sync(name, mode=install_mode)
    except (LifecycleError, SourceRegistryError) as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(f"{name}: rebase={'ok' if result.rebase.rebase_ok else 'FAIL'}")
    if not result.rebase.rebase_ok:
        raise typer.Exit(1)
    if result.bump:
        typer.echo(f"  bumped: {result.bump.old_sha} -> {result.bump.new_sha}")
    raise typer.Exit(0)


@app.command("auto-sync")
def auto_sync(
    name: Optional[str] = typer.Argument(None, help="Source name (omit if --all)"),
    all_sources: bool = typer.Option(False, "--all"),
    mode: str = typer.Option("dev", "--mode", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    registry: Optional[Path] = typer.Option(None, "--registry"),
) -> None:
    reg = _load_registry(_resolve(registry))
    try:
        install_mode = InstallMode(mode)
    except ValueError:
        typer.echo(f"ERROR: invalid mode {mode!r}", err=True)
        raise typer.Exit(2)

    if all_sources:
        results = reg.auto_sync_all(mode=install_mode, dry_run=dry_run)
    else:
        if name is None:
            typer.echo("ERROR: provide a source name or pass --all", err=True)
            raise typer.Exit(2)
        try:
            results = [reg.auto_sync(name, mode=install_mode, dry_run=dry_run)]
        except SourceRegistryError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(2)

    any_blocked = False
    for r in results:
        marker = "[OK]   " if r.ok else "[BLOCK]"
        suffix = " (dry-run)" if dry_run else ""
        typer.echo(f"{marker} {r.name}: {r.final_state}{suffix}")
        for action in r.actions_taken:
            typer.echo(f"         + {action}")
        for blocked in r.actions_blocked:
            typer.echo(f"         ! {blocked}")
            any_blocked = True
    raise typer.Exit(1 if any_blocked else 0)


# ── Poll / push / drop ──────────────────────────────────────────────────


@app.command("poll")
def poll(
    patches: Optional[Path] = typer.Option(None, "--patches", help="Path to patches root"),
    json_output: bool = typer.Option(False, "--json"),
    registry: Optional[Path] = typer.Option(None, "--registry"),
) -> None:
    """Run one poll iteration; emits findings.

    Exit non-zero when any reconciliation is suggested.
    """
    reg = _load_registry(_resolve(registry))
    findings = poll_all(reg.all(), patches_root=_resolve(patches))

    if json_output:
        sys.stdout.write(_json.dumps([f.to_dict() for f in findings], indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        if not findings:
            typer.echo("No reconciliation suggestions.")
        for f in findings:
            typer.echo(f"[{f.suggestion.value}] {f.patch_id}")
            typer.echo(f"    reason: {f.reason}")
            if f.action_link:
                typer.echo(f"    link:   {f.action_link}")
    raise typer.Exit(1 if findings else 0)


@app.command("push")
def push(
    full_id: str = typer.Argument(..., help="<source>:<PATCH-NNN>"),
    patches: Optional[Path] = typer.Option(None, "--patches", help="Path to patches root"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    registry: Optional[Path] = typer.Option(None, "--registry"),
) -> None:
    """Push a patch's branch to its fork remote and open an upstream PR.

    Refuses unless both ``auto_pr_push`` (per-source) and ``push_enabled``
    (per-patch) are true.
    """
    reg = _load_registry(_resolve(registry))
    patches_root = _resolve(patches)
    if patches_root is None:
        typer.echo("ERROR: --patches is required for push", err=True)
        raise typer.Exit(2)

    if ":" not in full_id:
        typer.echo("ERROR: id must be '<source>:<PATCH-NNN>'", err=True)
        raise typer.Exit(2)
    source_name = full_id.split(":", 1)[0]

    try:
        entry = reg.resolve(source_name)
    except SourceRegistryError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2)

    try:
        result = push_patch(full_id, entry, patches_root=patches_root, dry_run=dry_run)
    except PushError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2)

    if not result.pushed_branch:
        typer.echo(f"[FAIL] {full_id}: {result.detail}")
        raise typer.Exit(1)
    if not result.pr_created:
        typer.echo(f"[FAIL] {full_id}: branch pushed but PR creation failed: {result.detail}")
        raise typer.Exit(1)
    typer.echo(f"[OK] {full_id}: branch pushed, PR opened at {result.pr_url}")
    raise typer.Exit(0)


@app.command("drop")
def drop(
    full_id: str = typer.Argument(..., help="<source>:<PATCH-NNN>"),
    patches: Optional[Path] = typer.Option(None, "--patches"),
) -> None:
    """Remove a patch yaml after upstream merge.

    The consumer is responsible for transitioning any associated
    contract gap status (e.g. forked → upstream_merged).
    """
    patches_root = _resolve(patches)
    if patches_root is None:
        typer.echo("ERROR: --patches is required for drop", err=True)
        raise typer.Exit(2)
    try:
        target = _drop_patch(patches_root, full_id)
    except SourceRegistryError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(f"[OK] {full_id}: removed {target}")
    typer.echo("     Caller should now transition any related gap status.")
    raise typer.Exit(0)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
