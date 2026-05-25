"""commitr: AI-generated git commit messages that match your project's style."""
from __future__ import annotations

import os

import questionary
import typer
from rich.console import Console
from rich.panel import Panel

from commitr import git, llm

app = typer.Typer(
    add_completion=False,
    help="Generate a git commit message from your staged diff using an LLM.",
    no_args_is_help=False,
)
console = Console()


@app.command()
def _run(
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="LLM model (litellm format). Defaults to $COMMITR_MODEL or gpt-4o-mini.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation, commit directly."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the message but do not commit."),
) -> None:
    """Generate a commit message from staged changes."""
    if not git.in_repo():
        console.print("[red]Not inside a git repository.[/red]")
        raise typer.Exit(code=1)

    if not git.has_staged_changes():
        console.print("[yellow]No staged changes. Run `git add` first.[/yellow]")
        raise typer.Exit(code=1)

    diff = git.staged_diff()
    subjects = git.recent_commits(limit=20)
    samples = git.recent_commit_samples(limit=5)

    with console.status("[cyan]Asking the model…[/cyan]"):
        try:
            message = llm.generate_commit_message(
                diff=diff, subjects=subjects, samples=samples, model=model,
            )
        except Exception as exc:
            console.print(f"[red]LLM call failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

    console.print(Panel(message, title="Proposed commit", border_style="cyan"))

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
                diff=diff, subjects=subjects, samples=samples, model=model,
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
