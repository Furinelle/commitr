"""commitr: AI-generated git commit messages that match your project's style."""
from __future__ import annotations

import os

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from commitr import config, git, llm

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
) -> None:
    """Default action (no subcommand): generate a commit message."""
    config.load_env_file()
    if ctx.invoked_subcommand is not None:
        return
    _run_commit(model=model, provider=provider, yes=yes, dry_run=dry_run)


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


def _run_commit(
    model: str | None,
    provider: str | None,
    yes: bool,
    dry_run: bool,
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
    subjects = git.recent_commits(limit=20)
    samples = git.recent_commit_samples(limit=5)

    with console.status(f"[cyan]Asking {resolved}…[/cyan]"):
        try:
            message = llm.generate_commit_message(
                diff=diff, subjects=subjects, samples=samples, model=resolved,
            )
        except Exception as exc:
            console.print(f"[red]LLM call failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

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


def _edit_in_editor(initial: str) -> str:
    """Open $EDITOR (or vim) to edit the message; return the result."""
    import tempfile

    editor = os.environ.get("EDITOR", "vim")
    with tempfile.NamedTemporaryFile("w+", suffix=".COMMIT_MSG", delete=False) as fh:
        fh.write(initial)
        path = fh.name
    try:
        os.system(f'{editor} "{path}"')  # noqa: S605
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
