"""Synchronous database layer for Streamlit app.

Streamlit runs synchronously, so we need a sync database layer
instead of the async one used by the main application.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from budget_me.config import get_settings
from budget_me.db.models.account import Account
from budget_me.db.models.account_balance_snapshot import AccountBalanceSnapshot
from budget_me.db.models.anticipated_item import AnticipatedItem
from budget_me.db.models.category_budget import CategoryBudget
from budget_me.db.models.credit_liability import CreditLiability, CreditLiabilityApr
from budget_me.db.models.loan_details import LoanDetails
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.plaid_item import PlaidItem
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.models.transaction import Transaction


def get_sync_engine() -> Engine:
    """Create a synchronous SQLAlchemy engine.

    Converts the asyncpg URL to psycopg2 for sync access.
    """
    settings = get_settings()
    async_url = settings.active_database_url

    # Convert from asyncpg to psycopg2
    sync_url = async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    return create_engine(sync_url, echo=False)


# Module-level engine (lazy initialization)
_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def _get_engine() -> Engine:
    """Get or create the module-level engine."""
    global _engine
    if _engine is None:
        _engine = get_sync_engine()
    return _engine


def _get_session_factory() -> sessionmaker:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=_get_engine())
    return _session_factory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a sync database session."""
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Transaction type categories based on Plaid's personal_finance_category
TRANSFER_CATEGORIES = ("TRANSFER_IN", "TRANSFER_OUT")
PAYMENT_CATEGORIES = ("LOAN_PAYMENTS",)
INCOME_CATEGORIES = ("INCOME",)

# Map transaction type to SQL filter conditions
TYPE_TO_CATEGORIES = {
    "transfers": TRANSFER_CATEGORIES,
    "payments": PAYMENT_CATEGORIES,
    "income": INCOME_CATEGORIES,
}


