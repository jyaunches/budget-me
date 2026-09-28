"""Fail-closed identity guard for local disposable restore databases."""

from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg2
import typer
from sqlalchemy.engine import URL, make_url

LIVE_DATABASE_ENV = "BUDGET_ME_LIVE_DATABASE_URL"
RESTORE_DATABASE_ENV = "BUDGET_ME_RESTORE_DATABASE_URL"
RESTORE_DATABASE_MARKER = "_restore_test"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_VERIFY_QUERY = (
    "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
)
_VERIFY_PASSED = "Restore target verification passed."
_VERIFY_FAILED = "Restore target verification failed."

restore_target_app = typer.Typer(
    name="restore-target",
    help="Verify and use a local disposable restore database.",
)


class RestoreTargetError(RuntimeError):
    """A deliberately detail-free restore-target verification failure."""


@dataclass(frozen=True)
class DatabaseFingerprint:
    """Database identity returned by PostgreSQL itself."""

    database: str
    server_address: str
    server_port: int


@dataclass(frozen=True)
class _ValidatedTargetURLs:
    live_raw: str
    live: URL
    restore_raw: str
    restore: URL


def _fail() -> None:
    typer.echo(_VERIFY_FAILED, err=True)
    raise typer.Exit(1)


def _parse_database_url(raw_url: str) -> URL:
    try:
        url = make_url(raw_url)
        backend = url.get_backend_name()
    except Exception:
        raise RestoreTargetError from None

    if backend not in {"postgres", "postgresql"}:
        raise RestoreTargetError
    if url.query or not url.database:
        raise RestoreTargetError
    return url


def _validate_target_urls(expected_database: str | None) -> _ValidatedTargetURLs:
    live_raw = os.environ.get(LIVE_DATABASE_ENV)
    restore_raw = os.environ.get(RESTORE_DATABASE_ENV)
    if not live_raw or not restore_raw:
        raise RestoreTargetError

    live = _parse_database_url(live_raw)
    restore = _parse_database_url(restore_raw)

    if live == restore:
        raise RestoreTargetError
    if not expected_database or RESTORE_DATABASE_MARKER not in expected_database:
        raise RestoreTargetError
    if restore.database != expected_database:
        raise RestoreTargetError
    if (restore.host or "").lower() not in _LOOPBACK_HOSTS:
        raise RestoreTargetError

    return _ValidatedTargetURLs(
        live_raw=live_raw,
        live=live,
        restore_raw=restore_raw,
        restore=restore,
    )


def _read_fingerprint(url: URL) -> DatabaseFingerprint:
    dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    connection = None
    try:
        connection = psycopg2.connect(dsn)
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute(_VERIFY_QUERY)
            row = cursor.fetchone()
        if (
            row is None
            or len(row) != 3
            or not isinstance(row[0], str)
            or not isinstance(row[1], str)
            or not isinstance(row[2], int)
        ):
            raise RestoreTargetError
        return DatabaseFingerprint(
            database=row[0],
            server_address=row[1],
            server_port=row[2],
        )
    except RestoreTargetError:
        raise
    except Exception:
        raise RestoreTargetError from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _verify_target(expected_database: str | None) -> _ValidatedTargetURLs:
    targets = _validate_target_urls(expected_database)
    live_fingerprint = _read_fingerprint(targets.live)
    restore_fingerprint = _read_fingerprint(targets.restore)

    if live_fingerprint.database != targets.live.database:
        raise RestoreTargetError
    if restore_fingerprint.database != expected_database:
        raise RestoreTargetError
    if live_fingerprint == restore_fingerprint:
        raise RestoreTargetError
    return targets


@restore_target_app.command("verify")
def verify_command(
    expected_database: str | None = typer.Option(
        None,
        "--expected-database",
        help="Required exact database name; must contain '_restore_test'.",
    ),
) -> None:
    """Verify configured live and local restore targets without printing identity."""
    try:
        _verify_target(expected_database)
    except RestoreTargetError:
        _fail()
    typer.echo(_VERIFY_PASSED)


@restore_target_app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run_command(
    ctx: typer.Context,
    expected_database: str | None = typer.Option(
        None,
        "--expected-database",
        help="Required exact database name; must contain '_restore_test'.",
    ),
) -> None:
    """Verify, then replace this process with the exact trailing command."""
    command = list(ctx.args)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        _fail()

    try:
        targets = _verify_target(expected_database)
    except RestoreTargetError:
        _fail()

    child_environment = os.environ.copy()
    child_environment.pop(LIVE_DATABASE_ENV, None)
    child_environment.pop(RESTORE_DATABASE_ENV, None)
    child_environment["DATABASE_URL"] = targets.restore_raw
    child_environment["BUDGET_ME_DISABLE_DOTENV"] = "1"
    try:
        os.execvpe(command[0], command, child_environment)
    except OSError:
        _fail()
