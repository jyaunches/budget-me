"""Tests for the local disposable restore-target identity guard."""

import os
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.engine import make_url
from typer.testing import CliRunner

from budget_me.cli.commands import restore_target
from budget_me.cli.commands.restore_target import DatabaseFingerprint
from budget_me.cli.main import app

runner = CliRunner()

LIVE_URL = "postgresql+psycopg2://live_user:live-secret@db.example:5432/live_budget"
RESTORE_URL = (
    "postgresql+asyncpg://restore_user:restore-secret@127.0.0.1:55432/"
    "budget_restore_test"
)
EXPECTED_DATABASE = "budget_restore_test"
LIVE_FINGERPRINT = DatabaseFingerprint("live_budget", "10.0.0.12", 5432)
RESTORE_FINGERPRINT = DatabaseFingerprint(
    EXPECTED_DATABASE,
    "127.0.0.1",
    55432,
)


def _set_target_environment(monkeypatch, live=LIVE_URL, restore=RESTORE_URL):
    if live is None:
        monkeypatch.delenv(restore_target.LIVE_DATABASE_ENV, raising=False)
    else:
        monkeypatch.setenv(restore_target.LIVE_DATABASE_ENV, live)
    if restore is None:
        monkeypatch.delenv(restore_target.RESTORE_DATABASE_ENV, raising=False)
    else:
        monkeypatch.setenv(restore_target.RESTORE_DATABASE_ENV, restore)


def _run_args(expected_database=EXPECTED_DATABASE):
    return [
        "restore-target",
        "run",
        "--expected-database",
        expected_database,
        "--",
        "worker",
        "--mode",
        "check",
    ]


@pytest.mark.parametrize(
    ("live", "restore", "expected_database"),
    [
        (None, RESTORE_URL, EXPECTED_DATABASE),
        (LIVE_URL, None, EXPECTED_DATABASE),
        ("sqlite:///live_budget", RESTORE_URL, EXPECTED_DATABASE),
        (
            LIVE_URL,
            "mysql://user:secret@localhost/budget_restore_test",
            EXPECTED_DATABASE,
        ),
        (f"{LIVE_URL}?sslmode=require", RESTORE_URL, EXPECTED_DATABASE),
        (LIVE_URL, f"{RESTORE_URL}?sslmode=disable", EXPECTED_DATABASE),
        ("postgresql://user:secret@db.example", RESTORE_URL, EXPECTED_DATABASE),
        (LIVE_URL, "postgresql://user:secret@localhost", EXPECTED_DATABASE),
        (RESTORE_URL, RESTORE_URL, EXPECTED_DATABASE),
        (
            LIVE_URL,
            "postgresql://user:secret@restore.example/budget_restore_test",
            EXPECTED_DATABASE,
        ),
        (LIVE_URL, RESTORE_URL, "budget_test"),
        (LIVE_URL, RESTORE_URL, "different_restore_test"),
    ],
)
def test_run_rejects_invalid_urls_before_connect_or_exec(
    monkeypatch,
    live,
    restore,
    expected_database,
):
    _set_target_environment(monkeypatch, live, restore)
    read_fingerprint = MagicMock()
    execute = MagicMock()
    monkeypatch.setattr(restore_target, "_read_fingerprint", read_fingerprint)
    monkeypatch.setattr(restore_target.os, "execvpe", execute)

    result = runner.invoke(app, _run_args(expected_database))

    assert result.exit_code == 1
    assert result.output == "Restore target verification failed.\n"
    read_fingerprint.assert_not_called()
    execute.assert_not_called()
    for secret in ("live-secret", "restore-secret", LIVE_URL, RESTORE_URL):
        assert secret not in result.output


@pytest.mark.parametrize(
    "fingerprints",
    [
        [
            DatabaseFingerprint("unexpected_live", "10.0.0.12", 5432),
            RESTORE_FINGERPRINT,
        ],
        [
            LIVE_FINGERPRINT,
            DatabaseFingerprint("unexpected_restore", "127.0.0.1", 55432),
        ],
    ],
)
def test_run_rejects_unexpected_actual_database_before_exec(
    monkeypatch,
    fingerprints,
):
    _set_target_environment(monkeypatch)
    execute = MagicMock()
    monkeypatch.setattr(
        restore_target,
        "_read_fingerprint",
        MagicMock(side_effect=fingerprints),
    )
    monkeypatch.setattr(restore_target.os, "execvpe", execute)

    result = runner.invoke(app, _run_args())

    assert result.exit_code == 1
    assert result.output == "Restore target verification failed.\n"
    execute.assert_not_called()


def test_run_rejects_identical_server_fingerprints_before_exec(monkeypatch):
    shared_database_url = "postgresql://live:secret@db.example:5432/budget_restore_test"
    _set_target_environment(monkeypatch, live=shared_database_url)
    fingerprint = DatabaseFingerprint(EXPECTED_DATABASE, "127.0.0.1", 55432)
    execute = MagicMock()
    monkeypatch.setattr(
        restore_target,
        "_read_fingerprint",
        MagicMock(side_effect=[fingerprint, fingerprint]),
    )
    monkeypatch.setattr(restore_target.os, "execvpe", execute)

    result = runner.invoke(app, _run_args())

    assert result.exit_code == 1
    assert result.output == "Restore target verification failed.\n"
    execute.assert_not_called()


