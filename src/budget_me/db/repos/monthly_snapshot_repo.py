"""Repository for MonthlySnapshot operations."""

import uuid
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from budget_me.db.models.account import PaymentStrategy
from budget_me.db.models.account_balance_snapshot import AccountBalanceSnapshot
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.repos.base import BaseRepository


class MonthlySnapshotRepo(BaseRepository[MonthlySnapshot]):
    """Repository boundary for snapshots and their child entities.

    Closed snapshots are immutable through this application repository. Direct
    raw SQL is outside this boundary and must be controlled separately.
    """

    model = MonthlySnapshot
    _GUARDED_CLOSE_FIELDS = {
        "status",
        "closing_balance",
        "closing_balance_frozen",
        "closed_at",
    }

    @staticmethod
    def _assert_snapshot_open(snapshot: MonthlySnapshot) -> None:
        """Reject application-level financial mutations after close."""
        if snapshot.status == SnapshotStatus.CLOSED:
            raise RuntimeError(
                f"Monthly snapshot {snapshot.id} is closed and immutable at the "
                "repository application boundary"
            )

    async def _require_open_snapshot(self, snapshot_id: uuid.UUID) -> MonthlySnapshot:
        """Lock and refresh a snapshot before permitting a mutation."""
        snapshot = await self.session.get(
            MonthlySnapshot,
            snapshot_id,
            populate_existing=True,
            with_for_update=True,
        )
        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        self._assert_snapshot_open(snapshot)
        return snapshot

    async def update(self, instance: MonthlySnapshot, **kwargs) -> MonthlySnapshot:
        """Update an open snapshot without bypassing guarded close fields."""
        guarded_fields = self._GUARDED_CLOSE_FIELDS.intersection(kwargs)
        if guarded_fields:
            fields = ", ".join(sorted(guarded_fields))
            raise RuntimeError(
                f"MonthlySnapshotRepo.update() cannot set guarded close fields "
                f"({fields}); use "
                "budget_me.snapshots.service.close_snapshot() for guarded closes"
            )
        snapshot = await self._require_open_snapshot(instance.id)
        return await super().update(snapshot, **kwargs)

    async def get_by_year_month(
        self, year_month: str, account_id: str
    ) -> MonthlySnapshot | None:
        """Get snapshot by year_month and account_id."""
        stmt = (
            select(MonthlySnapshot)
            .where(MonthlySnapshot.year_month == year_month)
            .where(MonthlySnapshot.account_id == account_id)
            .options(
                selectinload(MonthlySnapshot.line_items),
                selectinload(MonthlySnapshot.credit_cards),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self) -> list[MonthlySnapshot]:
        """Get all snapshots ordered by year_month desc."""
        stmt = select(MonthlySnapshot).order_by(MonthlySnapshot.year_month.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_for_account(self, account_id: str) -> list[MonthlySnapshot]:
        """Get all snapshots for a specific account ordered by year_month desc."""
        stmt = (
            select(MonthlySnapshot)
            .where(MonthlySnapshot.account_id == account_id)
            .order_by(MonthlySnapshot.year_month.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_open_snapshots(self) -> list[MonthlySnapshot]:
        """Get snapshots with status='open'."""
        stmt = select(MonthlySnapshot).where(
            MonthlySnapshot.status == SnapshotStatus.OPEN
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, year_month: str, account_id: str) -> MonthlySnapshot:
        """Create empty snapshot with validation."""
        # Validate year_month format
        datetime.strptime(year_month, "%Y-%m")

        snapshot = MonthlySnapshot(
            year_month=year_month, account_id=account_id, status=SnapshotStatus.OPEN
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def create_with_defaults(
        self, year_month: str, account_id: str
    ) -> MonthlySnapshot:
        """Create snapshot and populate from templates."""
        # Validate year_month format
        datetime.strptime(year_month, "%Y-%m")

        # Create snapshot
        snapshot = await self.create(year_month, account_id)

        # TODO: Populate line items from AnticipatedItems
        # TODO: Populate credit cards from Accounts

        # Calculate and update totals
        await self.update_totals(
            snapshot.id,
            income=Decimal("0.00"),
            expense=Decimal("0.00"),
            credit_card=Decimal("0.00"),
            net=Decimal("0.00"),
            reimbursement_in=Decimal("0.00"),
            reimbursement_out=Decimal("0.00"),
        )

        return snapshot

    async def close(self, snapshot_id: uuid.UUID) -> MonthlySnapshot:
        """Reject unguarded snapshot closes at the repository boundary."""
        raise RuntimeError(
            "MonthlySnapshotRepo.close() is disabled; use "
            "budget_me.snapshots.service.close_snapshot() for guarded closes"
        )

    async def update_totals(
        self,
        snapshot_id: uuid.UUID,
        income: Decimal,
        expense: Decimal,
        credit_card: Decimal,
        net: Decimal,
        transfer_in: Decimal | None = None,
        transfer_out: Decimal | None = None,
        reimbursement_in: Decimal | None = None,
        reimbursement_out: Decimal | None = None,
    ) -> None:
        """Cache totals, defaulting optional planned reimbursements to zero."""
        snapshot = await self._require_open_snapshot(snapshot_id)
        snapshot.income_total = income
        snapshot.expense_total = expense
        snapshot.transfer_in_total = transfer_in
        snapshot.transfer_out_total = transfer_out
        snapshot.reimbursement_in_total = (
            reimbursement_in if reimbursement_in is not None else Decimal("0.00")
        )
        snapshot.reimbursement_out_total = (
            reimbursement_out if reimbursement_out is not None else Decimal("0.00")
        )
        snapshot.credit_card_total = credit_card
        snapshot.net = net
        await self.session.flush()

    async def delete(self, snapshot_id: uuid.UUID) -> None:
        """Delete an open snapshot (cascades to children)."""
        snapshot = await self._require_open_snapshot(snapshot_id)
        await self.session.delete(snapshot)
        await self.session.flush()

    # Line Item operations
    async def get_line_items(
        self, snapshot_id: uuid.UUID, item_type: str | None = None
    ) -> list[SnapshotLineItem]:
        """Get line items for snapshot (includes skipped)."""
        stmt = select(SnapshotLineItem).where(
            SnapshotLineItem.snapshot_id == snapshot_id
        )
        if item_type:
            stmt = stmt.where(SnapshotLineItem.item_type == item_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_line_item(
        self,
        snapshot_id: uuid.UUID,
        item_type: str,
        name: str,
        amount: Decimal,
        category: str | None = None,
        source_item_id: uuid.UUID | None = None,
        is_one_time: bool = False,
    ) -> SnapshotLineItem:
        """Create line item."""
        await self._require_open_snapshot(snapshot_id)
        item = SnapshotLineItem(
            snapshot_id=snapshot_id,
            item_type=item_type,
            name=name,
            amount=amount,
            category=category,
            source_item_id=source_item_id,
            is_one_time=is_one_time,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def update_line_item(self, item_id: uuid.UUID, **kwargs) -> SnapshotLineItem:
        """Update line item fields."""
        stmt = select(SnapshotLineItem).where(SnapshotLineItem.id == item_id)
        result = await self.session.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            raise ValueError(f"Line item {item_id} not found")
        await self._require_open_snapshot(item.snapshot_id)

        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)

        await self.session.flush()
        return item

    async def skip_line_item(
        self, item_id: uuid.UUID, skipped: bool
    ) -> SnapshotLineItem:
        """Toggle skipped status (soft delete pattern)."""
        return await self.update_line_item(item_id, skipped=skipped)

    # Credit Card operations
    async def get_credit_cards(
        self, snapshot_id: uuid.UUID
    ) -> list[SnapshotCreditCard]:
        """Get credit cards for snapshot."""
        stmt = select(SnapshotCreditCard).where(
            SnapshotCreditCard.snapshot_id == snapshot_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_credit_card(
        self,
        snapshot_id: uuid.UUID,
        account_id: str,
        statement_balance: Decimal | None,
        payment_strategy: str,
        fixed_amount: Decimal | None,
        due_date: datetime | None = None,
    ) -> SnapshotCreditCard:
        """Create credit card entry with calculated payment."""
        await self._require_open_snapshot(snapshot_id)
        # Calculate payment based on strategy
        if payment_strategy == PaymentStrategy.PAY_IN_FULL:
            calculated_payment = statement_balance or Decimal("0.00")
        else:  # PROMOTIONAL_PAYDOWN
            calculated_payment = fixed_amount or Decimal("0.00")

        card = SnapshotCreditCard(
            snapshot_id=snapshot_id,
            account_id=account_id,
            statement_balance=statement_balance,
            payment_strategy=payment_strategy,
            fixed_payment_amount=fixed_amount,
            calculated_payment=calculated_payment,
            due_date=due_date,
        )
        self.session.add(card)
        await self.session.flush()
        return card

    async def update_credit_card(
        self, card_id: uuid.UUID, **kwargs
    ) -> SnapshotCreditCard:
        """Update credit card fields."""
        stmt = select(SnapshotCreditCard).where(SnapshotCreditCard.id == card_id)
        result = await self.session.execute(stmt)
        card = result.scalar_one_or_none()
        if not card:
            raise ValueError(f"Credit card {card_id} not found")
        await self._require_open_snapshot(card.snapshot_id)

        for key, value in kwargs.items():
            if hasattr(card, key):
                setattr(card, key, value)

        await self.session.flush()
        return card

    async def recalculate_payment(self, card_id: uuid.UUID) -> SnapshotCreditCard:
        """Recalculate payment based on strategy."""
        stmt = select(SnapshotCreditCard).where(SnapshotCreditCard.id == card_id)
        result = await self.session.execute(stmt)
        card = result.scalar_one_or_none()
        if not card:
            raise ValueError(f"Credit card {card_id} not found")
        await self._require_open_snapshot(card.snapshot_id)

        # Simple if/else calculation
        if card.payment_strategy == PaymentStrategy.PAY_IN_FULL:
            card.calculated_payment = card.statement_balance or Decimal("0.00")
        else:  # PROMOTIONAL_PAYDOWN
            card.calculated_payment = card.fixed_payment_amount or Decimal("0.00")

        await self.session.flush()
        return card

    # Balance Calculation Methods
    async def get_starting_balance(
        self, account_id: str, year_month: str
    ) -> tuple[Decimal | None, bool]:
        """
        Get starting balance for a month.

        Returns:
            tuple[Decimal | None, bool]: (balance, is_frozen)
                - balance: The starting balance, or None if cannot be determined
                - is_frozen: True if from closed previous month, False otherwise

        Algorithm:
        1. Check if current month's snapshot has starting_balance set directly
           → If it matches M-1's explicitly frozen close: Return
             (starting_balance, True)
           → Otherwise: Return (starting_balance, False)
        2. Get previous month (M-1)
        3. Check if M-1 snapshot has closing_balance set
           → If closed: Return (closing_balance, True)
           → If open: Return (closing_balance, False) as estimate
        4. Query account_balance_snapshots for last day of M-1
           → Return (balance_current, False)
        5. Return (None, False) if no data available
        """
        # Parse year_month to get previous month
        year, month = map(int, year_month.split("-"))
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        prev_year_month = f"{prev_year:04d}-{prev_month:02d}"

        current_snapshot = await self.get_by_year_month(year_month, account_id)
        prev_snapshot = await self.get_by_year_month(prev_year_month, account_id)

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

        # Check for previous month snapshot with closing_balance
        if prev_snapshot and prev_snapshot.closing_balance is not None:
            # If closed, it's frozen; if open, it's an estimate
            is_frozen = prev_snapshot.status == SnapshotStatus.CLOSED
            return (prev_snapshot.closing_balance, is_frozen)

        # Carry the calculated close of an open prior month into future
        # projections even though that close has not been frozen yet.
        if prev_snapshot and prev_snapshot.status == SnapshotStatus.OPEN:
            prev_starting, _ = await self.get_starting_balance(
                account_id, prev_year_month
            )
            if prev_starting is not None:
                calculated = (
                    prev_starting
                    + (prev_snapshot.income_total or Decimal("0.00"))
                    + (prev_snapshot.transfer_in_total or Decimal("0.00"))
                    + (prev_snapshot.reimbursement_in_total or Decimal("0.00"))
                    - (prev_snapshot.expense_total or Decimal("0.00"))
                    - (prev_snapshot.transfer_out_total or Decimal("0.00"))
                    - (prev_snapshot.reimbursement_out_total or Decimal("0.00"))
                    - (prev_snapshot.credit_card_total or Decimal("0.00"))
                )
                return (calculated, False)

        # Fall back to balance snapshot for last day of previous month
        last_day = monthrange(prev_year, prev_month)[1]
        last_date = date(prev_year, prev_month, last_day)

        stmt = select(AccountBalanceSnapshot).where(
            AccountBalanceSnapshot.account_id == account_id,
            AccountBalanceSnapshot.snapshot_date == last_date,
        )
        result = await self.session.execute(stmt)
        balance_snapshot = result.scalar_one_or_none()

        if balance_snapshot:
            return (balance_snapshot.balance_current, False)

        # No data available
        return (None, False)

    async def get_closing_balance(
        self, account_id: str, year_month: str
    ) -> tuple[Decimal | None, bool]:
        """
        Get closing balance for a month.

        Returns:
            tuple[Decimal | None, bool]: (balance, is_frozen)
                - balance: The closing balance, or None if cannot be determined
                - is_frozen: True if from closed month, False if calculated/estimated

        Algorithm:
        1. Get this month's snapshot
        2. If closed and has closing_balance
           → Return (closing_balance, True)
        3. Query account_balance_snapshots for last day of this month
           → If exists, return (balance_current, False)
        4. Calculate: starting + income + transfers_in + reimbursements_in
           - expenses - transfers_out - reimbursements_out - card payments
           → If starting_balance is None, return (None, False)
           → Use Decimal("0.00") as default for None totals
           → Return (calculated, False)
        """
        # Get this month's snapshot
        snapshot = await self.get_by_year_month(year_month, account_id)

        # If closed with frozen balance, return it
        if (
            snapshot
            and snapshot.status == SnapshotStatus.CLOSED
            and snapshot.closing_balance is not None
        ):
            return (snapshot.closing_balance, True)

        # Prefer the reconciled balance (starting + net) over Plaid's daily
        # capture. The daily capture can miss same-day postings (e.g. a check
        # that clears on the last day of the month), which silently drifts the
        # balance and then cascades into every following month. The reconciled
        # net ties to the actual transactions, so it is authoritative. Fall back
        # to the daily capture only when we can't reconcile.
        if snapshot:
            starting_balance, _ = await self.get_starting_balance(
                account_id, year_month
            )
            if starting_balance is not None:
                calculated = (
                    starting_balance
                    + (snapshot.income_total or Decimal("0.00"))
                    + (snapshot.transfer_in_total or Decimal("0.00"))
                    + (snapshot.reimbursement_in_total or Decimal("0.00"))
                    - (snapshot.expense_total or Decimal("0.00"))
                    - (snapshot.transfer_out_total or Decimal("0.00"))
                    - (snapshot.reimbursement_out_total or Decimal("0.00"))
                    - (snapshot.credit_card_total or Decimal("0.00"))
                )
                return (calculated, False)

        # Fall back to the daily balance capture for the last day of the month
        year, month = map(int, year_month.split("-"))
        last_day = monthrange(year, month)[1]
        last_date = date(year, month, last_day)
        result = await self.session.execute(
            select(AccountBalanceSnapshot).where(
                AccountBalanceSnapshot.account_id == account_id,
                AccountBalanceSnapshot.snapshot_date == last_date,
            )
        )
        balance_snapshot = result.scalar_one_or_none()
        if balance_snapshot:
            return (balance_snapshot.balance_current, False)

        return (None, False)

    async def freeze_closing_balance(self, snapshot_id: uuid.UUID) -> None:
        """Reject unguarded closing-balance freezes at this boundary."""
        raise RuntimeError(
            "MonthlySnapshotRepo.freeze_closing_balance() is disabled; use "
            "budget_me.snapshots.service.close_snapshot() for guarded closes"
        )
