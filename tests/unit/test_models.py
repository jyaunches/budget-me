"""Tests for SQLAlchemy ORM models."""

from budget_me.db.models import (
    CreditLiabilityApr,
    IngestRun,
    IngestRunItem,
    IngestRunItemStatus,
    IngestRunStatus,
    IngestRunType,
    MerchantMap,
    MerchantRule,
    PlaidCursor,
    PlaidItem,
    PlaidItemStatus,
    Transaction,
)


class TestPlaidItem:
    """Tests for PlaidItem model."""

    def test_plaid_item_status_enum_values(self):
        """PlaidItemStatus has expected enum values."""
        assert PlaidItemStatus.ACTIVE == "active"
        assert PlaidItemStatus.RELINK_REQUIRED == "relink_required"
        assert PlaidItemStatus.REVOKED == "revoked"
        assert PlaidItemStatus.PENDING == "pending"

    def test_plaid_item_has_required_columns(self):
        """PlaidItem model has all required columns."""
        columns = PlaidItem.__table__.columns.keys()

        assert "id" in columns
        assert "user_key" in columns
        assert "item_id" in columns
        assert "institution_id" in columns
        assert "access_token_enc" in columns
        assert "status" in columns
        assert "last_success_at" in columns
        assert "last_error_at" in columns
        assert "last_error_code" in columns
        assert "last_error_message" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_plaid_item_status_default(self):
        """PlaidItem status defaults to ACTIVE."""
        status_column = PlaidItem.__table__.c.status
        assert status_column.default.arg == PlaidItemStatus.ACTIVE


class TestPlaidCursor:
    """Tests for PlaidCursor model."""

    def test_plaid_cursor_has_required_columns(self):
        """PlaidCursor has required columns."""
        columns = PlaidCursor.__table__.columns.keys()

        assert "plaid_item_id" in columns
        assert "transactions_cursor" in columns
        assert "updated_at" in columns

    def test_plaid_cursor_plaid_item_id_is_primary_key(self):
        """plaid_item_id is the primary key."""
        pk_cols = [c.name for c in PlaidCursor.__table__.primary_key.columns]
        assert pk_cols == ["plaid_item_id"]


class TestTransaction:
    """Tests for Transaction model."""

    def test_transaction_has_required_columns(self):
        """Transaction has all required columns."""
        columns = Transaction.__table__.columns.keys()

        assert "id" in columns
        assert "plaid_transaction_id" in columns
        assert "plaid_item_id" in columns
        assert "account_id" in columns
        assert "date" in columns
        assert "authorized_date" in columns
        assert "amount" in columns
        assert "iso_currency_code" in columns
        assert "name" in columns
        assert "merchant_name" in columns
        assert "pending" in columns
        assert "payment_channel" in columns
        assert "category_primary" in columns
        assert "category_detailed" in columns
        assert "merchant_id" in columns
        assert "normalized_merchant" in columns
        assert "raw" in columns

    def test_transaction_plaid_transaction_id_is_unique(self):
        """plaid_transaction_id has unique constraint."""
        col = Transaction.__table__.c.plaid_transaction_id
        assert col.unique is True

    def test_transaction_has_indexes(self):
        """Transaction has expected indexes."""
        index_names = [idx.name for idx in Transaction.__table__.indexes]

        assert "ix_transactions_date" in index_names
        assert "ix_transactions_plaid_item_id_date" in index_names
        assert "ix_transactions_account_id" in index_names


class TestMerchantRule:
    """Tests for MerchantRule model."""

    def test_merchant_rule_has_required_columns(self):
        """MerchantRule has required columns."""
        columns = MerchantRule.__table__.columns.keys()

        assert "id" in columns
        assert "pattern" in columns
        assert "replacement" in columns
        assert "priority" in columns
        assert "enabled" in columns

    def test_merchant_rule_enabled_default(self):
        """enabled defaults to True."""
        col = MerchantRule.__table__.c.enabled
        assert col.default.arg is True


class TestMerchantMap:
    """Tests for MerchantMap model."""

    def test_merchant_map_has_required_columns(self):
        """MerchantMap has required columns."""
        columns = MerchantMap.__table__.columns.keys()

        assert "input_name" in columns
        assert "normalized" in columns
        assert "updated_at" in columns

    def test_merchant_map_input_name_is_primary_key(self):
        """input_name is the primary key."""
        pk_cols = [c.name for c in MerchantMap.__table__.primary_key.columns]
        assert pk_cols == ["input_name"]


