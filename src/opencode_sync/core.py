"""Core sync orchestration logic."""

from pathlib import Path
from typing import Optional

from rich.console import Console

from opencode_sync import config, git_ops, github
from opencode_sync.conflict import Resolution, prompt_conflict
from opencode_sync.utils import (
    DEFAULT_SYNC_PATHS,
    LOCAL_REPO_DIR,
    copy_from_repo,
    copy_to_repo,
    ensure_dir,
)

console = Console()


def _stage_local_to_repo() -> None:
    """Copy all tracked config files into the local repo mirror."""
    for rel in DEFAULT_SYNC_PATHS:
        src = Path.home() / rel
        copy_to_repo(src, LOCAL_REPO_DIR)


def cmd_init(repo_url: Optional[str] = None) -> None:
    if git_ops.is_initialized():
        console.print("[yellow]Already initialized.[/yellow] Run [bold]ocs pull[/bold] to sync.")
        return

    # Determine repo URL
    if not repo_url:
        if github.gh_authenticated():
            console.print("GitHub CLI detected. Creating private repo [bold]opencode-config[/bold]...")
            repo_url, error = github.create_private_repo()
            if repo_url:
                console.print(f"[green]Created:[/green] {repo_url}")
            else:
                console.print(f"[red]Failed to create repo via gh.[/red]\n{error}")
                console.print(github.manual_instructions())
                return
        else:
            console.print(github.manual_instructions())
            return

    config.set_repo_url(repo_url)

    # Check if remote repo is empty or has content
    console.print(f"Connecting to [bold]{repo_url}[/bold]...")
    try:
        repo = git_ops.init_repo(repo_url)
        # Remote has content — pull it down
        console.print("Remote repo has existing config. Pulling...")
        copy_from_repo(LOCAL_REPO_DIR)
        console.print("[green]Done![/green] Config pulled from remote.")
    except Exception:
        # Remote is empty — push local config up
        console.print("Remote repo is empty. Pushing local config...")
        repo = git_ops.create_local_repo(repo_url)
        _stage_local_to_repo()
        commit = git_ops.commit_all(repo, "Initial config sync")
        if commit:
            repo.git.push("--set-upstream", "origin", "HEAD:main")
            console.print("[green]Done![/green] Local config pushed to remote.")
        else:
            console.print("[yellow]No config files found to sync.[/yellow]")

    console.print("\nSetup complete! Add to your shell rc file:")
    console.print("  [bold]alias ocs='uvx --from opencode-config-sync ocs'[/bold]")


def cmd_push() -> None:
    _require_init()
    repo = git_ops.open_repo()

    # Stage current config into repo
    _stage_local_to_repo()

    if not git_ops.has_local_changes(repo):
        console.print("[dim]Nothing to push — config is up to date.[/dim]")
        return

    # Fetch and check for remote changes first
    git_ops.fetch(repo)
    remote_ahead = _remote_is_ahead(repo)

    if remote_ahead:
        diff = git_ops.get_diff(repo)
        resolution = prompt_conflict(diff)

        if resolution == Resolution.CANCEL:
            console.print("[dim]Push cancelled.[/dim]")
            return
        elif resolution == Resolution.USE_REMOTE:
            _do_pull(repo)
            return
        # KEEP_LOCAL: fall through to force push below

    git_ops.commit_all(repo, "Update config")
    try:
        git_ops.push(repo)
        console.print("[green]Config pushed successfully.[/green]")
    except Exception as e:
        # If push was rejected (non-fast-forward), force push after conflict resolution
        if "rejected" in str(e).lower() or "non-fast-forward" in str(e).lower():
            repo.git.push("--force-with-lease")
            console.print("[green]Config pushed successfully.[/green]")
        else:
            raise


def cmd_pull() -> None:
    _require_init()
    repo = git_ops.open_repo()

    # Check for uncommitted local changes first
    _stage_local_to_repo()
    if git_ops.has_local_changes(repo):
        diff = git_ops.get_diff(repo)
        resolution = prompt_conflict(diff)
        if resolution == Resolution.CANCEL:
            console.print("[dim]Pull cancelled.[/dim]")
            return
        elif resolution == Resolution.KEEP_LOCAL:
            console.print("[dim]Keeping local config. Nothing pulled.[/dim]")
            return
        # USE_REMOTE: fall through

    _do_pull(repo)


def cmd_status() -> None:
    _require_init()
    repo = git_ops.open_repo()
    _stage_local_to_repo()

    repo_url = config.get_repo_url()
    console.print(f"[bold]Repo:[/bold] {repo_url}")
    console.print(f"[bold]Local repo:[/bold] {LOCAL_REPO_DIR}")

    git_ops.fetch(repo)
    local_dirty = git_ops.has_local_changes(repo)
    remote_ahead = _remote_is_ahead(repo)

    if not local_dirty and not remote_ahead:
        console.print("[green]In sync.[/green] Local and remote are identical.")
    else:
        if local_dirty:
            console.print("[yellow]Local changes[/yellow] not yet pushed.")
        if remote_ahead:
            console.print("[yellow]Remote changes[/yellow] not yet pulled.")


def cmd_diff() -> None:
    _require_init()
    repo = git_ops.open_repo()
    _stage_local_to_repo()
    diff = git_ops.get_diff(repo)
    if diff:
        from rich.syntax import Syntax
        console.print(Syntax(diff, "diff", theme="monokai"))
    else:
        console.print("[dim]No differences.[/dim]")


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_init() -> None:
    if not git_ops.is_initialized():
        console.print("[red]Not initialized.[/red] Run [bold]ocs init[/bold] first.")
        raise SystemExit(1)


def _remote_is_ahead(repo) -> bool:
    try:
        remote_ref = repo.remotes.origin.refs.main
    except AttributeError:
        try:
            remote_ref = repo.remotes.origin.refs.master
        except AttributeError:
            return False
    return repo.head.commit != remote_ref.commit and repo.is_ancestor(repo.head.commit, remote_ref.commit)


def _do_pull(repo) -> None:
    updated = git_ops.pull_ff(repo)
    if updated:
        copy_from_repo(LOCAL_REPO_DIR)
        console.print("[green]Config pulled and applied.[/green]")
    else:
        console.print("[dim]Already up to date.[/dim]")
