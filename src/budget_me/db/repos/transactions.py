"""Repository for Transaction operations."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from budget_me.db.models.transaction import Transaction
from budget_me.db.repos.base import BaseRepository


class TransactionsRepo(BaseRepository[Transaction]):
    """Repository for Transaction CRUD and query operations."""

    model = Transaction

    async def find_by_plaid_transaction_id(
        self, plaid_transaction_id: str
    ) -> Transaction | None:
        """Find a transaction by its Plaid transaction ID.

        Args:
            plaid_transaction_id: The Plaid-assigned transaction identifier.

        Returns:
            The Transaction if found, None otherwise.
        """
        stmt = select(Transaction).where(
            Transaction.plaid_transaction_id == plaid_transaction_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_date_range(
        self,
        start_date: date,
        end_date: date,
        plaid_item_id: uuid.UUID | None = None,
    ) -> list[Transaction]:
        """Find transactions within a date range.

        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            plaid_item_id: Optional filter by PlaidItem.

        Returns:
            List of transactions in the date range.
        """
        stmt = select(Transaction).where(
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )

        if plaid_item_id:
            stmt = stmt.where(Transaction.plaid_item_id == plaid_item_id)

        stmt = stmt.order_by(Transaction.date.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_plaid_item(
        self, plaid_item_id: uuid.UUID, limit: int = 100
    ) -> list[Transaction]:
        """Find transactions for a specific PlaidItem.

        Args:
            plaid_item_id: The PlaidItem UUID.
            limit: Maximum number of transactions to return.

        Returns:
            List of transactions for the PlaidItem.
        """
        stmt = (
            select(Transaction)
            .where(Transaction.plaid_item_id == plaid_item_id)
            .order_by(Transaction.date.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        plaid_transaction_id: str,
        plaid_item_id: uuid.UUID,
        account_id: str,
        transaction_date: date,
        amount: Decimal,
        name: str,
        **kwargs: Any,
    ) -> tuple[Transaction, bool]:
        """Insert or update a transaction.

        Uses PostgreSQL INSERT ... ON CONFLICT to handle upserts efficiently.

        Args:
            plaid_transaction_id: The Plaid transaction ID (unique key).
            plaid_item_id: The PlaidItem UUID.
            account_id: The Plaid account ID.
            transaction_date: The transaction date.
            amount: The transaction amount.
            name: The transaction name/description.
            **kwargs: Additional transaction fields.

        Returns:
            Tuple of (Transaction, was_created) where was_created is True
            if a new record was created, False if updated.
        """
        # Check if exists first to determine if created
        existing = await self.find_by_plaid_transaction_id(plaid_transaction_id)
        was_created = existing is None

        values = {
            "plaid_transaction_id": plaid_transaction_id,
            "plaid_item_id": plaid_item_id,
            "account_id": account_id,
            "date": transaction_date,
            "amount": amount,
            "name": name,
            **kwargs,
        }

        stmt = insert(Transaction).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["plaid_transaction_id"],
            set_={
                "account_id": stmt.excluded.account_id,
                "date": stmt.excluded.date,
                "amount": stmt.excluded.amount,
                "name": stmt.excluded.name,
                "authorized_date": stmt.excluded.authorized_date,
                "merchant_name": stmt.excluded.merchant_name,
                "pending": stmt.excluded.pending,
                "payment_channel": stmt.excluded.payment_channel,
                "category_primary": stmt.excluded.category_primary,
                "category_detailed": stmt.excluded.category_detailed,
                "merchant_id": stmt.excluded.merchant_id,
                "normalized_merchant": stmt.excluded.normalized_merchant,
                "raw": stmt.excluded.raw,
                "updated_at": func.clock_timestamp(),
            },
        )

        await self.session.execute(stmt)
        await self.session.flush()

        # Fetch the record to return
        transaction = await self.find_by_plaid_transaction_id(plaid_transaction_id)
        return transaction, was_created

    async def bulk_upsert(self, transactions: list[dict[str, Any]]) -> tuple[int, int]:
        """Bulk upsert multiple transactions.

        Args:
            transactions: List of transaction dictionaries with required fields.

        Returns:
            Tuple of (added_count, modified_count).
        """
        if not transactions:
            return 0, 0

        # Get existing transaction IDs
        plaid_ids = [t["plaid_transaction_id"] for t in transactions]
        stmt = select(Transaction.plaid_transaction_id).where(
            Transaction.plaid_transaction_id.in_(plaid_ids)
        )
        result = await self.session.execute(stmt)
        existing_ids = set(result.scalars().all())

        added = 0
        modified = 0

        for tx_data in transactions:
            if tx_data["plaid_transaction_id"] in existing_ids:
                modified += 1
            else:
                added += 1

        # Perform bulk upsert
        stmt = insert(Transaction).values(transactions)
        stmt = stmt.on_conflict_do_update(
            index_elements=["plaid_transaction_id"],
            set_={
                "account_id": stmt.excluded.account_id,
                "date": stmt.excluded.date,
                "amount": stmt.excluded.amount,
                "name": stmt.excluded.name,
                "authorized_date": stmt.excluded.authorized_date,
                "merchant_name": stmt.excluded.merchant_name,
                "pending": stmt.excluded.pending,
                "payment_channel": stmt.excluded.payment_channel,
                "category_primary": stmt.excluded.category_primary,
                "category_detailed": stmt.excluded.category_detailed,
                "merchant_id": stmt.excluded.merchant_id,
                "normalized_merchant": stmt.excluded.normalized_merchant,
                "raw": stmt.excluded.raw,
                "updated_at": func.clock_timestamp(),
            },
        )

        await self.session.execute(stmt)
        await self.session.flush()

        return added, modified

    async def bulk_upsert_with_details(
        self, transactions: list[dict[str, Any]]
    ) -> tuple[int, int, list[Transaction], list[tuple[Transaction, list[str]]]]:
        """Bulk upsert with detailed tracking of added and modified transactions.

        Args:
            transactions: List of transaction dictionaries with required fields.

        Returns:
            Tuple of (added_count, modified_count, added_transactions, modified_with_changes).
            modified_with_changes is a list of (Transaction, changes_list) tuples.
        """
        if not transactions:
            return 0, 0, [], []

        # Fields to compare for change detection
        tracked_fields = ["amount", "name", "date", "pending", "merchant_name"]

        # Get existing transactions with full data for comparison
        plaid_ids = [t["plaid_transaction_id"] for t in transactions]
        stmt = select(Transaction).where(
            Transaction.plaid_transaction_id.in_(plaid_ids)
        )
        result = await self.session.execute(stmt)
        existing_txns = {t.plaid_transaction_id: t for t in result.scalars().all()}

        # Track which are adds vs modifies and detect changes
        added_plaid_ids: list[str] = []
        modified_data: dict[str, list[str]] = {}  # plaid_id -> list of changed fields

        for tx_data in transactions:
            plaid_id = tx_data["plaid_transaction_id"]
            if plaid_id in existing_txns:
                # Detect which fields changed
                existing = existing_txns[plaid_id]
                changes: list[str] = []
                for field_name in tracked_fields:
                    old_val = getattr(existing, field_name, None)
                    new_val = tx_data.get(field_name)
                    # Normalize for comparison (handle Decimal vs float, etc.)
                    if old_val != new_val:
                        changes.append(field_name)
                if changes:
                    modified_data[plaid_id] = changes
            else:
                added_plaid_ids.append(plaid_id)

        added_count = len(added_plaid_ids)
        modified_count = len(modified_data)

        # Perform bulk upsert
        stmt = insert(Transaction).values(transactions)
        stmt = stmt.on_conflict_do_update(
            index_elements=["plaid_transaction_id"],
            set_={
                "account_id": stmt.excluded.account_id,
                "date": stmt.excluded.date,
                "amount": stmt.excluded.amount,
                "name": stmt.excluded.name,
                "authorized_date": stmt.excluded.authorized_date,
                "merchant_name": stmt.excluded.merchant_name,
                "pending": stmt.excluded.pending,
                "payment_channel": stmt.excluded.payment_channel,
                "category_primary": stmt.excluded.category_primary,
                "category_detailed": stmt.excluded.category_detailed,
                "merchant_id": stmt.excluded.merchant_id,
                "normalized_merchant": stmt.excluded.normalized_merchant,
                "raw": stmt.excluded.raw,
                "updated_at": func.clock_timestamp(),
            },
        )

        await self.session.execute(stmt)
        await self.session.flush()

        # Fetch the newly upserted records to get their IDs
        stmt = select(Transaction).where(
            Transaction.plaid_transaction_id.in_(plaid_ids)
        )
        result = await self.session.execute(stmt)
        all_txns = {t.plaid_transaction_id: t for t in result.scalars().all()}

        # Build added transactions list
        added_txns = [all_txns[pid] for pid in added_plaid_ids if pid in all_txns]

        # Build modified transactions with changes
        modified_with_changes: list[tuple[Transaction, list[str]]] = []
        for plaid_id, changes in modified_data.items():
            if plaid_id in all_txns:
                modified_with_changes.append((all_txns[plaid_id], changes))

        return added_count, modified_count, added_txns, modified_with_changes

    async def delete_by_plaid_id(self, plaid_transaction_id: str) -> bool:
        """Delete a transaction by its Plaid transaction ID.

        Args:
            plaid_transaction_id: The Plaid transaction ID.

        Returns:
            True if a transaction was deleted, False otherwise.
        """
        stmt = delete(Transaction).where(
            Transaction.plaid_transaction_id == plaid_transaction_id
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def delete_by_plaid_ids(self, plaid_transaction_ids: list[str]) -> int:
        """Delete multiple transactions by their Plaid transaction IDs.

        Args:
            plaid_transaction_ids: List of Plaid transaction IDs.

        Returns:
            Number of transactions deleted.
        """
        if not plaid_transaction_ids:
            return 0

        stmt = delete(Transaction).where(
            Transaction.plaid_transaction_id.in_(plaid_transaction_ids)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def get_uncategorized_since(
        self,
        days: int | None = None,
    ) -> list[Transaction]:
        """Get transactions without budget categories.

        Args:
            days: Look back N days. If None, get all uncategorized.

        Returns:
            List of uncategorized transactions ordered by date desc.
        """
        query = select(Transaction).where(Transaction.budget_category.is_(None))

        if days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            query = query.where(Transaction.date >= cutoff.date())

        query = query.order_by(Transaction.date.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def bulk_update_budget_category(
        self,
        transaction_ids: list[uuid.UUID],
        category: str,
    ) -> int:
        """Bulk update budget category for transactions.

        Args:
            transaction_ids: List of transaction IDs to update
            category: Budget category to assign

        Returns:
            Number of transactions updated
        """
        if not transaction_ids:
            return 0

        stmt = (
            update(Transaction)
            .where(Transaction.id.in_(transaction_ids))
            .values(budget_category=category)
        )

        result = await self.session.execute(stmt)
        return result.rowcount

    async def update_reimbursable(
        self,
        transaction_ids: list[uuid.UUID],
        reimbursable: bool,
        status: str,
        notes: dict[uuid.UUID, str],
    ) -> int:
        """Update reimbursable fields for transactions.

        Args:
            transaction_ids: List of transaction IDs to update
            reimbursable: Whether expense will be reimbursed
            status: Reimbursement status ("pending" or "received")
            notes: Mapping of transaction ID to group tag/note

        Returns:
            Number of transactions updated
        """
        if not transaction_ids:
            return 0

        # Update each transaction with its specific note
        updated = 0
        for txn_id in transaction_ids:
            note = notes.get(txn_id, "")
            stmt = (
                update(Transaction)
                .where(Transaction.id == txn_id)
                .values(
                    reimbursable=reimbursable,
                    reimbursement_status=status,
                    reimbursement_note=note,
                )
            )
            result = await self.session.execute(stmt)
            updated += result.rowcount

        return updated

    async def set_project_tag(
        self,
        transaction_ids: list[uuid.UUID],
        project_tag: str | None,
    ) -> int:
        """Set (or clear) the cross-month project tag on transactions.

        The project tag is budget-neutral: it does not affect any budget,
        snapshot, or categorization calculation. It exists purely to roll up
        spending for a project (e.g. a trip or landscaping job) across months.

        Args:
            transaction_ids: List of transaction IDs to update
            project_tag: Tag to assign, or None to clear the tag

        Returns:
            Number of transactions updated
        """
        if not transaction_ids:
            return 0

        stmt = (
            update(Transaction)
            .where(Transaction.id.in_(transaction_ids))
            .values(project_tag=project_tag)
        )

        result = await self.session.execute(stmt)
        return result.rowcount

    async def get_project_summary(
        self,
        project_tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """Summarize spending by project tag across all months.

        Args:
            project_tag: If given, summarize only this tag. Otherwise summarize
                every tag present in the data.

        Returns:
            One dict per project tag, ordered by tag name:
                {
                    "project_tag": str,
                    "total": Decimal,        # net sum of amounts (outflows positive)
                    "count": int,
                    "months": [              # ordered by month ascending
                        {"month": "YYYY-MM", "total": Decimal, "count": int},
                        ...
                    ],
                }
        """
        month_col = func.to_char(Transaction.date, "YYYY-MM").label("month")
        query = (
            select(
                Transaction.project_tag,
                month_col,
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
                func.count().label("count"),
            )
            .where(Transaction.project_tag.is_not(None))
            .group_by(Transaction.project_tag, month_col)
            .order_by(Transaction.project_tag, month_col)
        )
        if project_tag is not None:
            query = query.where(Transaction.project_tag == project_tag)

        rows = (await self.session.execute(query)).all()

        summaries: dict[str, dict[str, Any]] = {}
        for tag, month, total, count in rows:
            entry = summaries.setdefault(
                tag,
                {"project_tag": tag, "total": Decimal("0"), "count": 0, "months": []},
            )
            entry["total"] += total
            entry["count"] += count
            entry["months"].append({"month": month, "total": total, "count": count})

        return list(summaries.values())

    async def get_card_payments(
        self,
        account_id: str,
        start_date: date,
        end_date: date,
    ) -> list[Transaction]:
        """Get payments received on a credit-card account in a date range.

        Reads the card account's OWN transaction feed for posted entries Plaid
        classifies as credit-card payments. It recognizes the current PFC detailed
        value ``LOAN_PAYMENTS_CREDIT_CARD_PAYMENT`` in either raw or normalized
        storage, plus the legacy normalized detail ``Payment, Credit Card``. On a
        card account a payment is a
        negative amount (it reduces the balance owed). Pending entries are
        excluded so a pending payment and its posted replacement cannot both be
        counted.

        This is the deterministic way to attribute a checking-side autopay to a
        specific card when several cards share one institution: the payment is
        recorded against the card account itself, so no name/amount guessing is
        needed.

        Args:
            account_id: The credit-card account id.
            start_date: Range start (inclusive).
            end_date: Range end (inclusive).

        Returns:
            Payment transactions ordered by date ascending.
        """
        detailed = Transaction.raw["personal_finance_category"]["detailed"].astext
        stmt = (
            select(Transaction)
            .where(
                Transaction.account_id == account_id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                Transaction.amount < 0,
                Transaction.pending.is_(False),
                or_(
                    detailed == "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",
                    Transaction.category_detailed
                    == "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",
                    Transaction.category_detailed == "Payment, Credit Card",
                ),
            )
            .order_by(Transaction.date)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_card_payments(
        self,
        account_id: str,
        start_date: date,
        end_date: date,
    ) -> list[Transaction]:
        """Get pending card-side payments in a date range.

        This deliberately remains separate from :meth:`get_card_payments` so
        callers cannot accidentally mix pending activity into posted actuals.
        A pending payment is instead a reconciliation blocker until Plaid
        replaces or removes it.

        Args:
            account_id: The credit-card account id.
            start_date: Range start (inclusive).
            end_date: Range end (inclusive).

        Returns:
            Pending payment transactions ordered by date ascending.
        """
        detailed = Transaction.raw["personal_finance_category"]["detailed"].astext
        stmt = (
            select(Transaction)
            .where(
                Transaction.account_id == account_id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                Transaction.amount < 0,
                Transaction.pending.is_(True),
                or_(
                    detailed == "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",
                    Transaction.category_detailed
                    == "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",
                    Transaction.category_detailed == "Payment, Credit Card",
                ),
            )
            .order_by(Transaction.date)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
