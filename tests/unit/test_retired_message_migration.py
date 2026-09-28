"""Tests for the retired inbound-message storage migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_migration():
    migration_path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "2026_07_30_0100_drop_legacy_message_storage.py"
    )
    spec = importlib.util.spec_from_file_location(
        "drop_legacy_message_storage", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_follows_rls_head_and_uses_idempotent_drop():
    migration = _load_migration()

    assert migration.revision == "d4a7e9c2f610"
    assert migration.down_revision == "a38d91f0c4e2"
    assert migration.DROP_LEGACY_MESSAGE_SQL == (
        'DROP TABLE IF EXISTS public."whatsapp_messages" CASCADE'
    )


def test_upgrade_drops_legacy_storage_and_downgrade_is_noop():
    migration = _load_migration()
    executed = []
    migration.op = SimpleNamespace(execute=executed.append)

    migration.upgrade()
    assert executed == [migration.DROP_LEGACY_MESSAGE_SQL]

    executed.clear()
    assert migration.downgrade() is None
    assert executed == []