def get_transactions(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: str | None = None,
    reviewed: bool | None = None,
    transaction_type: str | None = None,
    categorized: bool | None = None,
    budget_category: str | None = None,
    project_tag: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Query transactions with optional filters.

    Args:
        session: Database session
        start_date: Filter transactions on or after this date
        end_date: Filter transactions on or before this date
        account_id: Filter by specific account ID
        reviewed: Filter by reviewed status (True/False/None for all)
        transaction_type: Filter by type - "spending", "transfers", "payments", "income", or None for all
        categorized: Filter by categorization status (True=categorized, False=uncategorized, None=all)
        budget_category: Filter by specific budget category
        limit: Maximum number of transactions to return

    Returns:
        List of transaction dictionaries with account name joined
    """
    from sqlalchemy import and_, func, or_
    from sqlalchemy import text as sql_text

    # Build query with account join for display name
    # Use COALESCE to prefer display_name over name
    stmt = (
        select(
            Transaction.id,
            Transaction.date,
            Transaction.name,
            Transaction.merchant_name,
            Transaction.amount,
            Transaction.category_primary,
            Transaction.category_detailed,
            Transaction.account_id,
            Transaction.reviewed,
            Transaction.reviewed_at,
            Transaction.raw,
            Transaction.budget_category,
            Transaction.project_tag,
            func.coalesce(Account.display_name, Account.name).label("account_name"),
        )
        .outerjoin(Account, Transaction.account_id == Account.account_id)
        .order_by(Transaction.date.desc(), Transaction.id)
    )

    # Apply filters
    if start_date:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date:
        stmt = stmt.where(Transaction.date <= end_date)
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if reviewed is not None:
        stmt = stmt.where(Transaction.reviewed == reviewed)
    if categorized is not None:
        if categorized:
            # Categorized: budget_category IS NOT NULL
            stmt = stmt.where(Transaction.budget_category.is_not(None))
        else:
            # Uncategorized: budget_category IS NULL
            stmt = stmt.where(Transaction.budget_category.is_(None))
    if budget_category is not None:
        stmt = stmt.where(Transaction.budget_category == budget_category)
    if project_tag is not None:
        stmt = stmt.where(Transaction.project_tag == project_tag)

    # Filter by transaction type at SQL level using JSONB
    if transaction_type:
        if transaction_type == "spending":
            # Spending = NOT in any of the special categories
            all_special = TRANSFER_CATEGORIES + PAYMENT_CATEGORIES + INCOME_CATEGORIES
            conditions = [
                sql_text(f"raw->'personal_finance_category'->>'primary' != '{cat}'")
                for cat in all_special
            ]
            # Also include NULL categories as spending
            stmt = stmt.where(or_(Transaction.raw.is_(None), and_(*conditions)))
        else:
            # Specific type - match the categories
            categories = TYPE_TO_CATEGORIES.get(transaction_type, ())
            if categories:
                conditions = [
                    sql_text(f"raw->'personal_finance_category'->>'primary' = '{cat}'")
                    for cat in categories
                ]
                stmt = stmt.where(or_(*conditions))

    stmt = stmt.limit(limit)

    result = session.execute(stmt)
    rows = result.fetchall()

    # Process rows
    transactions = []
    for row in rows:
        # Extract primary category from raw JSON
        raw_category = None
        if row.raw and isinstance(row.raw, dict):
            pfc = row.raw.get("personal_finance_category", {})
            if isinstance(pfc, dict):
                raw_category = pfc.get("primary")

        # Determine transaction type for display
        if raw_category in TRANSFER_CATEGORIES:
            txn_type = "transfers"
        elif raw_category in PAYMENT_CATEGORIES:
            txn_type = "payments"
        elif raw_category in INCOME_CATEGORIES:
            txn_type = "income"
        else:
            txn_type = "spending"

        transactions.append(
            {
                "id": str(row.id),
                "date": row.date,
                "name": row.name,
                "merchant_name": row.merchant_name,
                "amount": float(row.amount),
                "category_primary": raw_category or row.category_primary,
                "category_detailed": row.category_detailed,
                "account_id": row.account_id,
                "account_name": row.account_name or row.account_id[:8] + "...",
                "reviewed": row.reviewed,
                "reviewed_at": row.reviewed_at,
                "transaction_type": txn_type,
                "budget_category": row.budget_category,
                "project_tag": row.project_tag,
            }
        )

    return transactions


def mark_reviewed(
    session: Session, transaction_ids: list[str], reviewed: bool = True
) -> int:
    """Mark transactions as reviewed or unreviewed.

    Args:
        session: Database session
        transaction_ids: List of transaction UUIDs to update
        reviewed: True to mark as reviewed, False to unmark

    Returns:
        Number of transactions updated
    """
    if not transaction_ids:
        return 0

    # Convert string IDs to UUIDs
    uuids = [UUID(tid) for tid in transaction_ids]

    stmt = (
        update(Transaction)
        .where(Transaction.id.in_(uuids))
        .values(
            reviewed=reviewed,
            reviewed_at=datetime.utcnow() if reviewed else None,
        )
    )

    result = session.execute(stmt)
    return result.rowcount


def set_project_tags(session: Session, tags_by_id: dict[str, str | None]) -> int:
    """Set (or clear) the cross-month project tag on transactions.

    Budget-neutral: project tags do not affect any budget, snapshot, or
    categorization calculation. They only roll up spending for a project
    (e.g. a trip or landscaping job) across months.

    Args:
        session: Database session
        tags_by_id: Mapping of transaction UUID (str) to tag. An empty string
            or None clears the tag.

    Returns:
        Number of transactions updated
    """
    updated = 0
    for tid, tag in tags_by_id.items():
        value = tag.strip() if isinstance(tag, str) and tag.strip() else None
        stmt = (
            update(Transaction)
            .where(Transaction.id == UUID(tid))
            .values(project_tag=value)
        )
        updated += session.execute(stmt).rowcount
    return updated


def get_project_tags(session: Session) -> list[str]:
    """Return the distinct project tags in use, ordered alphabetically."""
    stmt = (
        select(Transaction.project_tag)
        .where(Transaction.project_tag.is_not(None))
        .distinct()
        .order_by(Transaction.project_tag)
    )
    return [row[0] for row in session.execute(stmt).all()]


def get_accounts(session: Session, include_excluded: bool = False) -> list[dict]:
    """Get all accounts for filter dropdown.

    Args:
        session: Database session
        include_excluded: If False (default), filters out excluded accounts

    Returns:
        List of account dictionaries with id, name, display_name, and display string
    """
    stmt = select(
        Account.account_id,
        Account.name,
        Account.display_name,
        Account.type,
        Account.mask,
    )

    if not include_excluded:
        stmt = stmt.where(Account.is_excluded.is_(False))

    stmt = stmt.order_by(Account.name)

    result = session.execute(stmt)
    rows = result.fetchall()

    accounts = []
    for row in rows:
        # Use display_name if set, otherwise fall back to name
        shown_name = row.display_name or row.name
        display = f"{shown_name} ({row.type} ...{row.mask})" if row.mask else shown_name
        accounts.append(
            {
                "account_id": row.account_id,
                "name": row.name,
                "display_name": row.display_name,
                "type": row.type,
                "mask": row.mask,
                "display": display,
            }
        )
    return accounts


def get_all_accounts_with_details(session: Session) -> list[dict]:
    """Get all accounts with balances and institution info for accounts page.

    Returns:
        List of account dictionaries with all fields including display_name,
        balances, paying_account_id, and institution_id from the linked PlaidItem.
    """
    stmt = (
        select(
            Account.id,
            Account.account_id,
            Account.name,
            Account.display_name,
            Account.type,
            Account.subtype,
            Account.mask,
            Account.balance_current,
            Account.balance_available,
            Account.is_excluded,
            Account.paying_account_id,
            PlaidItem.institution_id,
        )
        .outerjoin(PlaidItem, Account.plaid_item_id == PlaidItem.id)
        .order_by(Account.name)
    )

    result = session.execute(stmt)
    rows = result.fetchall()

    return [
        {
            "id": str(row.id),
            "account_id": row.account_id,
            "name": row.name,
            "display_name": row.display_name,
            "type": row.type,
            "subtype": row.subtype,
            "mask": row.mask,
            "balance_current": float(row.balance_current)
            if row.balance_current
            else None,
            "balance_available": float(row.balance_available)
            if row.balance_available
            else None,
            "is_excluded": row.is_excluded,
            "paying_account_id": row.paying_account_id,
            "institution_id": row.institution_id,
        }
        for row in rows
    ]


def update_account_display_name(
    session: Session, account_id: str, display_name: str | None
) -> bool:
    """Update the display name for an account.

    Args:
        session: Database session
        account_id: The Plaid account_id to update
        display_name: The new display name, or None to clear it

    Returns:
        True if the account was found and updated, False otherwise
    """
    stmt = (
        update(Account)
        .where(Account.account_id == account_id)
        .values(display_name=display_name)
    )

    result = session.execute(stmt)
    return result.rowcount > 0


def update_account_excluded_status(
    session: Session, account_id: str, is_excluded: bool
) -> bool:
    """Update the excluded status for an account.

    Args:
        session: Database session
        account_id: The Plaid account_id to update
        is_excluded: Whether the account should be excluded from operations

    Returns:
        True if the account was found and updated, False otherwise
    """
    stmt = (
        update(Account)
        .where(Account.account_id == account_id)
        .values(is_excluded=is_excluded)
    )

    result = session.execute(stmt)
    return result.rowcount > 0


def update_paying_account(
    session: Session, account_id: str, paying_account_id: str | None
) -> bool:
    """Update the paying account for a credit card.

    Args:
        session: Database session
        account_id: The credit card account_id to update
        paying_account_id: The checking account that pays this card, or None to clear

    Returns:
        True if the account was found and updated, False otherwise
    """
    stmt = (
        update(Account)
        .where(Account.account_id == account_id)
        .values(paying_account_id=paying_account_id)
    )

    result = session.execute(stmt)
    return result.rowcount > 0


def get_transaction_stats(session: Session) -> dict:
    """Get transaction statistics for dashboard header.

    Returns:
        Dictionary with total, reviewed, and unreviewed counts
    """
    from sqlalchemy import func

    total_stmt = select(func.count(Transaction.id))
    reviewed_stmt = select(func.count(Transaction.id)).where(
        Transaction.reviewed.is_(True)
    )

    total = session.execute(total_stmt).scalar() or 0
    reviewed = session.execute(reviewed_stmt).scalar() or 0

    return {
        "total": total,
        "reviewed": reviewed,
        "unreviewed": total - reviewed,
    }


def get_budget_categories(session: Session) -> list[str]:
    """Get distinct budget categories from transactions.

    Returns:
        Sorted list of category names (excludes NULL)
    """
    stmt = (
        select(Transaction.budget_category)
        .where(Transaction.budget_category.is_not(None))
        .distinct()
        .order_by(Transaction.budget_category)
    )
    result = session.execute(stmt)
    return [row[0] for row in result.fetchall()]


def get_debt_with_aprs(session: Session) -> list[dict]:
    """Get credit liability data with APR details for debt overview page.

    Joins credit_liability_aprs -> credit_liabilities -> accounts.
    Returns one row per APR entry.

    Returns:
        List of dicts with account_name (using display_name fallback), mask,
        apr_type, apr_percentage, balance, and interest_charge
    """
    from sqlalchemy import func

    stmt = (
        select(
            func.coalesce(Account.display_name, Account.name).label("account_name"),
            Account.mask,
            CreditLiabilityApr.apr_type,
            CreditLiabilityApr.apr_percentage,
            CreditLiabilityApr.balance_subject_to_apr,
            CreditLiabilityApr.interest_charge_amount,
        )
        .join(
            CreditLiability,
            CreditLiabilityApr.credit_liability_id == CreditLiability.id,
        )
        .join(Account, CreditLiability.account_id == Account.account_id)
        .where(CreditLiabilityApr.balance_subject_to_apr > 0)
        .order_by(CreditLiabilityApr.balance_subject_to_apr.desc())
    )

    result = session.execute(stmt)
    rows = result.fetchall()

    return [
        {
            "account_name": row.account_name,
            "mask": row.mask,
            "apr_type": row.apr_type,
            "apr_percentage": float(row.apr_percentage),
            "balance": float(row.balance_subject_to_apr),
            "interest_charge": float(row.interest_charge_amount)
            if row.interest_charge_amount
            else 0.0,
        }
        for row in rows
    ]


def get_zero_percent_balance_schedule(session: Session) -> list[dict]:
    """Get positive 0% APR balances and their promotional end dates.

    Returns one row per promotional balance so cards with multiple offers are
    shown as separate payoff deadlines on the debt page.
    """
    stmt = (
        select(
            func.coalesce(Account.display_name, Account.name).label("account_name"),
            Account.mask,
            CreditLiabilityApr.balance_subject_to_apr,
            CreditLiabilityApr.promo_rate_end_date,
            CreditLiabilityApr.promo_offer_id,
        )
        .join(
            CreditLiability,
            CreditLiabilityApr.credit_liability_id == CreditLiability.id,
        )
        .join(Account, CreditLiability.account_id == Account.account_id)
        .where(
            CreditLiabilityApr.apr_percentage == 0,
            CreditLiabilityApr.balance_subject_to_apr > 0,
            Account.is_excluded.is_(False),
        )
        .order_by(
            CreditLiabilityApr.promo_rate_end_date.asc().nullslast(),
            Account.name,
        )
    )

    rows = session.execute(stmt).fetchall()
    return [
        {
            "account_name": row.account_name,
            "mask": row.mask,
            "balance": float(row.balance_subject_to_apr),
            "promo_rate_end_date": row.promo_rate_end_date,
            "promo_offer_id": row.promo_offer_id,
        }
        for row in rows
    ]


def get_loans_with_interest(session: Session) -> list[dict]:
    """Get loan data with calculated monthly interest.

    Joins loan_details -> accounts to get current balances.
    Calculates monthly interest as: (balance × rate / 100) / 12

    Returns:
        List of dicts with loan_type, account_name, mask, balance,
        interest_rate, monthly_payment, maturity_date, lender_name,
        collateral_description, and calculated monthly_interest
    """
    from sqlalchemy import func

    stmt = (
        select(
            LoanDetails.loan_type,
            func.coalesce(Account.display_name, Account.name).label("account_name"),
            Account.mask,
            func.coalesce(Account.balance_current, 0).label("balance"),
            LoanDetails.interest_rate,
            LoanDetails.monthly_payment,
            LoanDetails.maturity_date,
            LoanDetails.lender_name,
            LoanDetails.collateral_description,
        )
        .join(Account, LoanDetails.account_id == Account.account_id)
        .where(Account.is_excluded.is_(False))
        .order_by(LoanDetails.loan_type, Account.name)
    )

    result = session.execute(stmt)
    rows = result.fetchall()

    loans = []
    for row in rows:
        # Calculate monthly interest: (balance × rate / 100) / 12
        balance = float(row.balance)
        rate = float(row.interest_rate)
        monthly_interest = (balance * rate / 100) / 12

        loans.append(
            {
                "loan_type": row.loan_type,
                "account_name": row.account_name,
                "mask": row.mask,
                "balance": balance,
                "interest_rate": rate,
                "monthly_payment": float(row.monthly_payment),
                "maturity_date": row.maturity_date,
                "lender_name": row.lender_name,
                "collateral_description": row.collateral_description,
                "monthly_interest": monthly_interest,
            }
        )

    return loans


def get_cc_calculated_interest(session: Session) -> list[dict]:
    """Get credit card calculated interest based on payment strategy.

    For pay_in_full cards: Returns 0 (grace period).
    For promotional_paydown cards: Calculates interest only on APRs > 0%.

    Returns:
        List of dicts with account_id, account_name, mask, balance,
        payment_strategy, and calculated_interest
    """
    from sqlalchemy import func

    # Query credit card accounts with balances > 0
    stmt = (
        select(
            Account.account_id,
            func.coalesce(Account.display_name, Account.name).label("account_name"),
            Account.mask,
            Account.balance_current,
            Account.payment_strategy,
        )
        .where(
            Account.subtype == "credit card",
            Account.balance_current > 0,
            Account.is_excluded.is_(False),
        )
        .order_by(Account.name)
    )

    result = session.execute(stmt)
    accounts = result.fetchall()

    cards = []
    for account in accounts:
        calculated_interest = 0.0

        # pay_in_full strategy: zero interest (grace period)
        if account.payment_strategy == "pay_in_full":
            calculated_interest = 0.0
        # promotional_paydown: calculate from APRs > 0%
        elif account.payment_strategy == "promotional_paydown":
            # Query APRs for this account
            apr_stmt = (
                select(
                    CreditLiabilityApr.apr_percentage,
                    CreditLiabilityApr.balance_subject_to_apr,
                )
                .join(
                    CreditLiability,
                    CreditLiabilityApr.credit_liability_id == CreditLiability.id,
                )
                .where(
                    CreditLiability.account_id == account.account_id,
                    CreditLiabilityApr.apr_percentage > 0,
                    CreditLiabilityApr.balance_subject_to_apr > 0,
                )
            )

            apr_result = session.execute(apr_stmt)
            aprs = apr_result.fetchall()

            # Sum interest from all positive APRs
            for apr in aprs:
                if apr.balance_subject_to_apr is None:
                    continue
                balance = float(apr.balance_subject_to_apr)
                rate = float(apr.apr_percentage)
                monthly_int = (balance * rate / 100) / 12
                calculated_interest += monthly_int

        cards.append(
            {
                "account_id": account.account_id,
                "account_name": account.account_name,
                "mask": account.mask,
                "balance": float(account.balance_current)
                if account.balance_current
                else 0.0,
                "payment_strategy": account.payment_strategy,
                "calculated_interest": calculated_interest,
            }
        )

    return cards


def get_cc_interest_from_transactions(
    session: Session, months: int = 2
) -> dict[str, dict[str, float]]:
    """Get actual credit card interest from transaction history.

    Queries transactions with 'interest' in name and positive amounts
    (interest charged, not earned) on credit card accounts.

    Args:
        session: Database session
        months: Number of months to look back (default: 2)

    Returns:
        Nested dict: {month: {account_name: interest_amount}}
        Example: {'2025-12': {'Example Card A': 100.50}, '2025-11': {'Example Card A': 150.75}}
    """
    from sqlalchemy import func

    # Calculate cutoff date
    cutoff_date = date.today() - timedelta(days=months * 30)

    # Query interest transactions grouped by month and account
    stmt = (
        select(
            func.to_char(Transaction.date, "YYYY-MM").label("year_month"),
            func.coalesce(Account.display_name, Account.name).label("account_name"),
            func.sum(Transaction.amount).label("total_interest"),
        )
        .join(Account, Transaction.account_id == Account.account_id)
        .where(
            Account.subtype == "credit card",
            func.lower(Transaction.name).like("%interest%"),
            Transaction.amount > 0,  # Interest charged (not earned)
            Transaction.date >= cutoff_date,
        )
        .group_by(
            func.to_char(Transaction.date, "YYYY-MM"),
            func.coalesce(Account.display_name, Account.name),
        )
        .order_by(func.to_char(Transaction.date, "YYYY-MM").desc())
    )

    result = session.execute(stmt)
    rows = result.fetchall()

    # Build nested dict
    interest_by_month: dict[str, dict[str, float]] = {}
    for row in rows:
        month = row.year_month
        account_name = row.account_name
        interest = float(row.total_interest)

        if month not in interest_by_month:
            interest_by_month[month] = {}

        interest_by_month[month][account_name] = interest

    return interest_by_month


# Monthly Snapshot Functions


def get_depository_accounts(
    session: Session, include_excluded: bool = False
) -> list[dict]:
    """Get depository accounts (checking/savings) for account selection.

    Args:
        session: Database session
        include_excluded: If True, includes excluded accounts with [Excluded] prefix

    Returns:
        List of account dicts with account_id, name, display_name, type, subtype, is_excluded
    """
    stmt = select(
        Account.account_id,
        Account.name,
        Account.display_name,
        Account.type,
        Account.subtype,
        Account.is_excluded,
    ).where(Account.type == "depository")

    if not include_excluded:
        stmt = stmt.where(Account.is_excluded.is_(False))

    stmt = stmt.order_by(Account.name)

    result = session.execute(stmt)
    rows = result.fetchall()

    accounts = []
    for row in rows:
        # Use display_name if set, otherwise fall back to name
        shown_name = row.display_name or row.name

        # Add [Excluded] prefix if account is excluded
        if row.is_excluded:
            shown_name = f"[Excluded] {shown_name}"

        display = f"{shown_name} ({row.subtype})"
        accounts.append(
            {
                "account_id": row.account_id,
                "name": row.name,
                "display_name": row.display_name,
                "type": row.type,
                "subtype": row.subtype,
                "is_excluded": row.is_excluded,
                "display": display,
            }
        )
    return accounts


def get_credit_cards_for_account(session: Session, account_id: str) -> list[dict]:
    """Get credit cards paid by a specific checking account.

    Args:
        session: Database session
        account_id: The checking account ID that pays the cards

    Returns:
        List of credit card account dicts
    """
    stmt = (
        select(
            Account.account_id,
            func.coalesce(Account.display_name, Account.name).label("name"),
            Account.mask,
            Account.balance_current,
            Account.payment_strategy,
            Account.fixed_payment_amount,
            CreditLiability.last_statement_balance,
            CreditLiability.next_payment_due_date,
        )
        .outerjoin(CreditLiability, Account.account_id == CreditLiability.account_id)
        .where(
            Account.subtype == "credit card",
            Account.paying_account_id == account_id,
            Account.is_excluded.is_(False),
        )
        .order_by(Account.name)
    )

    result = session.execute(stmt)
    rows = result.fetchall()

    cards = []
    for row in rows:
        # Calculate average monthly spend for each card
        avg_spend = get_account_avg_monthly_spend(session, row.account_id)

        cards.append(
            {
                "account_id": row.account_id,
                "name": row.name,
                "mask": row.mask,
                "balance_current": float(row.balance_current)
                if row.balance_current
                else 0.0,
                "payment_strategy": row.payment_strategy,
                "fixed_payment_amount": float(row.fixed_payment_amount)
                if row.fixed_payment_amount
                else None,
                "last_statement_balance": float(row.last_statement_balance)
                if row.last_statement_balance
                else None,
                "next_payment_due_date": row.next_payment_due_date,
                "avg_monthly_spend": float(avg_spend),
            }
        )

    return cards


def get_anticipated_expenses(session: Session, account_id: str) -> list[dict]:
    """Get all active anticipated expense items for an account.

    Args:
        session: Database session
        account_id: Account ID to filter by

    Returns:
        List of expense item dicts
    """
    stmt = (
        select(AnticipatedItem)
        .where(
            AnticipatedItem.active.is_(True),
            AnticipatedItem.item_type == "expense",
            AnticipatedItem.account_id == account_id,
        )
        .order_by(AnticipatedItem.category, AnticipatedItem.name)
    )

    result = session.execute(stmt)
    items = result.scalars().all()

    return [
        {
            "id": str(item.id),
            "name": item.name,
            "amount": float(item.amount),
            "category": item.category,
            "item_type": item.item_type,
        }
        for item in items
    ]


def get_anticipated_income(session: Session, account_id: str) -> list[dict]:
    """Get all active anticipated income items for an account.

    Args:
        session: Database session
        account_id: Account ID to filter by

    Returns:
        List of income item dicts
    """
    stmt = (
        select(AnticipatedItem)
        .where(
            AnticipatedItem.active.is_(True),
            AnticipatedItem.item_type == "income",
            AnticipatedItem.account_id == account_id,
        )
        .order_by(AnticipatedItem.name)
    )

    result = session.execute(stmt)
    items = result.scalars().all()

    return [
        {
            "id": str(item.id),
            "name": item.name,
            "amount": float(item.amount),
            "category": item.category,
            "item_type": item.item_type,
        }
        for item in items
    ]


def get_account_avg_monthly_spend(
    session: Session, account_id: str, months: int = 3
) -> Decimal:
    """Calculate average monthly spend for a credit card account.

    Args:
        session: Database session
        account_id: Account UUID
        months: Number of months to average (default: 3)

    Returns:
        Average monthly spend as Decimal
    """
    # Calculate date range (last N months)
    end_date = date.today()
    start_date = end_date - timedelta(days=months * 30)  # Approximate months

    # Sum transactions for the account in date range
    stmt = select(func.sum(Transaction.amount)).where(
        Transaction.account_id == account_id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
    )

    result = session.execute(stmt).scalar()
    total = result if result else Decimal("0")

    # Calculate average
    return total / Decimal(str(months)) if months > 0 else Decimal("0")


def get_credit_cards_with_strategy(session: Session) -> list[dict]:
    """Get credit card accounts with payment strategy and balances.

    Returns list of dicts with account_id, name, mask, balance_current,
    payment_strategy, fixed_payment_amount, last_statement_balance,
    and avg_monthly_spend.

    Args:
        session: Database session

    Returns:
        List of credit card dicts
    """
    stmt = (
        select(
            Account.account_id,
            func.coalesce(Account.display_name, Account.name).label("name"),
            Account.mask,
            Account.balance_current,
            Account.payment_strategy,
            Account.fixed_payment_amount,
            CreditLiability.last_statement_balance,
            CreditLiability.next_payment_due_date,
        )
        .outerjoin(CreditLiability, Account.account_id == CreditLiability.account_id)
        .where(Account.subtype == "credit card")
        .where(Account.is_excluded.is_(False))
        .order_by(Account.name)
    )

    result = session.execute(stmt)
    rows = result.fetchall()

    cards = []
    for row in rows:
        # Calculate average monthly spend for each card
        avg_spend = get_account_avg_monthly_spend(session, row.account_id)

        cards.append(
            {
                "account_id": row.account_id,
                "name": row.name,
                "mask": row.mask,
                "balance_current": float(row.balance_current)
                if row.balance_current
                else 0.0,
                "payment_strategy": row.payment_strategy,
                "fixed_payment_amount": float(row.fixed_payment_amount)
                if row.fixed_payment_amount
                else None,
                "last_statement_balance": float(row.last_statement_balance)
                if row.last_statement_balance
                else None,
                "next_payment_due_date": row.next_payment_due_date,
                "avg_monthly_spend": float(avg_spend),
            }
        )

    return cards


def create_anticipated_item(
    session: Session,
    name: str,
    amount: float,
    item_type: str,
    category: str | None = None,
) -> dict:
    """Create a new anticipated item.

    Args:
        session: Database session
        name: Display name
        amount: Monthly amount
        item_type: Type ('expense' or 'income')
        category: Optional category

    Returns:
        Created item as dict
    """
    item = AnticipatedItem(
        name=name, amount=Decimal(str(amount)), item_type=item_type, category=category
    )
    session.add(item)
    session.flush()

    return {
        "id": str(item.id),
        "name": item.name,
        "amount": float(item.amount),
        "category": item.category,
        "item_type": item.item_type,
    }


def update_anticipated_item(session: Session, item_id: str, **kwargs) -> dict:
    """Update an anticipated item.

    Args:
        session: Database session
        item_id: Item UUID
        **kwargs: Fields to update

    Returns:
        Updated item as dict
    """
    stmt = select(AnticipatedItem).where(AnticipatedItem.id == UUID(item_id))
    result = session.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise ValueError(f"Item {item_id} not found")

    # Update fields
    for key, value in kwargs.items():
        if key == "amount":
            value = Decimal(str(value))
        setattr(item, key, value)

    session.flush()

    return {
        "id": str(item.id),
        "name": item.name,
        "amount": float(item.amount),
        "category": item.category,
        "item_type": item.item_type,
    }


def delete_anticipated_item(session: Session, item_id: str) -> bool:
    """Soft delete (deactivate) an anticipated item.

    Args:
        session: Database session
        item_id: Item UUID

    Returns:
        True on success
    """
    stmt = select(AnticipatedItem).where(AnticipatedItem.id == UUID(item_id))
    result = session.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        return False

    item.active = False
    session.flush()
    return True


def update_account_payment_strategy(
    session: Session, account_id: str, strategy: str, fixed_amount: float | None = None
) -> dict:
    """Update credit card payment strategy.

    Args:
        session: Database session
        account_id: Account ID
        strategy: Payment strategy ('pay_in_full' or 'promotional_paydown')
        fixed_amount: Fixed payment amount (for promotional_paydown)

    Returns:
        Updated account as dict
    """
    stmt = select(Account).where(Account.account_id == account_id)
    result = session.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        raise ValueError(f"Account {account_id} not found")

    account.payment_strategy = strategy
    account.fixed_payment_amount = Decimal(str(fixed_amount)) if fixed_amount else None
    session.flush()

    return {
        "account_id": account.account_id,
        "name": account.display_name or account.name,
        "payment_strategy": account.payment_strategy,
        "fixed_payment_amount": float(account.fixed_payment_amount)
        if account.fixed_payment_amount
        else None,
    }


def get_promo_cards_with_aprs(session: Session) -> list[dict]:
    """Get cards with payment_strategy='promotional_paydown' and their APR details.

    Returns list of dicts with account info and nested aprs list.
    Each APR includes promo fields: promo_offer_id, promo_rate_end_date, source.

    Args:
        session: Database session

    Returns:
        List of card dicts with account_id, name, mask, balance_current,
        fixed_payment_amount, payment_strategy, and aprs list
    """
    # Query accounts with promotional_paydown strategy
    stmt = (
        select(
            Account.account_id,
            func.coalesce(Account.display_name, Account.name).label("name"),
            Account.mask,
            Account.balance_current,
            Account.fixed_payment_amount,
            Account.payment_strategy,
        )
        .where(
            Account.payment_strategy == "promotional_paydown",
            Account.is_excluded.is_(False),
        )
        .order_by(Account.name)
    )

    result = session.execute(stmt)
    account_rows = result.fetchall()

    cards = []
    for row in account_rows:
        # Get APRs for this account
        apr_stmt = (
            select(
                CreditLiabilityApr.apr_type,
                CreditLiabilityApr.apr_percentage,
                CreditLiabilityApr.balance_subject_to_apr,
                CreditLiabilityApr.interest_charge_amount,
                CreditLiabilityApr.promo_offer_id,
                CreditLiabilityApr.promo_rate_end_date,
                CreditLiabilityApr.source,
            )
            .join(
                CreditLiability,
                CreditLiabilityApr.credit_liability_id == CreditLiability.id,
            )
            .where(CreditLiability.account_id == row.account_id)
            .order_by(CreditLiabilityApr.balance_subject_to_apr.desc())
        )

        apr_result = session.execute(apr_stmt)
        apr_rows = apr_result.fetchall()

        aprs = [
            {
                "apr_type": apr_row.apr_type,
                "apr_percentage": float(apr_row.apr_percentage)
                if apr_row.apr_percentage
                else 0.0,
                "balance": float(apr_row.balance_subject_to_apr)
                if apr_row.balance_subject_to_apr
                else 0.0,
                "interest_charge": float(apr_row.interest_charge_amount)
                if apr_row.interest_charge_amount
                else 0.0,
                "promo_offer_id": apr_row.promo_offer_id,
                "promo_rate_end_date": apr_row.promo_rate_end_date,
                "source": apr_row.source,
            }
            for apr_row in apr_rows
        ]

        cards.append(
            {
                "account_id": row.account_id,
                "name": row.name,
                "mask": row.mask,
                "balance_current": float(row.balance_current)
                if row.balance_current
                else 0.0,
                "fixed_payment_amount": float(row.fixed_payment_amount)
                if row.fixed_payment_amount
                else None,
                "payment_strategy": row.payment_strategy,
                "aprs": aprs,
            }
        )

    return cards


def get_all_credit_cards_with_full_details(session: Session) -> list[dict]:
    """Get all credit cards with comprehensive details for management page.

    Returns all credit cards (not just promotional) with:
    - Account info: account_id, name, display_name, mask, balance_current
    - Payment settings: payment_strategy, fixed_payment_amount
    - Relationships: paying_account_id, paying_account_display, institution_id
    - Status: is_excluded
    - APR data: list of APRs with promotional tracking

    Args:
        session: Database session

    Returns:
        List of credit card dicts with all details
    """
    # Alias for paying account self-join
    from sqlalchemy.orm import aliased

    paying_account_alias = aliased(Account, name="paying_account")

    # Query all credit card accounts with paying account display name
    stmt = (
        select(
            Account.account_id,
            func.coalesce(Account.display_name, Account.name).label("name"),
            Account.display_name,
            Account.mask,
            Account.balance_current,
            Account.payment_strategy,
            Account.fixed_payment_amount,
            Account.paying_account_id,
            func.coalesce(
                paying_account_alias.display_name, paying_account_alias.name
            ).label("paying_account_display"),
            Account.is_excluded,
            PlaidItem.institution_id,
        )
        .outerjoin(
            paying_account_alias,
            Account.paying_account_id == paying_account_alias.account_id,
        )
        .outerjoin(PlaidItem, Account.plaid_item_id == PlaidItem.id)
        .where(Account.subtype == "credit card")
        .order_by(Account.name)
    )

    result = session.execute(stmt)
    account_rows = result.fetchall()

    cards = []
    for row in account_rows:
        # Get APRs for this account
        apr_stmt = (
            select(
                CreditLiabilityApr.apr_type,
                CreditLiabilityApr.apr_percentage,
                CreditLiabilityApr.balance_subject_to_apr,
                CreditLiabilityApr.interest_charge_amount,
                CreditLiabilityApr.promo_offer_id,
                CreditLiabilityApr.promo_rate_end_date,
                CreditLiabilityApr.source,
            )
            .join(
                CreditLiability,
                CreditLiabilityApr.credit_liability_id == CreditLiability.id,
            )
            .where(CreditLiability.account_id == row.account_id)
            .order_by(CreditLiabilityApr.balance_subject_to_apr.desc())
        )

        apr_result = session.execute(apr_stmt)
        apr_rows = apr_result.fetchall()

        aprs = [
            {
                "apr_type": apr_row.apr_type,
                "apr_percentage": float(apr_row.apr_percentage)
                if apr_row.apr_percentage
                else 0.0,
                "balance": float(apr_row.balance_subject_to_apr)
                if apr_row.balance_subject_to_apr
                else 0.0,
                "interest_charge": float(apr_row.interest_charge_amount)
                if apr_row.interest_charge_amount
                else 0.0,
                "promo_offer_id": apr_row.promo_offer_id,
                "promo_rate_end_date": apr_row.promo_rate_end_date,
                "source": apr_row.source,
            }
            for apr_row in apr_rows
        ]

        cards.append(
            {
                "account_id": row.account_id,
                "name": row.name,
                "display_name": row.display_name,
                "mask": row.mask,
                "balance_current": float(row.balance_current)
                if row.balance_current
                else 0.0,
                "payment_strategy": row.payment_strategy,
                "fixed_payment_amount": float(row.fixed_payment_amount)
                if row.fixed_payment_amount
                else None,
                "paying_account_id": row.paying_account_id,
                "paying_account_display": row.paying_account_display,
                "is_excluded": row.is_excluded,
                "institution_id": row.institution_id,
                "aprs": aprs,
            }
        )

    return cards


def get_expiring_promos(session: Session, within_days: int = 60) -> list[dict]:
    """Get promotional APRs expiring within N days.

    Returns list of dicts with account info and promo details for APRs
    that have a promo_rate_end_date within the specified window.

    Args:
        session: Database session
        within_days: Number of days to look ahead (default: 60)

    Returns:
        List of dicts with account_id, account_name, mask, apr details,
        and days_until_expiration
    """
    end_date = date.today() + timedelta(days=within_days)

    stmt = (
        select(
            Account.account_id,
            func.coalesce(Account.display_name, Account.name).label("account_name"),
            Account.mask,
            CreditLiabilityApr.apr_type,
            CreditLiabilityApr.apr_percentage,
            CreditLiabilityApr.balance_subject_to_apr,
            CreditLiabilityApr.promo_offer_id,
            CreditLiabilityApr.promo_rate_end_date,
        )
        .join(
            CreditLiability,
            CreditLiabilityApr.credit_liability_id == CreditLiability.id,
        )
        .join(Account, CreditLiability.account_id == Account.account_id)
        .where(
            CreditLiabilityApr.promo_rate_end_date.isnot(None),
            CreditLiabilityApr.promo_rate_end_date <= end_date,
            Account.is_excluded.is_(False),
        )
        .order_by(CreditLiabilityApr.promo_rate_end_date)
    )

    result = session.execute(stmt)
    rows = result.fetchall()

    promos = []
    for row in rows:
        days_until = (row.promo_rate_end_date - date.today()).days

        promos.append(
            {
                "account_id": row.account_id,
                "account_name": row.account_name,
                "mask": row.mask,
                "apr_type": row.apr_type,
                "apr_percentage": float(row.apr_percentage),
                "balance": float(row.balance_subject_to_apr),
                "promo_offer_id": row.promo_offer_id,
                "promo_rate_end_date": row.promo_rate_end_date,
                "days_until_expiration": days_until,
            }
        )

    return promos


def upsert_promotional_apr(
    session: Session,
    account_id: str,
    apr_type: str,
    apr_percentage: float,
    balance: float,
    promo_end_date: date | None = None,
    offer_id: str | None = None,
) -> dict:
    """Create or update a manual promotional APR entry.

    Finds the CreditLiability by account_id, then calls the repository
    upsert_manual_apr method to create or update the APR record.

    Args:
        session: Database session
        account_id: Account ID
        apr_type: APR type (e.g., "promotional")
        apr_percentage: APR percentage
        balance: Balance subject to APR
        promo_end_date: Promotional rate end date (optional)
        offer_id: Promotional offer ID (optional)

    Returns:
        Created/updated APR as dict

    Raises:
        ValueError: If account or credit liability not found
    """
    from budget_me.db.repos.liabilities_repo import LiabilitiesRepo

    # Find the credit liability for this account
    stmt = select(CreditLiability).where(CreditLiability.account_id == account_id)
    result = session.execute(stmt)
    liability = result.scalar_one_or_none()

    if not liability:
        raise ValueError(f"Credit liability not found for account {account_id}")

    # Use repository to upsert the APR
    repo = LiabilitiesRepo(session)
    apr = repo.upsert_manual_apr(
        liability_id=liability.id,
        apr_type=apr_type,
        apr_percentage=Decimal(str(apr_percentage)),
        balance=Decimal(str(balance)),
        promo_end_date=promo_end_date,
        offer_id=offer_id,
    )

    return {
        "id": str(apr.id),
        "apr_type": apr.apr_type,
        "apr_percentage": float(apr.apr_percentage),
        "balance": float(apr.balance_subject_to_apr),
        "promo_offer_id": apr.promo_offer_id,
        "promo_rate_end_date": apr.promo_rate_end_date,
        "source": "manual",
    }


# Snapshot-based Monthly Functions


def get_or_create_snapshot(session: Session, year_month: str, account_id: str) -> dict:
    """Get existing snapshot or create new one with defaults for an account.

    If snapshot doesn't exist for the month and account:
    1. Create MonthlySnapshot
    2. Populate line items from AnticipatedItems for this account
    3. Populate credit cards paid by this account
    4. Return the new snapshot

    Args:
        session: Database session
        year_month: Year-month string (e.g., '2025-12')
        account_id: Account ID to scope the snapshot to

    Returns:
        Snapshot dict with status and totals
    """
    # Try to get existing snapshot for this account and month
    stmt = select(MonthlySnapshot).where(
        MonthlySnapshot.year_month == year_month,
        MonthlySnapshot.account_id == account_id,
    )
    result = session.execute(stmt)
    snapshot = result.scalar_one_or_none()

    if snapshot:
        # Return existing snapshot
        return {
            "id": str(snapshot.id),
            "year_month": snapshot.year_month,
            "account_id": snapshot.account_id,
            "status": snapshot.status,
            "income_total": float(snapshot.income_total)
            if snapshot.income_total
            else 0.0,
            "expense_total": float(snapshot.expense_total)
            if snapshot.expense_total
            else 0.0,
            "reimbursement_in_total": float(
                snapshot.reimbursement_in_total or Decimal("0.00")
            ),
            "reimbursement_out_total": float(
                snapshot.reimbursement_out_total or Decimal("0.00")
            ),
            "credit_card_total": float(snapshot.credit_card_total)
            if snapshot.credit_card_total
            else 0.0,
            "net": float(snapshot.net) if snapshot.net else 0.0,
            "closed_at": snapshot.closed_at,
            "last_synced_at": snapshot.last_synced_at,
            "notes": snapshot.notes,
        }

    # Create new snapshot for this account
    snapshot = MonthlySnapshot(
        year_month=year_month, account_id=account_id, status=SnapshotStatus.OPEN
    )
    session.add(snapshot)
    session.flush()

    # Populate only anticipated items that actually occur in this snapshot month.
    # The generic anticipated-item getters intentionally return every active item;
    # using them here used to pull future one-time and bounded items into the
    # current month's snapshot.
    from budget_me.forecasting.engine import get_item_months_in_range

    anticipated_items = (
        session.execute(
            select(AnticipatedItem).where(
                AnticipatedItem.active.is_(True),
                AnticipatedItem.account_id == account_id,
            )
        )
        .scalars()
        .all()
    )
    for item in anticipated_items:
        if year_month not in get_item_months_in_range(item, year_month, year_month):
            continue

        line_item = SnapshotLineItem(
            snapshot_id=snapshot.id,
            item_type=item.item_type,
            name=item.name,
            amount=item.amount,
            category=item.category,
            source_item_id=item.id,
            is_one_time=item.frequency == "one_time",
            skipped=False,
        )
        session.add(line_item)

    # Populate credit cards paid by this account
    credit_cards = get_credit_cards_for_account(session, account_id)
    for card in credit_cards:
        # Calculate payment based on strategy
        if card["payment_strategy"] == "pay_in_full":
            calculated_payment = Decimal(str(card["last_statement_balance"] or 0.0))
        else:  # promotional_paydown
            calculated_payment = Decimal(str(card["fixed_payment_amount"] or 0.0))

        credit_card = SnapshotCreditCard(
            snapshot_id=snapshot.id,
            account_id=card["account_id"],
            statement_balance=Decimal(str(card["last_statement_balance"]))
            if card["last_statement_balance"]
            else None,
            payment_strategy=card["payment_strategy"],
            fixed_payment_amount=Decimal(str(card["fixed_payment_amount"]))
            if card["fixed_payment_amount"]
            else None,
            calculated_payment=calculated_payment,
            due_date=card["next_payment_due_date"],
        )
        session.add(credit_card)

    session.flush()

    # Calculate and cache totals
    totals = calculate_snapshot_totals(session, year_month, account_id)

    # Update snapshot with totals
    snapshot.income_total = Decimal(str(totals["income_total"]))
    snapshot.expense_total = Decimal(str(totals["expense_total"]))
    snapshot.reimbursement_in_total = Decimal(str(totals["reimbursement_in_total"]))
    snapshot.reimbursement_out_total = Decimal(str(totals["reimbursement_out_total"]))
    snapshot.credit_card_total = Decimal(str(totals["credit_card_total"]))
    snapshot.net = Decimal(str(totals["net"]))
    session.flush()

    return {
        "id": str(snapshot.id),
        "year_month": snapshot.year_month,
        "account_id": snapshot.account_id,
        "status": snapshot.status,
        "income_total": totals["income_total"],
        "expense_total": totals["expense_total"],
        "reimbursement_in_total": totals["reimbursement_in_total"],
        "reimbursement_out_total": totals["reimbursement_out_total"],
        "credit_card_total": totals["credit_card_total"],
        "net": totals["net"],
        "closed_at": None,
        "last_synced_at": None,
        "notes": None,
    }


def get_available_months(session: Session, account_id: str) -> list[dict]:
    """Get months that have snapshots for a specific account.

    Args:
        session: Database session
        account_id: Account ID to filter by

    Returns:
        List of {year_month, status, display_label} sorted by year_month desc.
        Always includes current month and next month (for planning ahead).
    """
    from dateutil.relativedelta import relativedelta

    # Get current month and next month
    today = date.today()
    current_month = today.strftime("%Y-%m")
    next_month = (today + relativedelta(months=1)).strftime("%Y-%m")

    # Ensure current month snapshot exists for this account
    get_or_create_snapshot(session, current_month, account_id)

    # Get all snapshots for this account
    stmt = (
        select(MonthlySnapshot)
        .where(MonthlySnapshot.account_id == account_id)
        .order_by(MonthlySnapshot.year_month.desc())
    )
    result = session.execute(stmt)
    snapshots = result.scalars().all()

    # Build months list from existing snapshots
    months = []
    existing_months = set()
    for snapshot in snapshots:
        existing_months.add(snapshot.year_month)
        # Parse year-month for display
        year, month = snapshot.year_month.split("-")
        month_name = date(int(year), int(month), 1).strftime("%B")
        display_label = f"{month_name} {year}"

        # Add status indicator
        status_icon = "🔒" if snapshot.status == SnapshotStatus.CLOSED else "✏️"
        display_label = f"{status_icon} {display_label}"

        months.append(
            {
                "year_month": snapshot.year_month,
                "status": snapshot.status,
                "display_label": display_label,
            }
        )

    # Add next month if not already present (for planning ahead)
    if next_month not in existing_months:
        year, month = next_month.split("-")
        month_name = date(int(year), int(month), 1).strftime("%B")
        display_label = f"➕ {month_name} {year}"  # Plus icon indicates new
        months.insert(
            0,
            {
                "year_month": next_month,
                "status": "new",  # Special status for not-yet-created
                "display_label": display_label,
            },
        )

    return months


def get_snapshot_line_items(
    session: Session, year_month: str, account_id: str, item_type: str | None = None
) -> list[dict]:
    """Get line items for a snapshot for a specific account.

    Replaces get_anticipated_expenses() and get_anticipated_income()
    when viewing snapshots.

    Args:
        session: Database session
        year_month: Year-month string (e.g., '2025-12')
        account_id: Account ID to filter by
        item_type: Optional filter by item type ('income', 'expense', etc.)

    Returns:
        List of line item dicts
    """
    # Get snapshot for this account and month
    stmt = select(MonthlySnapshot).where(
        MonthlySnapshot.year_month == year_month,
        MonthlySnapshot.account_id == account_id,
    )
    result = session.execute(stmt)
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        return []

    # Get line items
    items_stmt = select(SnapshotLineItem).where(
        SnapshotLineItem.snapshot_id == snapshot.id
    )
    if item_type:
        items_stmt = items_stmt.where(SnapshotLineItem.item_type == item_type)

    items_result = session.execute(items_stmt)
    items = items_result.scalars().all()

    return [
        {
            "id": str(item.id),
            "name": item.name,
            "amount": float(item.amount),
            "category": item.category,
            "item_type": item.item_type,
            "is_one_time": item.is_one_time,
            "skipped": item.skipped,
            "source_item_id": str(item.source_item_id) if item.source_item_id else None,
        }
        for item in items
    ]


def get_snapshot_credit_cards(
    session: Session, year_month: str, account_id: str
) -> list[dict]:
    """Get credit cards for a snapshot for a specific account.

    Replaces get_credit_cards_with_strategy() when viewing snapshots.

    Args:
        session: Database session
        year_month: Year-month string (e.g., '2025-12')
        account_id: Account ID to filter by

    Returns:
        List of credit card dicts for the snapshot
    """
    # Get snapshot for this account and month
    stmt = select(MonthlySnapshot).where(
        MonthlySnapshot.year_month == year_month,
        MonthlySnapshot.account_id == account_id,
    )
    result = session.execute(stmt)
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        return []

    # Get credit cards with account names
    cards_stmt = (
        select(
            SnapshotCreditCard,
            func.coalesce(Account.display_name, Account.name).label("name"),
            Account.mask,
        )
        .outerjoin(Account, SnapshotCreditCard.account_id == Account.account_id)
        .where(SnapshotCreditCard.snapshot_id == snapshot.id)
    )

    cards_result = session.execute(cards_stmt)
    rows = cards_result.fetchall()

    return [
        {
            "id": str(row.SnapshotCreditCard.id),
            "account_id": row.SnapshotCreditCard.account_id,
            "name": row.name,
            "mask": row.mask,
            "statement_balance": float(row.SnapshotCreditCard.statement_balance)
            if row.SnapshotCreditCard.statement_balance
            else None,
            "payment_strategy": row.SnapshotCreditCard.payment_strategy,
            "fixed_payment_amount": float(row.SnapshotCreditCard.fixed_payment_amount)
            if row.SnapshotCreditCard.fixed_payment_amount
            else None,
            "calculated_payment": float(row.SnapshotCreditCard.calculated_payment),
            "due_date": row.SnapshotCreditCard.due_date,
            "actual_payment_amount": float(row.SnapshotCreditCard.actual_payment_amount)
            if row.SnapshotCreditCard.actual_payment_amount is not None
            else None,
            "actual_payment_date": row.SnapshotCreditCard.actual_payment_date,
        }
        for row in rows
    ]


def _require_open_snapshot_for_update(
    session: Session, snapshot_id: UUID
) -> MonthlySnapshot:
    """Lock and refresh a snapshot before permitting a direct UI mutation."""
    snapshot = session.get(
        MonthlySnapshot,
        snapshot_id,
        populate_existing=True,
        with_for_update=True,
    )
    if snapshot is None:
        raise ValueError(f"Snapshot {snapshot_id} not found")
    if snapshot.status == SnapshotStatus.CLOSED:
        raise ValueError("Cannot edit a closed snapshot")
    return snapshot


def update_snapshot_line_item(session: Session, item_id: str, **kwargs) -> dict:
    """Update a line item in an open snapshot.

    Validates snapshot is open before allowing edit.
    """
    # Get line item
    stmt = select(SnapshotLineItem).where(SnapshotLineItem.id == UUID(item_id))
    result = session.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise ValueError(f"Line item {item_id} not found")

    _require_open_snapshot_for_update(session, item.snapshot_id)

    # Update fields
    for key, value in kwargs.items():
        if key == "amount":
            value = Decimal(str(value))
        if hasattr(item, key):
            setattr(item, key, value)

    session.flush()

    return {
        "id": str(item.id),
        "name": item.name,
        "amount": float(item.amount),
        "category": item.category,
        "item_type": item.item_type,
        "is_one_time": item.is_one_time,
        "skipped": item.skipped,
    }


def skip_snapshot_line_item(session: Session, item_id: str, skipped: bool) -> dict:
    """Toggle skipped status on a line item."""
    return update_snapshot_line_item(session, item_id, skipped=skipped)


def add_one_time_item(
    session: Session,
    year_month: str,
    account_id: str,
    item_type: str,
    name: str,
    amount: float,
    category: str | None = None,
) -> dict:
    """Add a one-time line item to an open snapshot."""
    # Get or create snapshot
    snapshot_data = get_or_create_snapshot(session, year_month, account_id)
    snapshot_id = UUID(snapshot_data["id"])
    _require_open_snapshot_for_update(session, snapshot_id)

    # Create line item
    item = SnapshotLineItem(
        snapshot_id=snapshot_id,
        item_type=item_type,
        name=name,
        amount=Decimal(str(amount)),
        category=category,
        source_item_id=None,
        is_one_time=True,
        skipped=False,
    )
    session.add(item)
    session.flush()

    return {
        "id": str(item.id),
        "name": item.name,
        "amount": float(item.amount),
        "category": item.category,
        "item_type": item.item_type,
        "is_one_time": True,
        "skipped": False,
    }


def update_snapshot_credit_card(
    session: Session, card_id: str, payment_strategy: str, fixed_amount: float | None
) -> dict:
    """Update credit card payment strategy in open snapshot."""
    # Get credit card
    stmt = select(SnapshotCreditCard).where(SnapshotCreditCard.id == UUID(card_id))
    result = session.execute(stmt)
    card = result.scalar_one_or_none()

    if not card:
        raise ValueError(f"Credit card {card_id} not found")

    _require_open_snapshot_for_update(session, card.snapshot_id)

    # Update strategy
    card.payment_strategy = payment_strategy
    card.fixed_payment_amount = Decimal(str(fixed_amount)) if fixed_amount else None

    # Recalculate payment
    if payment_strategy == "pay_in_full":
        card.calculated_payment = card.statement_balance or Decimal("0.00")
    else:  # promotional_paydown
        card.calculated_payment = card.fixed_payment_amount or Decimal("0.00")

    session.flush()

    return {
        "id": str(card.id),
        "account_id": card.account_id,
        "payment_strategy": card.payment_strategy,
        "fixed_payment_amount": float(card.fixed_payment_amount)
        if card.fixed_payment_amount
        else None,
        "calculated_payment": float(card.calculated_payment),
    }


def close_snapshot(
    session: Session,
    year_month: str,
    account_id: str,
    *,
    confirm_month: str,
    audit_hash: str,
) -> dict:
    """Close a snapshot through the guarded, hash-bound close service."""
    from budget_me.snapshots.service import close_snapshot as guarded_close_snapshot

    preview = guarded_close_snapshot(
        session,
        year_month,
        account_id,
        confirm_month=confirm_month,
        audit_hash=audit_hash,
    )
    return {
        "id": preview.snapshot_id,
        "year_month": preview.year_month,
        "account_id": preview.account_id,
        "status": SnapshotStatus.CLOSED,
        "income_total": float(preview.totals.income_total),
        "expense_total": float(preview.totals.expense_total),
        "transfer_in_total": float(preview.totals.transfer_in_total),
        "transfer_out_total": float(preview.totals.transfer_out_total),
        "reimbursement_in_total": float(preview.totals.reimbursement_in_total),
        "reimbursement_out_total": float(preview.totals.reimbursement_out_total),
        "credit_card_total": float(preview.totals.credit_card_total),
        "net": float(preview.totals.net),
        "closing_balance": float(preview.closing_balance_to_freeze),
        "closed_at": preview.closed_at,
    }


def update_snapshot_notes(
    session: Session, year_month: str, account_id: str, notes: str | None
) -> dict:
    """Update notes for a snapshot.

    Args:
        session: Database session
        year_month: Year-month string (e.g., '2025-12')
        account_id: Account ID
        notes: Notes text (can be None to clear)

    Returns:
        Updated snapshot dict
    """
    stmt = select(MonthlySnapshot).where(
        MonthlySnapshot.year_month == year_month,
        MonthlySnapshot.account_id == account_id,
    )
    result = session.execute(stmt)
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise ValueError(
            f"Snapshot for {year_month} and account {account_id} not found"
        )

    snapshot = _require_open_snapshot_for_update(session, snapshot.id)
    snapshot.notes = notes
    session.flush()

    return {
        "id": str(snapshot.id),
        "year_month": snapshot.year_month,
        "account_id": snapshot.account_id,
        "notes": snapshot.notes,
    }


_SNAPSHOT_TOTAL_FIELDS = (
    "income_total",
    "expense_total",
    "transfer_in_total",
    "transfer_out_total",
    "reimbursement_in_total",
    "reimbursement_out_total",
    "credit_card_total",
    "net",
)


def _coherent_snapshot_header(
    snapshot: MonthlySnapshot,
) -> dict[str, Decimal] | None:
    """Return all cached actual totals when their net is internally coherent."""
    cached = {field: getattr(snapshot, field) for field in _SNAPSHOT_TOTAL_FIELDS}
    if any(value is None for value in cached.values()):
        return None

    expected_net = (
        cached["income_total"]
        + cached["transfer_in_total"]
        + cached["reimbursement_in_total"]
        - cached["expense_total"]
        - cached["transfer_out_total"]
        - cached["reimbursement_out_total"]
        - cached["credit_card_total"]
    )
    if cached["net"] != expected_net:
        return None

    return cached


def _closed_snapshot_cache(
    snapshot: MonthlySnapshot,
) -> dict[str, Decimal] | None:
    """Return a complete, internally coherent frozen snapshot header."""
    if (
        snapshot.status != SnapshotStatus.CLOSED
        or not snapshot.closing_balance_frozen
        or snapshot.closing_balance is None
    ):
        return None

    cached = _coherent_snapshot_header(snapshot)
    if cached is None:
        return None

    return {
        **cached,
        "closing_balance": snapshot.closing_balance,
    }


def calculate_snapshot_totals(
    session: Session, year_month: str, account_id: str
) -> dict:
    """Return authoritative totals for one account's monthly snapshot.

    Closed snapshots use only their cached header. A timestamped open snapshot
    also uses its complete, coherent cached actual header. Only an unsynced open
    snapshot remains a live projection calculated from non-skipped line items
    and planned card payments, with reimbursement flows held at zero.

    Args:
        session: Database session
        year_month: Year-month string (e.g., '2025-12')
        account_id: Account ID to filter by

    Returns:
        Dict with totals
    """
    # Get snapshot for this account and month
    stmt = select(MonthlySnapshot).where(
        MonthlySnapshot.year_month == year_month,
        MonthlySnapshot.account_id == account_id,
    )
    result = session.execute(stmt)
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise ValueError(
            f"Snapshot for {year_month} and account {account_id} not found"
        )

    if snapshot.status == SnapshotStatus.CLOSED:
        totals = _closed_snapshot_cache(snapshot)
        if totals is None:
            raise ValueError(
                f"Closed snapshot for {year_month} and account {account_id} "
                "does not have a complete, coherent cached header and frozen close"
            )
        return {field: float(value) for field, value in totals.items()}

    if snapshot.last_synced_at is not None:
        cached = _coherent_snapshot_header(snapshot)
        if cached is None:
            raise ValueError(
                f"Reconciled open snapshot for {year_month} and account "
                f"{account_id} does not have a complete, coherent cached header"
            )
        closing_balance = (snapshot.starting_balance or Decimal("0.00")) + cached["net"]
        return {
            **{field: float(value) for field, value in cached.items()},
            "closing_balance": float(closing_balance),
        }

    # Get non-skipped line items
    items_stmt = select(SnapshotLineItem).where(
        SnapshotLineItem.snapshot_id == snapshot.id,
        SnapshotLineItem.skipped.is_not(True),
    )
    items_result = session.execute(items_stmt)
    items = items_result.scalars().all()

    # Calculate income, expense, and transfer totals
    income_total = Decimal("0.00")
    expense_total = Decimal("0.00")
    transfer_in_total = Decimal("0.00")
    transfer_out_total = Decimal("0.00")
    # Reimbursements are actual-only flows. Unsynced open snapshots retain their
    # plan-only semantics even if stale header values happen to exist.
    reimbursement_in_total = Decimal("0.00")
    reimbursement_out_total = Decimal("0.00")

    for item in items:
        if item.item_type == "income":
            income_total += item.amount or Decimal("0.00")
        elif item.item_type == "expense":
            expense_total += item.amount or Decimal("0.00")
        elif item.item_type == "transfer_in":
            transfer_in_total += item.amount or Decimal("0.00")
        elif item.item_type == "transfer_out":
            transfer_out_total += item.amount or Decimal("0.00")

    # Get credit cards
    cards_stmt = select(SnapshotCreditCard).where(
        SnapshotCreditCard.snapshot_id == snapshot.id
    )
    cards_result = session.execute(cards_stmt)
    cards = cards_result.scalars().all()

    # Calculate credit card total (treat null as 0.00)
    credit_card_total = Decimal("0.00")
    for card in cards:
        credit_card_total += card.calculated_payment or Decimal("0.00")

    # Calculate net with reimbursements separate from ordinary income and expense.
    net = (
        income_total
        + transfer_in_total
        + reimbursement_in_total
        - expense_total
        - transfer_out_total
        - reimbursement_out_total
        - credit_card_total
    )

    return {
        "income_total": float(income_total),
        "expense_total": float(expense_total),
        "transfer_in_total": float(transfer_in_total),
        "transfer_out_total": float(transfer_out_total),
        "reimbursement_in_total": float(reimbursement_in_total),
        "reimbursement_out_total": float(reimbursement_out_total),
        "credit_card_total": float(credit_card_total),
        "net": float(net),
        "closing_balance": float((snapshot.starting_balance or Decimal("0.00")) + net),
    }


def get_starting_balance(
    session: Session, account_id: str, year_month: str
) -> tuple[Decimal | None, bool]:
    """
    Get starting balance for a month.

    This is a synchronous wrapper around MonthlySnapshotRepo.get_starting_balance
    for use in Streamlit.

    Returns:
        tuple[Decimal | None, bool]: (balance, is_frozen)
            - balance: The starting balance, or None if cannot be determined
            - is_frozen: True if from closed previous month, False otherwise
    """
    from calendar import monthrange

    # First, look up the current month's snapshot.
    stmt = select(MonthlySnapshot).where(
        MonthlySnapshot.year_month == year_month,
        MonthlySnapshot.account_id == account_id,
    )
    result = session.execute(stmt)
    current_snapshot = result.scalar_one_or_none()

    # Parse year_month to get previous month
    year, month = map(int, year_month.split("-"))
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    prev_year_month = f"{prev_year:04d}-{prev_month:02d}"

    # Check for previous month snapshot with closing_balance
    stmt = select(MonthlySnapshot).where(
        MonthlySnapshot.year_month == prev_year_month,
        MonthlySnapshot.account_id == account_id,
    )
    result = session.execute(stmt)
    prev_snapshot = result.scalar_one_or_none()

    # A guarded close seeds an existing next-month snapshot's starting balance.
    # There is no persisted provenance column, so infer that provenance only
    # when the stored value exactly matches an explicitly frozen prior close.
    if current_snapshot and current_snapshot.starting_balance is not None:
        inherited_frozen_close = bool(
            prev_snapshot
            and prev_snapshot.status == SnapshotStatus.CLOSED
            and prev_snapshot.closing_balance_frozen
            and prev_snapshot.closing_balance == current_snapshot.starting_balance
        )
        return (current_snapshot.starting_balance, inherited_frozen_close)

    if prev_snapshot and prev_snapshot.closing_balance is not None:
        # If closed, it's frozen; if open, it's an estimate
        is_frozen = prev_snapshot.status == SnapshotStatus.CLOSED
        return (prev_snapshot.closing_balance, is_frozen)

    # Carry the live calculated close forward from an open prior month. Future
    # snapshots are often opened before the current month is closed, so there is
    # intentionally no stored closing_balance yet.
    if prev_snapshot and prev_snapshot.status == SnapshotStatus.OPEN:
        prev_starting, _ = get_starting_balance(session, account_id, prev_year_month)
        if prev_starting is not None:
            prev_totals = calculate_snapshot_totals(
                session, prev_year_month, account_id
            )
            return (
                prev_starting + Decimal(str(prev_totals["net"])),
                False,
            )

    # Fall back to balance snapshot for last day of previous month
    last_day = monthrange(prev_year, prev_month)[1]
    last_date = date(prev_year, prev_month, last_day)

    stmt = select(AccountBalanceSnapshot).where(
        AccountBalanceSnapshot.account_id == account_id,
        AccountBalanceSnapshot.snapshot_date == last_date,
    )
    result = session.execute(stmt)
    balance_snapshot = result.scalar_one_or_none()

    if balance_snapshot:
        return (balance_snapshot.balance_current, False)

    # No data available
    return (None, False)


def get_closing_balance(
    session: Session, account_id: str, year_month: str
) -> tuple[Decimal | None, bool]:
    """
    Get closing balance for a month.

    This is a synchronous wrapper around MonthlySnapshotRepo.get_closing_balance
    for use in Streamlit.

    Returns:
        tuple[Decimal | None, bool]: (balance, is_frozen)
            - balance: The closing balance, or None if cannot be determined
            - is_frozen: True if from closed month, False if calculated/estimated
    """
    from calendar import monthrange

    # Get this month's snapshot
    stmt = select(MonthlySnapshot).where(
        MonthlySnapshot.year_month == year_month,
        MonthlySnapshot.account_id == account_id,
    )
    result = session.execute(stmt)
    snapshot = result.scalar_one_or_none()

    # If closed with frozen balance, return it
    if (
        snapshot
        and snapshot.status == SnapshotStatus.CLOSED
        and snapshot.closing_balance is not None
    ):
        return (snapshot.closing_balance, True)

    # If open but has closing_balance set directly, use it (marked as estimate)
    if snapshot and snapshot.closing_balance is not None:
        return (snapshot.closing_balance, False)

    # Prefer the reconciled balance (starting + net) over Plaid's daily capture.
    # The daily capture can miss same-day postings (e.g. a check that clears on
    # the last day of the month), which silently drifts the balance and then
    # cascades into every following month's starting balance. The reconciled net
    # ties to the actual transactions, so it is authoritative. Fall back to the
    # daily capture only when we can't reconcile (no snapshot / no starting).
    if snapshot:
        starting_balance, _ = get_starting_balance(session, account_id, year_month)
        if starting_balance is not None:
            # Live totals include one-off items not in the cached totals
            totals = calculate_snapshot_totals(session, year_month, account_id)
            calculated = starting_balance + Decimal(str(totals["net"]))
            return (calculated, False)

    # Fall back to the daily balance capture for the last day of the month
    year, month = map(int, year_month.split("-"))
    last_day = monthrange(year, month)[1]
    last_date = date(year, month, last_day)
    result = session.execute(
        select(AccountBalanceSnapshot).where(
            AccountBalanceSnapshot.account_id == account_id,
            AccountBalanceSnapshot.snapshot_date == last_date,
        )
    )
    balance_snapshot = result.scalar_one_or_none()
    if balance_snapshot:
        return (balance_snapshot.balance_current, False)

    return (None, False)


# ============================================================================
# Budget Functions
# ============================================================================


def get_category_budgets(
    session: Session, account_id: str, year_month: str
) -> list[dict]:
    """Get all category budgets for an account/month.

    Args:
        session: Database session
        account_id: Account ID to filter by
        year_month: Year-month string (e.g., "2025-01")

    Returns:
        List of budget dictionaries with category and budget_amount
    """
    from sqlalchemy import select

    stmt = (
        select(
            CategoryBudget.category,
            CategoryBudget.budget_amount,
            CategoryBudget.account_id,
        )
        .where(
            CategoryBudget.account_id == account_id,
            CategoryBudget.year_month == year_month,
        )
        .order_by(CategoryBudget.category)
    )

    result = session.execute(stmt)
    rows = result.fetchall()

    return [
        {
            "category": row.category,
            "budget_amount": row.budget_amount,
            "account_id": row.account_id,
        }
        for row in rows
    ]


def upsert_category_budget(
    session: Session, account_id: str, year_month: str, category: str, amount: Decimal
) -> None:
    """Insert or update a category budget.

    Args:
        session: Database session
        account_id: Account ID
        year_month: Year-month string (e.g., "2025-01")
        category: Budget category name
        amount: Budget amount
    """
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(CategoryBudget).values(
        account_id=account_id,
        year_month=year_month,
        category=category,
        budget_amount=amount,
    )

    # On conflict, update the budget_amount and updated_at
    stmt = stmt.on_conflict_do_update(
        constraint="uq_category_budgets_account_month_category",
        set_={
            "budget_amount": amount,
            "updated_at": datetime.now(datetime.now().astimezone().tzinfo),
        },
    )

    session.execute(stmt)


def get_category_actuals(
    session: Session, account_id: str, year_month: str
) -> list[dict]:
    """Get actual spending by category for an account/month.

    Includes transactions from:
    - The specified depository account
    - All credit cards linked via paying_account_id

    Args:
        session: Database session
        account_id: Account ID to filter by (typically a depository account)
        year_month: Year-month string (e.g., "2025-01")

    Returns:
        List of dictionaries with category and total_spent
    """
    from sqlalchemy import extract, func, or_, select

    # Parse year and month from year_month
    year, month = map(int, year_month.split("-"))

    # Find all credit cards that pay to this account
    linked_cards = (
        session.execute(
            select(Account.account_id).where(Account.paying_account_id == account_id)
        )
        .scalars()
        .all()
    )

    # Include both the depository account and all linked credit cards
    all_account_ids = [account_id] + list(linked_cards)

    # Categories that represent money movement, not actual spending
    excluded_categories = [
        "reimbursement",  # Incoming reimbursements
        "credit_card_payment",  # Paying off CC debt (spending already counted on card)
        "cc_payment",  # Alternate naming for credit card payments
        "transfer",  # Moving money between accounts
    ]

    stmt = (
        select(
            Transaction.budget_category.label("category"),
            func.sum(Transaction.amount).label("total_spent"),
        )
        .where(
            Transaction.account_id.in_(all_account_ids),
            Transaction.budget_category.is_not(None),
            extract("year", Transaction.date) == year,
            extract("month", Transaction.date) == month,
            # Exclude reimbursable expenses and reimbursement income
            or_(Transaction.reimbursable.is_(None), ~Transaction.reimbursable),
            # Exclude money movement categories (not actual spending)
            Transaction.budget_category.notin_(excluded_categories),
            # Only include expenses (positive amounts) - excludes income/credits
            Transaction.amount > 0,
        )
        .group_by(Transaction.budget_category)
    )

    result = session.execute(stmt)
    rows = result.fetchall()

    return [
        {
            "category": row.category,
            "total_spent": row.total_spent,
        }
        for row in rows
    ]


def get_category_transactions(
    session: Session, account_id: str, year_month: str, category: str
) -> list[dict]:
    """Get individual transactions for a category in an account/month.

    Includes transactions from:
    - The specified depository account
    - All credit cards linked via paying_account_id

    Mirrors the filtering logic of get_category_actuals() but returns
    individual transactions instead of aggregated totals.

    Args:
        session: Database session
        account_id: Account ID to filter by (typically a depository account)
        year_month: Year-month string (e.g., "2025-01")
        category: Budget category to filter by

    Returns:
        List of dictionaries with date, merchant_name, amount, account_name
    """
    from sqlalchemy import desc, extract, func, or_, select

    # Parse year and month from year_month
    year, month = map(int, year_month.split("-"))

    # Find all credit cards that pay to this account
    linked_cards = (
        session.execute(
            select(Account.account_id).where(Account.paying_account_id == account_id)
        )
        .scalars()
        .all()
    )

    # Include both the depository account and all linked credit cards
    all_account_ids = [account_id] + list(linked_cards)

    # Categories that represent money movement, not actual spending
    excluded_categories = [
        "reimbursement",  # Incoming reimbursements
        "credit_card_payment",  # Paying off CC debt (spending already counted on card)
        "cc_payment",  # Alternate naming for credit card payments
        "transfer",  # Moving money between accounts
    ]

    stmt = (
        select(
            Transaction.date,
            func.coalesce(Transaction.merchant_name, Transaction.name).label(
                "merchant_name"
            ),
            Transaction.amount,
            func.coalesce(Account.display_name, Account.name).label("account_name"),
        )
        .join(Account, Transaction.account_id == Account.account_id)
        .where(
            Transaction.account_id.in_(all_account_ids),
            Transaction.budget_category == category,
            extract("year", Transaction.date) == year,
            extract("month", Transaction.date) == month,
            # Exclude reimbursable expenses and reimbursement income
            or_(Transaction.reimbursable.is_(None), ~Transaction.reimbursable),
            # Exclude money movement categories (not actual spending)
            Transaction.budget_category.notin_(excluded_categories),
            # Only include expenses (positive amounts) - excludes income/credits
            Transaction.amount > 0,
        )
        .order_by(desc(Transaction.date))
    )

    result = session.execute(stmt)
    rows = result.fetchall()

    return [
        {
            "date": row.date,
            "merchant_name": row.merchant_name,
            "amount": row.amount,
            "account_name": row.account_name,
        }
        for row in rows
    ]


def get_available_budget_months(session: Session, account_id: str) -> list[dict]:
    """Get months that have budgets or transactions for an account.

    Args:
        session: Database session
        account_id: Account ID to filter by

    Returns:
        List of dictionaries with year_month, sorted newest-first
    """
    from sqlalchemy import func, text, union

    # Months with budgets
    budget_months = (
        select(CategoryBudget.year_month)
        .where(CategoryBudget.account_id == account_id)
        .distinct()
    )

    # Months with categorized transactions
    transaction_months = (
        select(func.to_char(Transaction.date, "YYYY-MM").label("year_month"))
        .where(
            Transaction.account_id == account_id,
            Transaction.budget_category.is_not(None),
        )
        .distinct()
    )

    # Union both sources
    stmt = union(budget_months, transaction_months).order_by(text("year_month desc"))

    result = session.execute(stmt)
    rows = result.fetchall()

    return [{"year_month": row[0]} for row in rows]


def is_budget_month_locked(year_month: str) -> bool:
    """Check if a budget month is locked (in the past).

    Args:
        year_month: Year-month string (e.g., "2025-01")

    Returns:
        True if the month is in the past (locked), False otherwise
    """
    from datetime import date

    current_month = date.today().strftime("%Y-%m")
    return year_month < current_month


def get_budget_categories_from_yaml() -> list[str]:
    """Load the category taxonomy shipped with the OSS package."""
    from budget_me.categorization.rules import PACKAGED_RULES_PATH, load_rules

    try:
        _, categories, _ = load_rules(PACKAGED_RULES_PATH)
    except (FileNotFoundError, OSError, ValueError):
        return [
            "groceries",
            "dining",
            "subscriptions",
            "shopping",
            "transportation",
            "utilities",
            "entertainment",
            "health",
            "home",
            "travel",
            "fees",
            "giving",
            "gifts",
            "childcare",
            "insurance",
            "auto",
            "education",
            "personal_care",
            "hobbyist_eng",
            "shipping",
            "pets",
            "alcohol",
            "taxes",
            "mortgage",
            "landscaping",
            "credit_card_payment",
            "transfer",
            "uncategorized",
            "reimbursement",
        ]

    return sorted(categories)


def copy_budgets_from_month(
    session: Session, account_id: str, target_month: str, source_month: str
) -> None:
    """Copy budgets from source month to target month.

    Only copies if target month has no existing budgets.

    Args:
        session: Database session
        account_id: Account ID
        target_month: Target year-month (e.g., "2025-02")
        source_month: Source year-month (e.g., "2025-01")
    """
    from sqlalchemy import select

    # Check if target month already has budgets
    existing_count = session.execute(
        select(func.count())
        .select_from(CategoryBudget)
        .where(
            CategoryBudget.account_id == account_id,
            CategoryBudget.year_month == target_month,
        )
    ).scalar_one()

    if existing_count > 0:
        # Target month already has budgets, don't overwrite
        return

    # Get source month budgets
    source_budgets = get_category_budgets(session, account_id, source_month)

    # Create new budgets for target month
    for budget in source_budgets:
        upsert_category_budget(
            session,
            account_id,
            target_month,
            budget["category"],
            budget["budget_amount"],
        )


def get_previous_month(year_month: str) -> str:
    """Get the previous month from a year-month string.

    Args:
        year_month: Year-month string (e.g., "2025-01")

    Returns:
        Previous month in same format (e.g., "2024-12")
    """
    from datetime import date

    from dateutil.relativedelta import relativedelta

    year, month = map(int, year_month.split("-"))
    current = date(year, month, 1)
    previous = current - relativedelta(months=1)
    return previous.strftime("%Y-%m")


# === Credit Card Payment Projections (Phase 2.5) ===


def get_projected_payment(session: Session, account: Any) -> tuple[Decimal, str]:
    """Get projected monthly payment for a credit card.

    Returns (amount, source) where source is one of:
    - "fixed" - promotional_paydown card using fixed_payment_amount
    - "manual" - user override via projected_monthly_payment
    - "historical_3mo_avg" - calculated from spending history
    - "current_balance" - fallback when no history available

    Priority:
    1. If promotional_paydown: return fixed_payment_amount
    2. If projected_monthly_payment set: return it (manual override)
    3. Else: calculate historical average (TODO: implement)
    4. Fallback: current balance
    """
    from decimal import Decimal

    # Priority 1: Promotional paydown uses fixed amount
    if (
        account.payment_strategy == "promotional_paydown"
        and account.fixed_payment_amount
    ):
        return (account.fixed_payment_amount, "fixed")

    # Priority 2: Manual override
    if account.projected_monthly_payment is not None:
        return (account.projected_monthly_payment, "manual")

    # Priority 3: Historical average (TODO: implement calculate_historical_payment_average)
    # hist_avg = calculate_historical_payment_average(session, account.account_id)
    # if hist_avg:
    #     return (hist_avg, "historical_3mo_avg")

    # Priority 4: Fallback to current balance
    if account.balance_current:
        return (abs(account.balance_current), "current_balance")

    return (Decimal("0.00"), "current_balance")


def get_credit_card_projections(session: Session) -> list[dict]:
    """Get all non-excluded credit cards with their projected payments.

    Returns list of dicts with:
    - account_id, card_name, mask, current_balance
    - payment_strategy, projected_payment, projection_source
    - paying_account_id, paying_account_name
    """
    from sqlalchemy import select

    from budget_me.db.models.account import Account

    # Get all non-excluded credit cards
    result = session.execute(
        select(Account)
        .where(
            Account.subtype == "credit card",  # Note: Plaid uses space, not underscore
            Account.is_excluded.is_(False),
        )
        .order_by(Account.name)
    )
    cards = result.scalars().all()

    projections = []
    for card in cards:
        projected_payment, source = get_projected_payment(session, card)

        # Get paying account name if set
        paying_account_name = None
        if card.paying_account_id:
            paying_result = session.execute(
                select(Account.display_name, Account.name).where(
                    Account.account_id == card.paying_account_id
                )
            )
            paying_row = paying_result.first()
            if paying_row:
                paying_account_name = paying_row[0] or paying_row[1]

        projections.append(
            {
                "account_id": card.account_id,
                "card_name": card.display_name or card.name,
                "mask": card.mask,
                "current_balance": abs(card.balance_current)
                if card.balance_current
                else Decimal("0.00"),
                "payment_strategy": card.payment_strategy,
                "projected_payment": projected_payment,
                "projection_source": source,
                "paying_account_id": card.paying_account_id,
                "paying_account_name": paying_account_name,
            }
        )

    return projections


def get_historical_cc_average(session: Session, months: int = 3) -> Decimal | None:
    """Get monthly credit card payment estimate from historical snapshot data.

    If 3+ months of data exist, returns the average of the last N months.
    If fewer than 3 months exist, returns the most recent month's total
    (to avoid averaging with potentially incomplete older data).

    Args:
        session: Database session
        months: Number of months to average when sufficient data exists (default 3)

    Returns:
        Decimal CC payment estimate, or None if no historical data exists
    """
    if months <= 0:
        return None

    # Read every household snapshot so a partially closed month cannot masquerade
    # as complete merely because its closed account rows have cached card totals.
    result = session.execute(
        select(MonthlySnapshot).order_by(MonthlySnapshot.year_month.desc())
    )
    snapshots_by_month: dict[str, list[MonthlySnapshot]] = {}
    for snapshot in result.scalars().all():
        snapshots_by_month.setdefault(snapshot.year_month, []).append(snapshot)

    monthly_totals: list[Decimal] = []
    for snapshots in snapshots_by_month.values():
        cached_month: list[dict[str, Decimal]] = []
        for snapshot in snapshots:
            cached = _closed_snapshot_cache(snapshot)
            if cached is None:
                break
            cached_month.append(cached)
        else:
            monthly_totals.append(
                sum(
                    (cached["credit_card_total"] for cached in cached_month),
                    Decimal("0.00"),
                )
            )
            if len(monthly_totals) == months:
                break

    if not monthly_totals:
        return None

    # If fewer than 3 months of data, use only the most recent month
    # (to avoid averaging with potentially incomplete older data)
    if len(monthly_totals) < months:
        return Decimal(str(round(monthly_totals[0], 2)))

    # Calculate average when we have sufficient data
    average = sum(monthly_totals) / len(monthly_totals)
    return Decimal(str(round(average, 2)))


# === Yearly Forecast Functions (Phase 4) ===


def get_anticipated_items_for_forecast(session: Session) -> list[dict]:
    """Get all active anticipated items with extended fields.

    Returns items with: id, name, amount, item_type, category,
                       frequency, start_month, end_month, account_id
    """
    from sqlalchemy import select

    from budget_me.db.models.anticipated_item import AnticipatedItem

    result = session.execute(
        select(AnticipatedItem)
        .where(AnticipatedItem.active.is_(True))
        .order_by(AnticipatedItem.name)
    )
    items = result.scalars().all()

    return [
        {
            "id": str(item.id),
            "name": item.name,
            "amount": item.amount,
            "item_type": item.item_type,
            "category": item.category,
            "frequency": item.frequency,
            "start_month": item.start_month,
            "end_month": item.end_month,
            "account_id": item.account_id,
        }
        for item in items
    ]


def get_funding_sources(session: Session) -> list[dict]:
    """Get all active funding sources.

    Returns: id, name, source_type, available_amount, notes
    """
    from sqlalchemy import select

    from budget_me.db.models.funding_source import FundingSource

    result = session.execute(
        select(FundingSource)
        .where(FundingSource.active.is_(True))
        .order_by(FundingSource.name)
    )
    sources = result.scalars().all()

    return [
        {
            "id": str(source.id),
            "name": source.name,
            "source_type": source.source_type,
            "available_amount": source.available_amount,
            "notes": source.notes,
        }
        for source in sources
    ]


def get_total_available_funding(session: Session) -> Decimal:
    """Sum available_amount from all active funding sources."""
    from sqlalchemy import func, select

    from budget_me.db.models.funding_source import FundingSource

    result = session.execute(
        select(func.sum(FundingSource.available_amount)).where(
            FundingSource.active.is_(True)
        )
    )
    total = result.scalar()
    return total or Decimal("0.00")


def get_aggregate_checking_balance(session: Session) -> Decimal:
    """Get sum of current balance across all non-excluded checking accounts.

    Query accounts where type='depository' and is_excluded=False,
    sum balance_current.
    """
    from sqlalchemy import func, select

    from budget_me.db.models.account import Account

    result = session.execute(
        select(func.sum(Account.balance_current)).where(
            Account.type == "depository",
            Account.is_excluded.is_(False),
        )
    )
    total = result.scalar()
    return total or Decimal("0.00")


@dataclass
class SnapshotTotals:
    """Authoritative household cash-flow totals for one month."""

    income: Decimal
    expenses: Decimal
    cc_payments: Decimal
    closing_balance: Decimal
    transfer_in: Decimal
    transfer_out: Decimal
    net: Decimal
    reimbursement_in: Decimal = Decimal("0.00")
    reimbursement_out: Decimal = Decimal("0.00")


def get_snapshot_totals(
    session: Session, year_month: str, include_open: bool = True
) -> SnapshotTotals | None:
    """Get totals from monthly snapshots for a given month.

    Aggregates across ALL checking accounts (household view).

    Closed snapshots use only complete, coherent cached headers and their frozen
    closing balances. Open snapshots (when requested) are calculated from live
    non-skipped line items and planned card payments.

    Returns SnapshotTotals with:
    - base income and expenses
    - transfer and reimbursement inflows and outflows
    - card payments
    - coherent cash-flow net
    - frozen (closed) or projected (open) aggregate closing balance

    Returns None when no snapshots match or any closed header is incomplete.
    """
    # Build status filter
    if include_open:
        status_filter = MonthlySnapshot.year_month == year_month
    else:
        status_filter = (MonthlySnapshot.year_month == year_month) & (
            MonthlySnapshot.status == SnapshotStatus.CLOSED
        )

    # Get all snapshots for this month
    snapshots_result = session.execute(select(MonthlySnapshot).where(status_filter))
    snapshots = snapshots_result.scalars().all()

    if not snapshots:
        return None

    total_income = Decimal("0.00")
    total_expenses = Decimal("0.00")
    total_transfer_in = Decimal("0.00")
    total_transfer_out = Decimal("0.00")
    total_reimbursement_in = Decimal("0.00")
    total_reimbursement_out = Decimal("0.00")
    total_cc_payments = Decimal("0.00")
    total_net = Decimal("0.00")
    total_closing_balance = Decimal("0.00")

    for snapshot in snapshots:
        if snapshot.status == SnapshotStatus.CLOSED:
            totals = _closed_snapshot_cache(snapshot)
            if totals is None:
                return None
        elif snapshot.status == SnapshotStatus.OPEN and include_open:
            live = calculate_snapshot_totals(
                session,
                snapshot.year_month,
                snapshot.account_id,
            )
            totals = {field: Decimal(str(value)) for field, value in live.items()}
        else:
            return None

        total_income += totals["income_total"]
        total_expenses += totals["expense_total"]
        total_transfer_in += totals["transfer_in_total"]
        total_transfer_out += totals["transfer_out_total"]
        total_reimbursement_in += totals["reimbursement_in_total"]
        total_reimbursement_out += totals["reimbursement_out_total"]
        total_cc_payments += totals["credit_card_total"]
        total_net += totals["net"]
        total_closing_balance += totals["closing_balance"]

    expected_net = (
        total_income
        + total_transfer_in
        + total_reimbursement_in
        - total_expenses
        - total_transfer_out
        - total_reimbursement_out
        - total_cc_payments
    )
    if total_net != expected_net:
        return None

    return SnapshotTotals(
        income=total_income,
        expenses=total_expenses,
        cc_payments=total_cc_payments,
        closing_balance=total_closing_balance,
        transfer_in=total_transfer_in,
        transfer_out=total_transfer_out,
        net=total_net,
        reimbursement_in=total_reimbursement_in,
        reimbursement_out=total_reimbursement_out,
    )


def calculate_yearly_projection(
    session: Session,
    start_month: str | None = None,
    months: int = 12,
) -> dict:
    """Run projection engine and return results (combined household view).

    Steps:
    1. Get anticipated items (all accounts combined)
    2. Get credit card projections (from Phase 2.5 functions)
    3. Get funding sources
    4. Get aggregate checking balance (all non-excluded checking accounts)
    5. Fetch actuals for closed months
    6. Call calculate_projection() with all inputs including actuals
    7. Convert result to dict for Streamlit
    """
    from datetime import datetime

    from budget_me.forecasting.engine import (
        CardPayment,
        MonthActuals,
        add_months,
        calculate_projection,
    )

    # Determine start month
    if start_month is None:
        now = datetime.now()
        start_month = f"{now.year:04d}-{now.month:02d}"

    # 1. Get anticipated items
    items_data = get_anticipated_items_for_forecast(session)

    # Convert to AnticipatedItem-like objects for the engine
    from dataclasses import dataclass

    @dataclass
    class ProjectionItem:
        name: str
        amount: Decimal
        item_type: str
        frequency: str
        start_month: str | None = None
        end_month: str | None = None

    anticipated_items = [
        ProjectionItem(
            name=item["name"],
            amount=item["amount"],
            item_type=item["item_type"],
            frequency=item["frequency"],
            start_month=item["start_month"],
            end_month=item["end_month"],
        )
        for item in items_data
    ]

    # 2. Get credit card projections - use historical average if available
    historical_cc_avg = get_historical_cc_average(session, months=3)

    # Get individual card projections for display purposes
    cc_projections = get_credit_card_projections(session)

    if historical_cc_avg is not None:
        # Use historical average for forecasting (more consistent with snapshot data)
        credit_card_payments = [
            CardPayment(
                account_id="historical_avg",
                card_name="Historical Average (3mo)",
                projected_payment=historical_cc_avg,
                source="historical_3mo_avg",
            )
        ]
    else:
        # Fall back to individual card projections if no history
        credit_card_payments = [
            CardPayment(
                account_id=cc["account_id"],
                card_name=cc["card_name"],
                projected_payment=cc["projected_payment"],
                source=cc["projection_source"],
            )
            for cc in cc_projections
        ]

    # 3. Get funding sources (not used in projection engine yet, but available)
    funding_sources = get_funding_sources(session)

    # 4. Get aggregate checking balance
    starting_balance = get_aggregate_checking_balance(session)

    # 5. Fetch actuals from closed snapshots only
    actuals_by_month = {}
    current_month = start_month
    for _ in range(months):
        snapshot_totals = get_snapshot_totals(
            session, current_month, include_open=False
        )
        if snapshot_totals:
            actuals_by_month[current_month] = MonthActuals(
                income=(
                    snapshot_totals.income
                    + snapshot_totals.transfer_in
                    + snapshot_totals.reimbursement_in
                ),
                expenses=(
                    snapshot_totals.expenses
                    + snapshot_totals.transfer_out
                    + snapshot_totals.reimbursement_out
                ),
                cc_payments=snapshot_totals.cc_payments,
                closing_balance=snapshot_totals.closing_balance,
            )
        current_month = add_months(current_month, 1)

    # 6. Calculate projection with actuals
    result = calculate_projection(
        anticipated_items=anticipated_items,
        credit_card_payments=credit_card_payments,
        starting_balance=starting_balance,
        start_month=start_month,
        months=months,
        actuals_by_month=actuals_by_month if actuals_by_month else None,
    )

    # 7. Convert to dict
    return {
        "monthly_breakdown": [
            {
                "year_month": m.year_month,
                "income": float(m.income),
                "fixed_expenses": float(m.fixed_expenses),
                "cc_payments": float(m.cc_payments),
                "total_expenses": float(m.total_expenses),
                "net": float(m.net),
                "starting_balance": float(m.starting_balance),
                "ending_balance": float(m.ending_balance),
                "funding_needed": float(m.funding_needed),
                "cumulative_funding": float(m.cumulative_funding),
                "notes": m.notes,
            }
            for m in result.monthly_breakdown
        ],
        "total_income": float(result.total_income),
        "total_fixed_expenses": float(result.total_fixed_expenses),
        "total_cc_payments": float(result.total_cc_payments),
        "total_expenses": float(result.total_expenses),
        "total_net": float(result.total_net),
        "total_funding_required": float(result.total_funding_required),
        "runway_months": result.runway_months,
        "inflection_points": result.inflection_points,
        "funding_sources": funding_sources,
        "cc_projections": cc_projections,
        "starting_balance": float(starting_balance),
    }


# === One-Time Projects (Phase 6) ===


def create_project(
    session: Session,
    name: str,
    amount: float,
    month: str,
    category: str = "Projects",
    account_id: str | None = None,
) -> dict:
    """Create one-time project as anticipated_item.

    Creates item with:
    - frequency = "one_time"
    - start_month = month
    - end_month = month
    - item_type = "expense"
    """
    from decimal import Decimal

    from budget_me.db.models.anticipated_item import AnticipatedItem

    item = AnticipatedItem(
        name=name,
        amount=Decimal(str(amount)),
        item_type="expense",
        category=category,
        frequency="one_time",
        start_month=month,
        end_month=month,
        account_id=account_id,
        active=True,
    )

    session.add(item)
    session.commit()
    session.refresh(item)

    return {
        "id": str(item.id),
        "name": item.name,
        "amount": float(item.amount),
        "month": item.start_month,
        "category": item.category,
    }


def get_projects(session: Session) -> list[dict]:
    """Get all one-time expense items (projects).

    Filter anticipated_items where frequency='one_time'
    and item_type='expense'.
    """
    from sqlalchemy import select

    from budget_me.db.models.anticipated_item import AnticipatedItem

    result = session.execute(
        select(AnticipatedItem)
        .where(
            AnticipatedItem.frequency == "one_time",
            AnticipatedItem.item_type == "expense",
            AnticipatedItem.active.is_(True),
        )
        .order_by(AnticipatedItem.start_month, AnticipatedItem.name)
    )
    items = result.scalars().all()

    return [
        {
            "id": str(item.id),
            "name": item.name,
            "amount": float(item.amount),
            "month": item.start_month,
            "category": item.category,
        }
        for item in items
    ]


def delete_project(session: Session, item_id: str) -> bool:
    """Delete a project (soft delete by setting active=False)."""
    from uuid import UUID

    from sqlalchemy import select

    from budget_me.db.models.anticipated_item import AnticipatedItem

    result = session.execute(
        select(AnticipatedItem).where(AnticipatedItem.id == UUID(item_id))
    )
    item = result.scalar_one_or_none()

    if item:
        item.active = False
        session.commit()
        return True
    return False


def inject_anticipated_item_into_open_snapshots(session: Session, item_id: UUID) -> int:
    """Inject an anticipated item into all matching open snapshots.

    Finds open snapshots where:
    - snapshot.account_id matches item.account_id (or item has no account_id)
    - snapshot.year_month is within item's start_month/end_month bounds
    - Item's frequency applies to that month (using engine's frequency logic)

    Creates SnapshotLineItem with source_item_id for each match.
    Skips if line item with this source_item_id already exists.

    Returns number of snapshots updated.

    Note: Reuses get_item_months_in_range() from forecasting engine for
    frequency logic (monthly, quarterly, annual, one_time).
    """
    from budget_me.forecasting.engine import get_item_months_in_range

    # Get the anticipated item
    item = session.execute(
        select(AnticipatedItem).where(AnticipatedItem.id == item_id)
    ).scalar_one_or_none()

    if not item:
        return 0

    # Get all open snapshots
    query = select(MonthlySnapshot).where(MonthlySnapshot.status == SnapshotStatus.OPEN)

    # Filter by account_id if item has one
    if item.account_id:
        query = query.where(MonthlySnapshot.account_id == item.account_id)

    query = (
        query.order_by(
            MonthlySnapshot.account_id,
            MonthlySnapshot.year_month,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    open_snapshots = session.execute(query).scalars().all()

    if not open_snapshots:
        return 0

    # Determine which months this item applies to
    # Get the range of all open snapshot months
    snapshot_months = [s.year_month for s in open_snapshots]
    if not snapshot_months:
        return 0

    min_month = min(snapshot_months)
    max_month = max(snapshot_months)

    # Use engine's frequency logic to get applicable months
    applicable_months = get_item_months_in_range(item, min_month, max_month)

    # Convert to set for fast lookup
    applicable_months_set = set(applicable_months)

    # Inject into matching snapshots
    count = 0
    for snapshot in open_snapshots:
        # Check if this snapshot's month is applicable
        if snapshot.year_month not in applicable_months_set:
            continue

        # Check if already injected (duplicate prevention)
        existing = session.execute(
            select(SnapshotLineItem).where(
                SnapshotLineItem.snapshot_id == snapshot.id,
                SnapshotLineItem.source_item_id == item_id,
            )
        ).scalar_one_or_none()

        if existing:
            continue

        # Create new line item
        line_item = SnapshotLineItem(
            snapshot_id=snapshot.id,
            source_item_id=item_id,
            item_type=item.item_type,
            name=item.name,
            amount=item.amount,
            skipped=False,
        )
        session.add(line_item)
        count += 1

    session.commit()
    return count


# === Plan vs Actual Comparison (Budget Performance) ===


def calculate_plan_vs_actual(
    session: Session,
    start_month: str,
    months: int = 12,
) -> dict:
    """Calculate plan vs actual for each month in the range.

    For each month:
    - Planned: Expand anticipated_items by frequency to get expected income/expenses
    - Actual: Get totals from closed snapshots
    - Variance: Actual - Planned (negative = under budget, positive = over budget)

    Returns:
        {
            "months": [
                {
                    "year_month": "2025-01",
                    "status": "closed" | "open" | "future",
                    "planned_income": 8000.0,
                    "planned_expenses": 5000.0,
                    "planned_net": 3000.0,
                    "actual_income": 8200.0,  # None if not closed
                    "actual_expenses": 4800.0,
                    "actual_net": 3400.0,
                    "variance_income": 200.0,  # None if not closed
                    "variance_expenses": -200.0,  # Negative = spent less
                    "variance_net": 400.0,  # Positive = better than planned
                },
                ...
            ],
            "summary": {
                "closed_months_count": 3,
                "total_planned_income": 24000.0,
                "total_actual_income": 24600.0,
                "total_planned_expenses": 15000.0,
                "total_actual_expenses": 14200.0,
                "total_planned_net": 9000.0,
                "total_actual_net": 10400.0,
                "total_variance_net": 1400.0,
                "avg_monthly_variance_net": 466.67,
                "performance_pct": 15.6,  # % better than planned
            }
        }
    """
    from dataclasses import dataclass
    from decimal import Decimal

    from budget_me.db.models.monthly_snapshot import SnapshotStatus
    from budget_me.forecasting.engine import add_months, expand_anticipated_items

    # Get all anticipated items
    items_data = get_anticipated_items_for_forecast(session)

    # Convert to objects for the engine
    @dataclass
    class ProjectionItem:
        name: str
        amount: Decimal
        item_type: str
        frequency: str
        start_month: str | None = None
        end_month: str | None = None

    anticipated_items = [
        ProjectionItem(
            name=item["name"],
            amount=item["amount"],
            item_type=item["item_type"],
            frequency=item["frequency"],
            start_month=item["start_month"],
            end_month=item["end_month"],
        )
        for item in items_data
    ]

    # Calculate end month
    end_month = add_months(start_month, months - 1)

    # Expand anticipated items to get planned amounts per month
    expanded = expand_anticipated_items(anticipated_items, start_month, end_month)

    # Get all snapshots in range to determine status
    snapshots_by_month = {}
    result = session.execute(
        select(MonthlySnapshot).where(
            MonthlySnapshot.year_month >= start_month,
            MonthlySnapshot.year_month <= end_month,
        )
    )
    for snapshot in result.scalars().all():
        if snapshot.year_month not in snapshots_by_month:
            snapshots_by_month[snapshot.year_month] = []
        snapshots_by_month[snapshot.year_month].append(snapshot)

    # Process each month
    month_results = []
    current_month = start_month

    # Totals for closed months
    total_planned_income = Decimal("0")
    total_planned_expenses = Decimal("0")
    total_actual_income = Decimal("0")  # Compatibility: total inflows
    total_actual_expenses = Decimal("0")  # Compatibility: total outflows
    total_actual_base_income = Decimal("0")
    total_actual_base_expenses = Decimal("0")
    total_actual_transfer_in = Decimal("0")
    total_actual_transfer_out = Decimal("0")
    total_actual_reimbursement_in = Decimal("0")
    total_actual_reimbursement_out = Decimal("0")
    total_actual_cc_payments = Decimal("0")
    total_actual_net = Decimal("0")
    closed_count = 0

    for _ in range(months):
        # Get planned values from expanded anticipated items
        month_items = expanded.get(current_month, [])
        planned_income = sum(
            item["amount"] for item in month_items if item["item_type"] == "income"
        )
        planned_expenses = sum(
            item["amount"] for item in month_items if item["item_type"] == "expense"
        )
        planned_net = planned_income - planned_expenses

        actual_base_income = None
        actual_base_expenses = None
        actual_transfer_in = None
        actual_transfer_out = None
        actual_reimbursement_in = None
        actual_reimbursement_out = None
        actual_cc_payments = None
        actual_inflows = None
        actual_outflows = None
        actual_income = None
        actual_expenses = None
        actual_net = None
        variance_income = None
        variance_expenses = None
        variance_net = None

        # Determine month status and get actuals if any snapshots are closed
        snapshots = snapshots_by_month.get(current_month, [])
        any_closed = any(s.status == SnapshotStatus.CLOSED for s in snapshots)
        all_closed = all(s.status == SnapshotStatus.CLOSED for s in snapshots)
        any_open = any(s.status == SnapshotStatus.OPEN for s in snapshots)

        if snapshots and any_closed:
            # Use "closed" if all are closed, "partial" if mixed
            status = "closed" if all_closed else "partial"
            # Get actuals from closed snapshots only
            actuals = get_snapshot_totals(session, current_month, include_open=False)
            if actuals:
                actual_base_income = float(actuals.income)
                actual_base_expenses = float(actuals.expenses)
                actual_transfer_in = float(actuals.transfer_in)
                actual_transfer_out = float(actuals.transfer_out)
                actual_reimbursement_in = float(actuals.reimbursement_in)
                actual_reimbursement_out = float(actuals.reimbursement_out)
                actual_cc_payments = float(actuals.cc_payments)
                actual_inflows = (
                    actual_base_income + actual_transfer_in + actual_reimbursement_in
                )
                actual_outflows = (
                    actual_base_expenses
                    + actual_transfer_out
                    + actual_reimbursement_out
                    + actual_cc_payments
                )
                # Keep compatibility keys, but make their inclusive cash-flow
                # semantics explicit through the granular fields below.
                actual_income = actual_inflows
                actual_expenses = actual_outflows
                actual_net = float(actuals.net)
                variance_income = actual_income - float(planned_income)
                variance_expenses = actual_expenses - float(planned_expenses)
                variance_net = actual_net - float(planned_net)

                # Accumulate totals
                total_planned_income += planned_income
                total_planned_expenses += planned_expenses
                total_actual_income += (
                    actuals.income + actuals.transfer_in + actuals.reimbursement_in
                )
                total_actual_expenses += (
                    actuals.expenses
                    + actuals.transfer_out
                    + actuals.reimbursement_out
                    + actuals.cc_payments
                )
                total_actual_base_income += actuals.income
                total_actual_base_expenses += actuals.expenses
                total_actual_transfer_in += actuals.transfer_in
                total_actual_transfer_out += actuals.transfer_out
                total_actual_reimbursement_in += actuals.reimbursement_in
                total_actual_reimbursement_out += actuals.reimbursement_out
                total_actual_cc_payments += actuals.cc_payments
                total_actual_net += actuals.net
                closed_count += 1
        elif any_open:
            status = "open"
        else:
            status = "future"

        month_results.append(
            {
                "year_month": current_month,
                "status": status,
                "planned_income": float(planned_income),
                "planned_expenses": float(planned_expenses),
                "planned_net": float(planned_net),
                "actual_income": actual_income,
                "actual_expenses": actual_expenses,
                "actual_inflows": actual_inflows,
                "actual_outflows": actual_outflows,
                "actual_net": actual_net,
                "actual_base_income": actual_base_income,
                "actual_base_expenses": actual_base_expenses,
                "actual_transfer_in": actual_transfer_in,
                "actual_transfer_out": actual_transfer_out,
                "actual_reimbursement_in": actual_reimbursement_in,
                "actual_reimbursement_out": actual_reimbursement_out,
                "actual_cc_payments": actual_cc_payments,
                "variance_income": variance_income,
                "variance_expenses": variance_expenses,
                "variance_net": variance_net,
            }
        )

        current_month = add_months(current_month, 1)

    # Calculate summary
    total_planned_net = total_planned_income - total_planned_expenses
    total_variance_net = total_actual_net - total_planned_net

    if closed_count > 0:
        avg_monthly_variance = float(total_variance_net) / closed_count
        if float(total_planned_net) != 0:
            performance_pct = (
                float(total_variance_net) / abs(float(total_planned_net))
            ) * 100
        else:
            performance_pct = 0.0
    else:
        avg_monthly_variance = 0.0
        performance_pct = 0.0

    return {
        "months": month_results,
        "summary": {
            "closed_months_count": closed_count,
            "total_planned_income": float(total_planned_income),
            "total_actual_income": float(total_actual_income),
            "total_planned_expenses": float(total_planned_expenses),
            "total_actual_expenses": float(total_actual_expenses),
            "total_actual_inflows": float(total_actual_income),
            "total_actual_outflows": float(total_actual_expenses),
            "total_actual_base_income": float(total_actual_base_income),
            "total_actual_base_expenses": float(total_actual_base_expenses),
            "total_actual_transfer_in": float(total_actual_transfer_in),
            "total_actual_transfer_out": float(total_actual_transfer_out),
            "total_actual_reimbursement_in": float(total_actual_reimbursement_in),
            "total_actual_reimbursement_out": float(total_actual_reimbursement_out),
            "total_actual_cc_payments": float(total_actual_cc_payments),
            "total_planned_net": float(total_planned_net),
            "total_actual_net": float(total_actual_net),
            "total_variance_net": float(total_variance_net),
            "avg_monthly_variance_net": avg_monthly_variance,
            "performance_pct": performance_pct,
        },
    }
