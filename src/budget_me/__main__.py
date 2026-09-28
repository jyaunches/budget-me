"""Entry point for the budget_me CLI application."""

from budget_me.cli.main import app


def main() -> None:
    """Run the CLI application."""
    app()


if __name__ == "__main__":
    main()
