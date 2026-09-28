"""Repository for CreditLiability operations."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from budget_me.db.models.credit_liability import CreditLiability, CreditLiabilityApr
from budget_me.db.repos.base import BaseRepository


class LiabilitiesRepo(BaseRepository[CreditLiability]):
    """Repository for CreditLiability CRUD and liability management operations."""

    model = CreditLiability

    async def find_by_item_id(self, plaid_item_id: uuid.UUID) -> list[CreditLiability]:
        """Find all credit liabilities for a PlaidItem.

        Args:
            plaid_item_id: The PlaidItem UUID.

        Returns:
            List of CreditLiabilities belonging to the PlaidItem.
        """
        stmt = select(CreditLiability).where(
            CreditLiability.plaid_item_id == plaid_item_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_account_id(self, account_id: str) -> CreditLiability | None:
        """Find a credit liability by Plaid's account_id.

        Args:
            account_id: The Plaid-assigned account identifier.

        Returns:
            The CreditLiability if found, None otherwise.
        """
        stmt = select(CreditLiability).where(CreditLiability.account_id == account_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_liability(
        self, plaid_item_id: uuid.UUID, account_id: str, data: dict
    ) -> CreditLiability:
        """Create or update a credit liability.

        Args:
            plaid_item_id: The PlaidItem UUID.
            account_id: The Plaid-assigned account identifier.
            data: Dictionary with liability fields.

        Returns:
            The created or updated CreditLiability.
        """
        existing = await self.find_by_account_id(account_id)

        if existing:
            # Update existing liability
            existing.is_overdue = data.get("is_overdue")
            existing.last_payment_amount = data.get("last_payment_amount")
            existing.last_payment_date = data.get("last_payment_date")
            existing.last_statement_balance = data.get("last_statement_balance")
            existing.last_statement_issue_date = data.get("last_statement_issue_date")
            existing.minimum_payment_amount = data.get("minimum_payment_amount")
            existing.next_payment_due_date = data.get("next_payment_due_date")
            await self.session.flush()
            return existing
        else:
            # Create new liability
            return await self.create(
                plaid_item_id=plaid_item_id, account_id=account_id, **data
            )

    async def upsert_aprs(self, liability_id: uuid.UUID, aprs_data: list[dict]) -> None:
        """Replace all Plaid-sourced APRs for a credit liability.

        Deletes existing APRs where source='plaid' and creates new ones.
        Preserves manual APR entries (source='manual').

        Args:
            liability_id: The CreditLiability UUID.
            aprs_data: List of APR data dictionaries with keys:
                apr_type, apr_percentage, balance_subject_to_apr, interest_charge_amount
        """
        # Delete existing Plaid APRs only (preserve manual entries)
        stmt = delete(CreditLiabilityApr).where(
            CreditLiabilityApr.credit_liability_id == liability_id,
            CreditLiabilityApr.source == "plaid",
        )
        await self.session.execute(stmt)

        # Create new Plaid APRs
        for apr_data in aprs_data:
            apr = CreditLiabilityApr(
                credit_liability_id=liability_id, source="plaid", **apr_data
            )
            self.session.add(apr)

        await self.session.flush()

    async def upsert_manual_apr(
        self,
        liability_id: uuid.UUID,
        apr_type: str,
        apr_percentage: Decimal,
        balance: Decimal,
        promo_end_date: date | None = None,
        offer_id: str | None = None,
    ) -> CreditLiabilityApr:
        """Create or update a manual APR entry.

        Matches existing APRs by (liability_id, apr_type, offer_id).
        If offer_id is provided, uses it for matching. Otherwise matches by apr_type only.

        Args:
            liability_id: The CreditLiability UUID.
            apr_type: Type of APR (e.g., "promotional", "purchase_apr").
            apr_percentage: APR percentage.
            balance: Balance subject to this APR.
            promo_end_date: When promotional rate expires (optional).
            offer_id: Promotional offer ID from statement (optional).

        Returns:
            The created or updated CreditLiabilityApr.
        """
        # Find existing manual APR matching by liability_id, apr_type, and offer_id
        query = select(CreditLiabilityApr).where(
            CreditLiabilityApr.credit_liability_id == liability_id,
            CreditLiabilityApr.apr_type == apr_type,
            CreditLiabilityApr.source == "manual",
        )

        if offer_id:
            query = query.where(CreditLiabilityApr.promo_offer_id == offer_id)

        result = await self.session.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing APR
            existing.apr_percentage = apr_percentage
            existing.balance_subject_to_apr = balance
            existing.promo_rate_end_date = promo_end_date
            await self.session.flush()
            return existing
        else:
            # Create new manual APR
            apr = CreditLiabilityApr(
                credit_liability_id=liability_id,
                apr_type=apr_type,
                apr_percentage=apr_percentage,
                balance_subject_to_apr=balance,
                promo_rate_end_date=promo_end_date,
                promo_offer_id=offer_id,
                source="manual",
            )
            self.session.add(apr)
            await self.session.flush()
            return apr

    async def get_all_with_details(self) -> list[CreditLiability]:
        """Get all credit liabilities with account and APR relationships eagerly loaded.

        Returns:
            List of CreditLiabilities with account and aprs relationships loaded.
        """
        stmt = (
            select(CreditLiability)
            .options(joinedload(CreditLiability.account))
            .options(joinedload(CreditLiability.aprs))
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())
