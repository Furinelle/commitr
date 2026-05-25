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

from commitr import config, doctor, git, hook, llm, splitter, style


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
    _run_commit(model=model, provider=provider, yes=yes, dry_run=dry_run, split=split)


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
        diff = git.staged_diff()
        subjects = git.recent_commits(limit=20)
        samples = git.recent_commit_samples(limit=5)
        message = llm.generate_commit_message(
            diff=diff, subjects=subjects, samples=samples, model=resolved,
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
    diff = git.staged_diff() if files else ""
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

    diff = git.staged_diff()
    files = git.staged_files()
    subjects = git.recent_commits(limit=20)
    samples = git.recent_commit_samples(limit=5)

    # Doctor preflight: surface deterministic issues before burning an API call.
    findings = doctor.analyze_staged_changes(diff=diff, files=files)
    if findings:
        for f in findings:
            color = {"error": "red", "warning": "yellow"}.get(f.level, "cyan")
            console.print(f"[{color}]{f.level}[/{color}] {f.code}: {f.message}")
        if doctor.overall_status(findings) == "error":
            raise typer.Exit(code=1)

    if split:
        _split_flow(diff, subjects, samples, resolved, dry_run=dry_run, yes=yes)
        return

    with console.status(f"[cyan]Asking {resolved}…[/cyan]"):
        try:
            message = llm.generate_commit_message(
                diff=diff, subjects=subjects, samples=samples, model=resolved,
            )
        except Exception as exc:
            console.print(f"[red]LLM call failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

    message = _append_coauthor(message)
    console.print(Panel(message, title=f"Proposed commit (via {resolved})", border_style="cyan"))

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
            message = llm.generate_commit_message(
                diff=diff, subjects=subjects, samples=samples, model=resolved,
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


def _split_flow(
    diff: str,
    subjects: list[str],
    samples: list[str],
    resolved: str,
    dry_run: bool,
    yes: bool = False,
) -> None:
    """Multi-commit split: ask LLM to group files, then commit each group."""
    files = git.staged_files()
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
                git.stage_only(remaining)
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
            git.stage_only(group.files)
            git.commit(msg)
            committed += 1
            console.print(f"[green]✓ Committed group {i}.[/green]")
        except (ValueError, RuntimeError) as exc:
            console.print(f"[red]Commit failed:[/red] {exc}")
            return

    if skipped:
        skipped_files = [f for g in skipped for f in g.files]
        git.stage_only(skipped_files)
        console.print(
            f"[yellow]{len(skipped)} group(s) skipped.[/yellow] "
            f"Re-staged {len(skipped_files)} file(s) for follow-up."
        )
    console.print(f"\n[bold green]Done.[/bold green] {committed} commit(s) created.")


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
