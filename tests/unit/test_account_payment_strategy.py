"""Unit tests for Account model payment strategy fields."""

from budget_me.db.models.account import Account, PaymentStrategy


class TestAccountPaymentStrategy:
    """Tests for payment strategy additions to Account model."""

    def test_account_payment_strategy_enum_values(self):
        """Verify PaymentStrategy enum has correct values."""
        assert PaymentStrategy.PAY_IN_FULL == "pay_in_full"
        assert PaymentStrategy.PROMOTIONAL_PAYDOWN == "promotional_paydown"

    def test_account_has_payment_strategy_column(self):
        """Verify payment_strategy column exists."""
        column_names = {col.name for col in Account.__table__.columns}
        assert "payment_strategy" in column_names

    def test_account_payment_strategy_defaults_to_pay_in_full(self):
        """Verify payment_strategy defaults to PAY_IN_FULL."""
        payment_strategy_column = Account.__table__.c.payment_strategy
        assert payment_strategy_column.default is not None
        assert payment_strategy_column.default.arg == PaymentStrategy.PAY_IN_FULL

    def test_account_has_fixed_payment_amount_column(self):
        """Verify fixed_payment_amount column exists."""
        column_names = {col.name for col in Account.__table__.columns}
        assert "fixed_payment_amount" in column_names

    def test_account_fixed_payment_amount_is_nullable(self):
        """Verify fixed_payment_amount is nullable."""
        fixed_payment_amount_column = Account.__table__.c.fixed_payment_amount
        assert fixed_payment_amount_column.nullable is True
