"""Safety checks for Alembic environment loading."""

from pathlib import Path


def test_alembic_honors_dotenv_disable_guard() -> None:
    """Migration commands can be forced to use explicit environment values only."""
    env_source = (Path(__file__).parents[2] / "alembic" / "env.py").read_text(
        encoding="utf-8"
    )

    assert 'if os.environ.get("BUDGET_ME_DISABLE_DOTENV") != "1":' in env_source
    assert (
        'load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))'
        in env_source
    )
