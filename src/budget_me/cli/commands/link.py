"""Link command - start Plaid Link server."""

import warnings
import webbrowser

import typer
from rich.console import Console

from budget_me.server.link_server import start_link_server

console = Console()


def link_command():
    """Start the Plaid Link server to connect a bank account.

    This will:
    1. Start a local web server on port 8080
    2. Open your browser to the Link flow
    3. Allow you to connect a bank account
    4. Store the connection securely

    Press Ctrl+C to stop the server when done.
    """
    warnings.warn(
        "The 'budget-me link' command is deprecated. "
        "Use the Streamlit app's Link Account page instead: "
        "uv run streamlit run src/budget_me/streamlit_app/app.py",
        DeprecationWarning,
        stacklevel=2,
    )

    console.print("\n[bold green]Starting Plaid Link Server...[/bold green]")
    console.print("\nThe server will start on [bold]http://localhost:8080[/bold]")
    console.print("Opening your browser...")
    console.print("\n[dim]Press Ctrl+C to stop the server when you're done[/dim]\n")

    try:
        # Open browser to the link server
        webbrowser.open("http://localhost:8080")

        # Start the server (blocks until Ctrl+C)
        start_link_server()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Server stopped.[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
