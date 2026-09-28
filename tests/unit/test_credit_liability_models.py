"""Tests for CreditLiability and CreditLiabilityApr models."""

from budget_me.db.models.credit_liability import (
    AprType,
    CreditLiability,
    CreditLiabilityApr,
)


class TestAprTypeEnum:
    """Tests for AprType Enum."""

    def test_apr_type_enum_has_all_values(self):
        """AprType Enum has all required values."""
        assert hasattr(AprType, "BALANCE_TRANSFER")
        assert hasattr(AprType, "CASH")
        assert hasattr(AprType, "PURCHASE")
        assert hasattr(AprType, "SPECIAL")

        # Verify string values match Plaid API
        assert AprType.BALANCE_TRANSFER.value == "balance_transfer_apr"
        assert AprType.CASH.value == "cash_apr"
        assert AprType.PURCHASE.value == "purchase_apr"
        assert AprType.SPECIAL.value == "special"


class TestCreditLiabilityModel:
    """Tests for CreditLiability model structure."""

    def test_credit_liability_model_has_required_fields(self):
        """CreditLiability model has all required fields."""
        assert hasattr(CreditLiability, "id")
        assert hasattr(CreditLiability, "plaid_item_id")
        assert hasattr(CreditLiability, "account_id")
        assert hasattr(CreditLiability, "is_overdue")
        assert hasattr(CreditLiability, "last_payment_amount")
        assert hasattr(CreditLiability, "last_payment_date")
        assert hasattr(CreditLiability, "last_statement_balance")
        assert hasattr(CreditLiability, "last_statement_issue_date")
        assert hasattr(CreditLiability, "minimum_payment_amount")
        assert hasattr(CreditLiability, "next_payment_due_date")
        assert hasattr(CreditLiability, "created_at")
        assert hasattr(CreditLiability, "updated_at")

    def test_credit_liability_has_aprs_relationship(self):
        """CreditLiability has aprs relationship."""
        assert hasattr(CreditLiability, "aprs")
        # Verify it's a relationship attribute
        assert "aprs" in CreditLiability.__mapper__.relationships

    def test_credit_liability_has_plaid_item_relationship(self):
        """CreditLiability has plaid_item relationship."""
        assert hasattr(CreditLiability, "plaid_item")
        # Verify it's a relationship attribute
        assert "plaid_item" in CreditLiability.__mapper__.relationships


class TestCreditLiabilityAprModel:
    """Tests for CreditLiabilityApr model structure."""

    def test_credit_liability_apr_model_has_required_fields(self):
        """CreditLiabilityApr model has all required fields."""
        assert hasattr(CreditLiabilityApr, "id")
        assert hasattr(CreditLiabilityApr, "credit_liability_id")
        assert hasattr(CreditLiabilityApr, "apr_type")
        assert hasattr(CreditLiabilityApr, "apr_percentage")
        assert hasattr(CreditLiabilityApr, "balance_subject_to_apr")
        assert hasattr(CreditLiabilityApr, "interest_charge_amount")