def test_verify_connects_read_only_and_reports_only_pass(monkeypatch):
    _set_target_environment(monkeypatch)
    live_connection = MagicMock()
    restore_connection = MagicMock()
    live_cursor = MagicMock()
    restore_cursor = MagicMock()
    live_cursor.fetchone.return_value = ("live_budget", "10.0.0.12", 5432)
    restore_cursor.fetchone.return_value = (
        EXPECTED_DATABASE,
        "127.0.0.1",
        55432,
    )
    live_connection.cursor.return_value.__enter__.return_value = live_cursor
    restore_connection.cursor.return_value.__enter__.return_value = restore_cursor
    connect = MagicMock(side_effect=[live_connection, restore_connection])
    monkeypatch.setattr(restore_target.psycopg2, "connect", connect)

    result = runner.invoke(
        app,
        [
            "restore-target",
            "verify",
            "--expected-database",
            EXPECTED_DATABASE,
        ],
    )

    assert result.exit_code == 0
    assert result.output == "Restore target verification passed.\n"
    assert connect.call_count == 2
    live_connection.set_session.assert_called_once_with(
        readonly=True,
        autocommit=True,
    )
    restore_connection.set_session.assert_called_once_with(
        readonly=True,
        autocommit=True,
    )
    live_cursor.execute.assert_called_once_with(restore_target._VERIFY_QUERY)
    restore_cursor.execute.assert_called_once_with(restore_target._VERIFY_QUERY)
    live_connection.close.assert_called_once_with()
    restore_connection.close.assert_called_once_with()
    assert EXPECTED_DATABASE not in result.output
    assert "127.0.0.1" not in result.output


def test_connection_error_is_sanitized_and_never_execs(monkeypatch):
    _set_target_environment(monkeypatch)
    execute = MagicMock()
    monkeypatch.setattr(
        restore_target.psycopg2,
        "connect",
        MagicMock(side_effect=RuntimeError(f"connection failed: {LIVE_URL}")),
    )
    monkeypatch.setattr(restore_target.os, "execvpe", execute)

    result = runner.invoke(app, _run_args())

    assert result.exit_code == 1
    assert result.output == "Restore target verification failed.\n"
    assert LIVE_URL not in result.output
    assert "live-secret" not in result.output
    execute.assert_not_called()


def test_run_execs_exact_command_with_verified_restore_environment():
    inherited_environment = {
        "KEEP_ME": "yes",
        "DATABASE_URL": "postgresql://wrong:secret@wrong.example/wrong",
        restore_target.LIVE_DATABASE_ENV: LIVE_URL,
        restore_target.RESTORE_DATABASE_ENV: RESTORE_URL,
    }
    command = ["worker", "--mode", "check", "--unknown-option=value"]
    with (
        patch.dict(os.environ, inherited_environment, clear=True),
        patch.object(
            restore_target,
            "_read_fingerprint",
            side_effect=[LIVE_FINGERPRINT, RESTORE_FINGERPRINT],
        ),
        patch.object(restore_target.os, "execvpe") as execute,
    ):
        result = runner.invoke(
            app,
            [
                "restore-target",
                "run",
                "--expected-database",
                EXPECTED_DATABASE,
                "--",
                *command,
            ],
        )

    assert result.exit_code == 0
    execute.assert_called_once_with(
        command[0],
        command,
        {
            "KEEP_ME": "yes",
            "DATABASE_URL": RESTORE_URL,
            "BUDGET_ME_DISABLE_DOTENV": "1",
        },
    )
    assert result.output == ""


def test_run_requires_trailing_command_before_verification(monkeypatch):
    _set_target_environment(monkeypatch)
    verify = MagicMock()
    execute = MagicMock()
    monkeypatch.setattr(restore_target, "_verify_target", verify)
    monkeypatch.setattr(restore_target.os, "execvpe", execute)

    result = runner.invoke(
        app,
        [
            "restore-target",
            "run",
            "--expected-database",
            EXPECTED_DATABASE,
            "--",
        ],
    )

    assert result.exit_code == 1
    assert result.output == "Restore target verification failed.\n"
    verify.assert_not_called()
    execute.assert_not_called()


def test_verify_requires_expected_database_with_sanitized_output(monkeypatch):
    _set_target_environment(monkeypatch)
    read_fingerprint = MagicMock()
    monkeypatch.setattr(restore_target, "_read_fingerprint", read_fingerprint)

    result = runner.invoke(app, ["restore-target", "verify"])

    assert result.exit_code == 1
    assert result.output == "Restore target verification failed.\n"
    read_fingerprint.assert_not_called()


def test_exec_error_is_sanitized(monkeypatch):
    _set_target_environment(monkeypatch)
    monkeypatch.setattr(
        restore_target,
        "_read_fingerprint",
        MagicMock(side_effect=[LIVE_FINGERPRINT, RESTORE_FINGERPRINT]),
    )
    monkeypatch.setattr(
        restore_target.os,
        "execvpe",
        MagicMock(side_effect=OSError(f"could not execute with {RESTORE_URL}")),
    )

    result = runner.invoke(app, _run_args())

    assert result.exit_code == 1
    assert result.output == "Restore target verification failed.\n"
    assert RESTORE_URL not in result.output
    assert "restore-secret" not in result.output


def test_read_fingerprint_rejects_incomplete_server_identity(monkeypatch):
    connection = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (EXPECTED_DATABASE, None, 5432)
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(
        restore_target.psycopg2,
        "connect",
        MagicMock(return_value=connection),
    )

    with pytest.raises(restore_target.RestoreTargetError):
        restore_target._read_fingerprint(make_url(RESTORE_URL))

    connection.close.assert_called_once_with()
