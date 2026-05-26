"""commitr: AI-generated git commit messages that match your project's style."""
from __future__ import annotations

import importlib.metadata
import logging
import os
import shlex
import subprocess

# Quiet litellm's noisy import-time warnings about optional AWS providers.
# Must be set BEFORE importing anything that imports litellm.
logging.getLogger("LiteLLM").setLevel(logging.ERROR)

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from commitr import (
    cache, config, doctor, git, hook, hunks, issue, llm, pr, splitter, style,
)


def _version_callback(value: bool) -> None:
    if not value:
        return
    try:
        version = importlib.metadata.version("commitr")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    typer.echo(f"commitr {version}")
    raise typer.Exit()


app = typer.Typer(
    add_completion=False,
    help="Generate a git commit message from your staged diff using an LLM.",
    no_args_is_help=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def _entry(
    ctx: typer.Context,
    model: str | None = typer.Option(
        None, "--model", "-m",
        help="Exact LiteLLM model string. Overrides --provider and config.",
    ),
    provider: str | None = typer.Option(
        None, "--provider", "-p",
        help=f"Use a provider preset: {', '.join(config.PROVIDERS)}.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation, commit directly."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the message but do not commit."),
    split: bool = typer.Option(
        False, "--split", "-s",
        help="Analyze the diff and propose splitting into multiple independent commits.",
    ),
    hunks_flag: bool = typer.Option(
        False, "--hunks",
        help="With --split, group at the HUNK level (within files). Requires --split.",
    ),
    issue_num: int | None = typer.Option(
        None, "--issue", "-i",
        help="Inject issue #N as context for the model. Auto-detected from branch name otherwise.",
    ),
    no_issue: bool = typer.Option(
        False, "--no-issue",
        help="Skip the auto-detect-from-branch issue context.",
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache",
        help="Bypass the local message cache (force a fresh LLM call).",
    ),
    version: bool = typer.Option(
        False, "--version", "-V",
        callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Default action (no subcommand): generate a commit message."""
    config.load_env_file()
    if ctx.invoked_subcommand is not None:
        return
    _run_commit(
        model=model, provider=provider, yes=yes, dry_run=dry_run,
        split=split, hunks_split=hunks_flag,
        issue_num=issue_num, no_issue=no_issue, no_cache=no_cache,
    )


@app.command("providers")
def providers_cmd() -> None:
    """List supported AI providers and which have credentials configured."""
    config.load_env_file()
    table = Table(title="Supported providers", header_style="bold cyan")
    table.add_column("provider")
    table.add_column("model")
    table.add_column("key env")
    table.add_column("status")
    table.add_column("notes", style="dim")
    for p, ok in config.provider_status():
        key_label = p.key_env or "—"
        status = "[green]✓ ready[/green]" if ok else "[red]✗ no key[/red]"
        table.add_row(p.name, p.model, key_label, status, p.notes)
    console.print(table)
    console.print(
        "\n[dim]Use [bold]commitr --provider <name>[/bold] for a one-off, "
        "or [bold]commitr config --init[/bold] to set a default.[/dim]"
    )


@app.command("install-hook")
def install_hook_cmd(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing hook."),
) -> None:
    """Install a prepare-commit-msg hook so `git commit` auto-fills the message."""
    if not git.in_repo():
        console.print("[red]Not inside a git repository.[/red]")
        raise typer.Exit(code=1)
    try:
        path, overwrote = hook.install(force=force)
    except FileExistsError as exc:
        console.print(
            f"[yellow]Hook already exists at {exc}. "
            "Pass [bold]--force[/bold] to overwrite.[/yellow]"
        )
        raise typer.Exit(code=1) from exc
    verb = "Overwrote" if overwrote else "Installed"
    console.print(f"[green]✓[/green] {verb}: {path}")
    console.print(
        "Run [bold]git commit[/bold] (no -m) — commitr will fill the editor for you."
    )


@app.command("uninstall-hook")
def uninstall_hook_cmd() -> None:
    """Remove the prepare-commit-msg hook from the current repo."""
    if not git.in_repo():
        console.print("[red]Not inside a git repository.[/red]")
        raise typer.Exit(code=1)
    try:
        removed = hook.uninstall()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if removed is None:
        console.print("[dim]No hook installed.[/dim]")
    else:
        console.print(f"[green]✓[/green] Removed: {removed}")


@app.command("hook-fill", hidden=True)
def hook_fill_cmd(msg_file: str = typer.Argument(..., help="Path to COMMIT_EDITMSG")) -> None:
    """Internal: called by the prepare-commit-msg hook. Silent on failure."""
    config.load_env_file()
    if not git.in_repo() or not git.has_staged_changes():
        return
    try:
        resolved = config.resolve_model(cli_model=None, cli_provider=None)
        diff = git.staged_diff_for_llm()
        subjects = git.recent_commits(limit=20)
        samples = git.recent_commit_samples(limit=5)
        # Auto-detect issue context silently — never block the commit.
        issue_ctx: str | None = None
        try:
            detected = issue.detect_issue_from_branch()
            if detected is not None:
                issue_ctx = issue.fetch_issue_context(detected)
        except Exception:
            issue_ctx = None
        message = llm.generate_commit_message(
            diff=diff, subjects=subjects, samples=samples, model=resolved,
            context=issue_ctx,
        )
    except Exception:
        return  # silent: user gets a clean editor on any failure
    message = _append_coauthor(message)
    hook.fill_message_file(msg_file, message)


@app.command("config")
def config_cmd(
    init: bool = typer.Option(False, "--init", help="Write config & .env templates if missing."),
) -> None:
    """Show resolved config; with --init, create template files."""
    if init:
        cfg_path = config.write_config_template()
        env_path = config.write_env_template()
        console.print(f"[green]✓[/green] Config: {cfg_path}")
        console.print(f"[green]✓[/green] Env:    {env_path}")
        console.print("\nEdit them, then run [bold]commitr[/bold].")
        return
    config.load_env_file()
    try:
        resolved = config.resolve_model(cli_model=None, cli_provider=None)
        console.print(f"[bold]Resolved model:[/bold] {resolved}")
    except Exception as exc:
        console.print(f"[yellow]No model could be resolved:[/yellow] {exc}")
    cfg_exists = "exists" if config.CONFIG_FILE.exists() else "not found"
    env_exists = "exists" if config.ENV_FILE.exists() else "not found"
    console.print(f"[dim]Config file: {config.CONFIG_FILE} ({cfg_exists})[/dim]")
    console.print(f"[dim]Env file:    {config.ENV_FILE} ({env_exists})[/dim]")


@app.command("style")
def style_cmd() -> None:
    """Infer and print the commit-message style from recent history."""
    if not git.in_repo():
        console.print("[red]Not inside a git repository.[/red]")
        raise typer.Exit(code=1)
    profile = style.infer_profile(
        subjects=git.recent_commits(limit=50),
        samples=git.recent_commit_samples(limit=10),
    )
    console.print(
        Panel(
            style.render_profile(profile),
            title="Commit style profile",
            border_style="cyan",
        )
    )


@app.command("cache")
def cache_cmd(
    clear: bool = typer.Option(False, "--clear", help="Delete every cached message."),
) -> None:
    """Inspect or clear the local commit-message cache."""
    if clear:
        removed = cache.clear()
        console.print(f"[green]✓[/green] Cleared {removed} cache entr{'y' if removed == 1 else 'ies'}.")
        return
    info = cache.stats()
    kb = info["bytes"] / 1024 if info["bytes"] else 0
    console.print(f"[bold]Cache dir:[/bold] {cache.CACHE_DIR}")
    console.print(f"Entries:    {info['entries']}")
    console.print(f"On-disk:    {kb:.1f} KiB")
    console.print("\n[dim]Use [bold]commitr cache --clear[/bold] to wipe.[/dim]")


@app.command("pr")
def pr_cmd(
    model: str | None = typer.Option(None, "--model", "-m"),
    provider: str | None = typer.Option(None, "--provider", "-p"),
    base: str | None = typer.Option(
        None, "--base", "-b",
        help="Base ref to diff against. Auto-detected (origin/main, main, master).",
    ),
    create: bool = typer.Option(
        False, "--create", help="Create the PR via `gh pr create` after generation.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation, just print/create."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print only; do not call `gh pr create`."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the local cache."),
) -> None:
    """Generate a pull-request title + body from this branch's diff against base."""
    config.load_env_file()
    if not git.in_repo():
        console.print("[red]Not inside a git repository.[/red]")
        raise typer.Exit(code=1)

    base_ref = base or pr.detect_base_branch()
    if not base_ref:
        console.print(
            "[red]Could not detect a base branch.[/red] "
            "Pass --base origin/main (or similar)."
        )
        raise typer.Exit(code=1)

    commits = pr.commits_since(base_ref)
    if not commits:
        console.print(
            f"[yellow]No commits on HEAD that aren't already on {base_ref}.[/yellow]"
        )
        raise typer.Exit(code=1)

    diff = pr.diff_against(base_ref)
    if not diff.strip():
        console.print(
            f"[yellow]Empty diff against {base_ref}; nothing to describe.[/yellow]"
        )
        raise typer.Exit(code=1)

    try:
        resolved = config.resolve_model(cli_model=model, cli_provider=provider)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    pr_samples = pr.recent_pr_titles()

    with console.status(f"[cyan]Generating PR description via {resolved}…[/cyan]"):
        try:
            pull = pr.generate(
                base_ref=base_ref, commits=commits, diff=diff,
                pr_samples=pr_samples, model=resolved, use_cache=not no_cache,
            )
        except Exception as exc:
            console.print(f"[red]PR generation failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

    console.print(
        Panel(
            f"[bold]{pull.title}[/bold]\n\n{pull.body}",
            title=f"Proposed PR (base: {base_ref}, {len(commits)} commit(s))",
            border_style="cyan",
        )
    )

    if dry_run:
        return

    if create:
        if not yes and not questionary.confirm("Create this PR now?").ask():
            console.print("[dim]Aborted.[/dim]")
            return
        import subprocess as _sp
        result = _sp.run(
            ["gh", "pr", "create", "--title", pull.title, "--body", pull.body],
            check=False,
        )
        if result.returncode != 0:
            console.print("[red]`gh pr create` failed (is gh installed and authed?).[/red]")
            raise typer.Exit(code=2)
    else:
        console.print(
            "\n[dim]Pass [bold]--create[/bold] to open the PR via `gh pr create`.[/dim]"
        )


@app.command("doctor")
def doctor_cmd() -> None:
    """Check staged changes and local config before generating a commit."""
    config.load_env_file()
    if not git.in_repo():
        console.print("[red]Not inside a git repository.[/red]")
        raise typer.Exit(code=1)

    model_error: str | None = None
    try:
        config.resolve_model(cli_model=None, cli_provider=None)
    except Exception as exc:
        model_error = str(exc)

    files = git.staged_files()
    diff = git.staged_diff_for_llm() if files else ""
    findings = doctor.analyze_staged_changes(
        diff=diff,
        files=files,
        model_error=model_error,
    )
    status = doctor.overall_status(findings)

    if not findings:
        console.print("[green]✓[/green] No local commit issues detected.")
        return

    table = Table(title=f"commitr doctor: {status}", header_style="bold cyan")
    table.add_column("level")
    table.add_column("code")
    table.add_column("message")
    for finding in findings:
        style_name = {
            "error": "red",
            "warning": "yellow",
            "info": "cyan",
        }.get(finding.level, "white")
        table.add_row(
            f"[{style_name}]{finding.level}[/{style_name}]",
            finding.code,
            finding.message,
        )
    console.print(table)
    if status == "error":
        raise typer.Exit(code=1)


def _run_commit(
    model: str | None,
    provider: str | None,
    yes: bool,
    dry_run: bool,
    split: bool = False,
    hunks_split: bool = False,
    issue_num: int | None = None,
    no_issue: bool = False,
    no_cache: bool = False,
) -> None:
    if not git.in_repo():
        console.print("[red]Not inside a git repository.[/red]")
        raise typer.Exit(code=1)

    if not git.has_staged_changes():
        console.print("[yellow]No staged changes. Run `git add` first.[/yellow]")
        raise typer.Exit(code=1)

    try:
        resolved = config.resolve_model(cli_model=model, cli_provider=provider)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    diff = git.staged_diff_for_llm()
    patch_diff = git.staged_diff_for_patch() if split else diff
    files = git.staged_files()
    subjects = git.recent_commits(limit=20)
    samples = git.recent_commit_samples(limit=5)
    issue_context = _resolve_issue_context(issue_num, no_issue)

    # Doctor preflight: surface deterministic issues before burning an API call.
    findings = doctor.analyze_staged_changes(diff=diff, files=files)
    if findings:
        for f in findings:
            color = {"error": "red", "warning": "yellow"}.get(f.level, "cyan")
            console.print(f"[{color}]{f.level}[/{color}] {f.code}: {f.message}")
        if doctor.overall_status(findings) == "error":
            raise typer.Exit(code=1)

    if hunks_split and not split:
        console.print("[yellow]--hunks requires --split. Use `commitr --split --hunks`.[/yellow]")
        raise typer.Exit(code=1)

    if split:
        if hunks_split:
            _hunks_split_flow(
                patch_diff, subjects, samples, resolved, dry_run=dry_run, yes=yes,
            )
        else:
            _split_flow(
                diff, patch_diff, subjects, samples, resolved,
                dry_run=dry_run, yes=yes,
            )
        return

    with console.status(f"[cyan]Asking {resolved}…[/cyan]"):
        try:
            message = llm.generate_commit_message(
                diff=diff, subjects=subjects, samples=samples, model=resolved,
                context=issue_context, use_cache=not no_cache,
            )
        except Exception as exc:
            console.print(f"[red]LLM call failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

    message = _append_coauthor(message)
    title_suffix = f"via {resolved}"
    if issue_context:
        title_suffix += " · issue context loaded"
    console.print(Panel(message, title=f"Proposed commit ({title_suffix})", border_style="cyan"))

    if dry_run:
        return

    if yes:
        choice = "accept"
    else:
        choice = questionary.select(
            "What now?",
            choices=[
                questionary.Choice("Accept and commit", value="accept"),
                questionary.Choice("Edit before committing", value="edit"),
                questionary.Choice("Regenerate", value="regen"),
                questionary.Choice("Cancel", value="cancel"),
            ],
        ).ask()

    if choice is None or choice == "cancel":
        console.print("[dim]Aborted.[/dim]")
        return

    if choice == "regen":
        with console.status("[cyan]Regenerating…[/cyan]"):
            # Regen always bypasses cache; the user explicitly wants a new draft.
            message = llm.generate_commit_message(
                diff=diff, subjects=subjects, samples=samples, model=resolved,
                context=issue_context, use_cache=False,
            )
        message = _append_coauthor(message)
        console.print(Panel(message, title="Proposed commit (v2)", border_style="cyan"))
        if not questionary.confirm("Commit this?").ask():
            console.print("[dim]Aborted.[/dim]")
            return

    if choice == "edit":
        edited = _edit_in_editor(message)
        if not edited.strip():
            console.print("[dim]Empty message. Aborted.[/dim]")
            return
        message = edited

    try:
        out = git.commit(message)
        console.print(f"[green]✓ Committed.[/green]\n{out.strip()}")
    except RuntimeError as exc:
        console.print(f"[red]Commit failed:[/red] {exc}")
        raise typer.Exit(code=3) from exc


def _stage_files_from_snapshot(
    files: list[str],
    snapshot_by_path: dict[str, hunks.FilePatch],
) -> None:
    """Stage exactly the originally-staged changes for these files.

    Uses the snapshot diff instead of `git add` so that unstaged edits in the
    working tree are never accidentally pulled into the index.
    """
    patch = _render_snapshot_patch(files, snapshot_by_path)
    git.unstage_all()
    if patch:
        try:
            git.apply_patch_cached(patch)
        except (ValueError, RuntimeError):
            _restore_snapshot(snapshot_by_path)
            raise


def _render_snapshot_patch(
    files: list[str],
    snapshot_by_path: dict[str, hunks.FilePatch],
) -> str:
    return "".join(
        rendered
        for f in files
        if (fp := snapshot_by_path.get(f)) is not None
        and (rendered := fp.render())
    )


def _restore_snapshot(snapshot_by_path: dict[str, hunks.FilePatch]) -> None:
    """Best-effort restore of the original staged snapshot after apply failure."""
    patch = _render_snapshot_patch(list(snapshot_by_path), snapshot_by_path)
    git.unstage_all()
    if patch:
        try:
            git.apply_patch_cached(patch)
        except (ValueError, RuntimeError):
            pass


def _split_flow(
    diff: str,
    patch_diff: str,
    subjects: list[str],
    samples: list[str],
    resolved: str,
    dry_run: bool,
    yes: bool = False,
) -> None:
    """Multi-commit split: ask LLM to group files, then commit each group."""
    files = git.staged_files()
    # Snapshot the index NOW so partial staging (git add -p) is preserved.
    # All subsequent stage/restage operations use this patch, not git-add.
    snapshot_by_path = {fp.path: fp for fp in hunks.parse_diff(patch_diff)}
    if len(files) <= 1:
        console.print(
            "[yellow]Only one staged file; nothing to split. "
            "Run without --split for a normal commit.[/yellow]"
        )
        raise typer.Exit(code=1)

    with console.status(f"[cyan]Analyzing {len(files)} files for split groups…[/cyan]"):
        try:
            groups = splitter.analyze_splits(
                diff=diff, files=files, subjects=subjects, samples=samples, model=resolved,
            )
        except Exception as exc:
            console.print(f"[red]Split analysis failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

    # Apply Co-Authored-By trailer (if configured) to every group's proposed message.
    for g in groups:
        g.message = _append_coauthor(g.message)

    if len(groups) == 1:
        console.print("[dim]LLM judged this as a single coherent change — no split needed.[/dim]")

    console.print(
        f"\n[bold cyan]Proposed {len(groups)} commit group(s).[/bold cyan]\n"
    )
    if dry_run:
        for i, g in enumerate(groups, 1):
            _print_group_panel(g, i, len(groups))
        console.print("[dim](dry-run — no commits made)[/dim]")
        return

    skipped: list[splitter.CommitGroup] = []
    committed = 0
    for i, group in enumerate(groups, 1):
        _print_group_panel(group, i, len(groups))

        if yes:
            if not group.message.strip():
                console.print(
                    "[yellow]Group has no message; skipping (--yes can't edit).[/yellow]"
                )
                skipped.append(group)
                continue
            choice = "commit"
        else:
            choice = questionary.select(
                "What now?",
                choices=[
                    questionary.Choice("Commit this group", value="commit"),
                    questionary.Choice("Edit message, then commit", value="edit"),
                    questionary.Choice("Skip this group", value="skip"),
                    questionary.Choice("Stop (abort remaining)", value="stop"),
                ],
            ).ask()

        if choice in (None, "stop"):
            remaining = [f for g in (skipped + list(groups[i - 1 :])) for f in g.files]
            if remaining:
                _stage_files_from_snapshot(remaining, snapshot_by_path)
                console.print(
                    f"[dim]Re-staged {len(remaining)} files from skipped / remaining groups.[/dim]"
                )
            console.print("[dim]Stopped.[/dim]")
            return

        if choice == "skip":
            skipped.append(group)
            continue

        msg = group.message
        if choice == "edit" or not msg.strip():
            msg = _edit_in_editor(msg or "")
            if not msg.strip():
                console.print("[dim]Empty message; skipping this group.[/dim]")
                skipped.append(group)
                continue

        try:
            _stage_files_from_snapshot(group.files, snapshot_by_path)
            git.commit(msg)
            committed += 1
            console.print(f"[green]✓ Committed group {i}.[/green]")
        except (ValueError, RuntimeError) as exc:
            console.print(f"[red]Commit failed:[/red] {exc}")
            return

    if skipped:
        skipped_files = [f for g in skipped for f in g.files]
        _stage_files_from_snapshot(skipped_files, snapshot_by_path)
        console.print(
            f"[yellow]{len(skipped)} group(s) skipped.[/yellow] "
            f"Re-staged {len(skipped_files)} file(s) for follow-up."
        )
    console.print(f"\n[bold green]Done.[/bold green] {committed} commit(s) created.")


def _hunks_split_flow(
    diff: str,
    subjects: list[str],
    samples: list[str],
    resolved: str,
    dry_run: bool,
    yes: bool = False,
) -> None:
    """Hunk-level split: ask LLM to group hunks, then `git apply --cached` each group."""
    file_patches = hunks.parse_diff(diff)
    if not file_patches:
        console.print("[yellow]No parseable hunks in the staged diff.[/yellow]")
        raise typer.Exit(code=1)

    total_hunks = sum(len(fp.hunks) for fp in file_patches if not fp.atomic)
    atomic_count = sum(1 for fp in file_patches if fp.atomic)
    if total_hunks <= 1 and atomic_count == 0:
        console.print(
            "[yellow]Only one hunk to split; run without --hunks for a normal commit.[/yellow]"
        )
        raise typer.Exit(code=1)

    with console.status(
        f"[cyan]Analyzing {total_hunks} hunk(s) across "
        f"{len(file_patches)} file(s)…[/cyan]"
    ):
        try:
            groups = hunks.analyze_hunk_splits(
                file_patches=file_patches,
                subjects=subjects, samples=samples, model=resolved,
            )
        except Exception as exc:
            console.print(f"[red]Hunk split analysis failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

    if len(groups) == 1:
        console.print(
            "[dim]Model judged this as a single coherent change — no hunk split needed.[/dim]"
        )

    # Apply Co-Authored-By trailer (if configured) to every group's proposed message.
    for g in groups:
        g.message = _append_coauthor(g.message)

    console.print(
        f"\n[bold cyan]Proposed {len(groups)} commit group(s) (hunk-level).[/bold cyan]\n"
    )

    # Snapshot the original index so we can restore on Stop / failure.
    if dry_run:
        for i, group in enumerate(groups, 1):
            _print_hunk_group_panel(group, file_patches, i, len(groups))
        console.print("[dim](dry-run — no commits made)[/dim]")
        return

    skipped: list[hunks.HunkGroup] = []
    committed = 0
    remaining_groups = list(groups)
    for i, group in enumerate(groups, 1):
        _print_hunk_group_panel(group, file_patches, i, len(groups))

        if yes:
            if not group.message.strip():
                console.print(
                    "[yellow]Group has no message; skipping (--yes can't edit).[/yellow]"
                )
                skipped.append(group)
                continue
            choice = "commit"
        else:
            choice = questionary.select(
                "What now?",
                choices=[
                    questionary.Choice("Commit this group", value="commit"),
                    questionary.Choice("Edit message, then commit", value="edit"),
                    questionary.Choice("Skip this group", value="skip"),
                    questionary.Choice("Stop (abort remaining)", value="stop"),
                ],
            ).ask()

        if choice in (None, "stop"):
            # Re-stage everything that hasn't been committed so the user can finish.
            _restage_remaining_hunks(skipped + remaining_groups[i - 1 :], file_patches)
            console.print("[dim]Stopped.[/dim]")
            return

        if choice == "skip":
            skipped.append(group)
            continue

        msg = group.message
        if choice == "edit" or not msg.strip():
            msg = _edit_in_editor(msg or "")
            if not msg.strip():
                console.print("[dim]Empty message; skipping this group.[/dim]")
                skipped.append(group)
                continue

        try:
            patch_text = hunks.render_patch_for_group(group, file_patches)
            git.unstage_all()
            git.apply_patch_cached(patch_text)
            git.commit(msg)
            committed += 1
            console.print(f"[green]✓ Committed group {i}.[/green]")
        except (ValueError, RuntimeError) as exc:
            console.print(f"[red]Commit failed:[/red] {exc}")
            # Restore the remaining hunks so the user isn't left with a broken index.
            _restage_remaining_hunks(skipped + remaining_groups[i - 1 :], file_patches)
            return

    if skipped:
        _restage_remaining_hunks(skipped, file_patches)
        console.print(
            f"[yellow]{len(skipped)} group(s) skipped.[/yellow] Re-staged their hunks."
        )
    console.print(f"\n[bold green]Done.[/bold green] {committed} commit(s) created.")


def _restage_remaining_hunks(
    groups: list[hunks.HunkGroup],
    file_patches: list[hunks.FilePatch],
) -> None:
    """Reset the index and re-apply hunks from the given groups."""
    if not groups:
        return
    git.unstage_all()
    for group in groups:
        try:
            patch = hunks.render_patch_for_group(group, file_patches)
            if patch:
                git.apply_patch_cached(patch)
        except (ValueError, RuntimeError):
            # Best-effort: skip un-applicable patches but keep going.
            continue


def _print_hunk_group_panel(
    group: hunks.HunkGroup,
    file_patches: list[hunks.FilePatch],
    i: int,
    total: int,
) -> None:
    msg = group.message or "[dim italic](no message — you'll need to edit)[/dim italic]"
    by_file: dict[str, list[int]] = {}
    for ref in group.refs:
        by_file.setdefault(ref.path, []).append(ref.index)
    files_block = "\n".join(
        f"  {path}: {len(idxs)} hunk(s)" for path, idxs in by_file.items()
    )
    title = f"Group {i}/{total} · {len(group.refs)} hunk(s)"
    if group.rationale:
        title += f" · {group.rationale}"
    console.print(
        Panel(f"{msg}\n\n[dim]Hunks:[/dim]\n{files_block}", title=title, border_style="cyan")
    )


def _resolve_issue_context(issue_num: int | None, no_issue: bool) -> str | None:
    """Resolve --issue / auto-detect / --no-issue into a prompt-ready context block.

    Order:
      1. If --no-issue, return None.
      2. If --issue N was passed, fetch N (warn if gh fails).
      3. Otherwise, try detecting N from the current branch (silent on miss).
    """
    if no_issue:
        return None
    if issue_num is not None:
        ctx = issue.fetch_issue_context(issue_num)
        if not ctx:
            console.print(
                f"[yellow]Could not fetch issue #{issue_num} "
                "(is `gh` installed and authenticated?).[/yellow]"
            )
        return ctx
    detected = issue.detect_issue_from_branch()
    if detected is None:
        return None
    ctx = issue.fetch_issue_context(detected)
    if ctx:
        console.print(
            f"[dim]Loaded context from auto-detected issue #{detected} "
            "(use --no-issue to skip).[/dim]"
        )
    return ctx


def _append_coauthor(message: str) -> str:
    """Append a Co-Authored-By trailer if one is configured. No-op otherwise."""
    if not message:
        return message
    trailer = config.coauthor_trailer()
    if not trailer:
        return message
    if "Co-Authored-By:" in message:
        return message
    return f"{message.rstrip()}\n\nCo-Authored-By: {trailer}"


def _print_group_panel(group: splitter.CommitGroup, i: int, total: int) -> None:
    msg = group.message or "[dim italic](no message — you'll need to edit)[/dim italic]"
    title = f"Group {i}/{total} · {len(group.files)} file(s)"
    if group.rationale:
        title += f" · {group.rationale}"
    files_block = "\n".join(f"  {f}" for f in group.files)
    console.print(
        Panel(f"{msg}\n\n[dim]Files:[/dim]\n{files_block}", title=title, border_style="cyan")
    )


def _edit_in_editor(initial: str) -> str:
    """Open $EDITOR (or vim) to edit the message; return the result."""
    import tempfile

    editor = os.environ.get("EDITOR", "vim")
    with tempfile.NamedTemporaryFile("w+", suffix=".COMMIT_MSG", delete=False) as fh:
        fh.write(initial)
        path = fh.name
    try:
        result = subprocess.run([*shlex.split(editor), path], check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Editor exited with status {result.returncode}.")
        with open(path) as fh:
            return fh.read().strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def main() -> None:
    app()


if __name__ == "__main__":
    main()