class TestIngestRun:
    """Tests for IngestRun model."""

    def test_ingest_run_type_enum_values(self):
        """IngestRunType has expected enum values."""
        assert IngestRunType.SCHEDULED == "scheduled"
        assert IngestRunType.MANUAL == "manual"
        assert IngestRunType.WEBHOOK == "webhook"

    def test_ingest_run_status_enum_values(self):
        """IngestRunStatus has expected enum values."""
        assert IngestRunStatus.RUNNING == "running"
        assert IngestRunStatus.COMPLETED == "completed"
        assert IngestRunStatus.FAILED == "failed"
        assert IngestRunStatus.PARTIAL == "partial"

    def test_ingest_run_has_required_columns(self):
        """IngestRun has required columns."""
        columns = IngestRun.__table__.columns.keys()

        assert "id" in columns
        assert "started_at" in columns
        assert "ended_at" in columns
        assert "run_type" in columns
        assert "status" in columns
        assert "items_total" in columns
        assert "items_ok" in columns
        assert "items_failed" in columns
        assert "tx_added" in columns
        assert "tx_modified" in columns
        assert "tx_removed" in columns
        assert "error_summary" in columns


class TestIngestRunItem:
    """Tests for IngestRunItem model."""

    def test_ingest_run_item_status_enum_values(self):
        """IngestRunItemStatus has expected enum values."""
        assert IngestRunItemStatus.PENDING == "pending"
        assert IngestRunItemStatus.SUCCESS == "success"
        assert IngestRunItemStatus.FAILED == "failed"
        assert IngestRunItemStatus.SKIPPED == "skipped"

    def test_ingest_run_item_has_required_columns(self):
        """IngestRunItem has required columns."""
        columns = IngestRunItem.__table__.columns.keys()

        assert "id" in columns
        assert "ingest_run_id" in columns
        assert "plaid_item_id" in columns
        assert "status" in columns
        assert "tx_added" in columns
        assert "tx_modified" in columns
        assert "tx_removed" in columns
        assert "error_code" in columns
        assert "error_message" in columns
        assert "duration_ms" in columns


class TestRelationships:
    """Tests for model relationships."""

    def test_plaid_item_has_cursor_relationship(self):
        """PlaidItem has cursor relationship."""
        assert hasattr(PlaidItem, "cursor")

    def test_plaid_item_has_transactions_relationship(self):
        """PlaidItem has transactions relationship."""
        assert hasattr(PlaidItem, "transactions")

    def test_plaid_item_has_ingest_run_items_relationship(self):
        """PlaidItem has ingest_run_items relationship."""
        assert hasattr(PlaidItem, "ingest_run_items")

    def test_ingest_run_has_run_items_relationship(self):
        """IngestRun has run_items relationship."""
        assert hasattr(IngestRun, "run_items")

    def test_ingest_run_item_has_ingest_run_relationship(self):
        """IngestRunItem has ingest_run relationship."""
        assert hasattr(IngestRunItem, "ingest_run")

    def test_ingest_run_item_has_plaid_item_relationship(self):
        """IngestRunItem has plaid_item relationship."""
        assert hasattr(IngestRunItem, "plaid_item")


class TestCreditLiabilityApr:
    """Tests for CreditLiabilityApr model."""

    def test_credit_liability_apr_new_fields_exist(self):
        """CreditLiabilityApr model has new promotional APR tracking fields."""
        columns = CreditLiabilityApr.__table__.columns.keys()

        assert "promo_rate_end_date" in columns
        assert "promo_offer_id" in columns
        assert "source" in columns

    def test_credit_liability_apr_defaults(self):
        """CreditLiabilityApr has correct default values for new fields."""
        # Check source column has server_default
        source_column = CreditLiabilityApr.__table__.c.source
        assert source_column.server_default is not None
        assert source_column.server_default.arg == "plaid"

        # Check nullable fields
        promo_end_date_column = CreditLiabilityApr.__table__.c.promo_rate_end_date
        assert promo_end_date_column.nullable is True

        promo_offer_id_column = CreditLiabilityApr.__table__.c.promo_offer_id
        assert promo_offer_id_column.nullable is True
