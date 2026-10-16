"""Persistence operations for Plaid investment data."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from budget_me.db.models.investment import (
    InvestmentHolding,
    InvestmentHoldingSnapshot,
    InvestmentSecurity,
    InvestmentTransaction,
)
from budget_me.db.repos.base import BaseRepository


class InvestmentsRepo(BaseRepository[InvestmentHolding]):
    """Store current holdings, daily snapshots, and investment transactions."""

    model = InvestmentHolding

    async def upsert_securities(self, securities: list[dict[str, Any]]) -> int:
        """Insert or update securities by Plaid security ID."""
        if not securities:
            return 0

        statement = insert(InvestmentSecurity).values(securities)
        statement = statement.on_conflict_do_update(
            index_elements=["security_id"],
            set_={
                "institution_security_id": statement.excluded.institution_security_id,
                "institution_id": statement.excluded.institution_id,
                "name": statement.excluded.name,
                "ticker_symbol": statement.excluded.ticker_symbol,
                "security_type": statement.excluded.security_type,
                "close_price": statement.excluded.close_price,
                "close_price_as_of": statement.excluded.close_price_as_of,
                "iso_currency_code": statement.excluded.iso_currency_code,
                "unofficial_currency_code": statement.excluded.unofficial_currency_code,
                "raw": statement.excluded.raw,
                "updated_at": func.clock_timestamp(),
            },
        )
        await self.session.execute(statement)
        await self.session.flush()
        return len(securities)

    async def replace_holdings(
        self, plaid_item_id: uuid.UUID, holdings: list[dict[str, Any]]
    ) -> int:
        """Atomically replace the latest holding set for one Plaid Item."""
        await self.session.execute(
            delete(InvestmentHolding).where(
                InvestmentHolding.plaid_item_id == plaid_item_id
            )
        )
        if holdings:
            await self.session.execute(insert(InvestmentHolding).values(holdings))
        await self.session.flush()
        return len(holdings)

    async def upsert_holding_snapshots(
        self,
        holdings: list[dict[str, Any]],
        snapshot_date: date,
    ) -> int:
        """Store one end-of-day observation for every returned holding."""
        if not holdings:
            return 0

        snapshots = [
            {
                "plaid_item_id": holding["plaid_item_id"],
                "account_id": holding["account_id"],
                "security_id": holding["security_id"],
                "snapshot_date": snapshot_date,
                "quantity": holding["quantity"],
                "institution_price": holding["institution_price"],
                "institution_value": holding["institution_value"],
                "cost_basis": holding["cost_basis"],
                "iso_currency_code": holding["iso_currency_code"],
                "unofficial_currency_code": holding["unofficial_currency_code"],
            }
            for holding in holdings
        ]
        statement = insert(InvestmentHoldingSnapshot).values(snapshots)
        statement = statement.on_conflict_do_update(
            constraint="uq_investment_holding_snapshots_account_security_date",
            set_={
                "quantity": statement.excluded.quantity,
                "institution_price": statement.excluded.institution_price,
                "institution_value": statement.excluded.institution_value,
                "cost_basis": statement.excluded.cost_basis,
                "iso_currency_code": statement.excluded.iso_currency_code,
                "unofficial_currency_code": statement.excluded.unofficial_currency_code,
                "updated_at": func.clock_timestamp(),
            },
        )
        await self.session.execute(statement)
        await self.session.flush()
        return len(snapshots)

    async def upsert_transactions(
        self, transactions: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Insert or update investment transactions and return added/updated counts."""
        if not transactions:
            return 0, 0

        transaction_ids = [
            transaction["investment_transaction_id"] for transaction in transactions
        ]
        result = await self.session.execute(
            select(InvestmentTransaction.investment_transaction_id).where(
                InvestmentTransaction.investment_transaction_id.in_(transaction_ids)
            )
        )
        existing_ids = set(result.scalars().all())

        statement = insert(InvestmentTransaction).values(transactions)
        statement = statement.on_conflict_do_update(
            index_elements=["investment_transaction_id"],
            set_={
                "account_id": statement.excluded.account_id,
                "security_id": statement.excluded.security_id,
                "cancel_transaction_id": statement.excluded.cancel_transaction_id,
                "date": statement.excluded.date,
                "name": statement.excluded.name,
                "amount": statement.excluded.amount,
                "fees": statement.excluded.fees,
                "price": statement.excluded.price,
                "quantity": statement.excluded.quantity,
                "transaction_type": statement.excluded.transaction_type,
                "subtype": statement.excluded.subtype,
                "iso_currency_code": statement.excluded.iso_currency_code,
                "unofficial_currency_code": statement.excluded.unofficial_currency_code,
                "raw": statement.excluded.raw,
                "updated_at": func.clock_timestamp(),
            },
        )
        await self.session.execute(statement)
        await self.session.flush()

        updated = sum(
            transaction_id in existing_ids for transaction_id in transaction_ids
        )
        return len(transactions) - updated, updated
