"""Repository for persistent transaction categorization rules."""

from collections.abc import Mapping

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.db.models.categorization_rule import CategorizationRule
from budget_me.db.repos.base import BaseRepository


class CategorizationRulesRepo(BaseRepository[CategorizationRule]):
    """Read and upsert private categorization-rule overrides."""

    model = CategorizationRule

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def _execute_upsert(self, stmt: Insert) -> int:
        """Execute an upsert and report rows actually inserted or updated."""
        result = await self.session.execute(stmt.returning(CategorizationRule.id))
        await self.session.flush()
        return len(result.scalars().all())

    async def get_all_overrides(self) -> list[CategorizationRule]:
        """Return all overrides, including disabled packaged-rule masks."""
        result = await self.session.execute(
            select(CategorizationRule).order_by(
                CategorizationRule.rule_type, CategorizationRule.pattern
            )
        )
        return list(result.scalars().all())

    async def upsert_category_rules(
        self,
        rules: Mapping[str, str],
        *,
        source: str,
        confidence: str | None = None,
        replace: bool = True,
    ) -> int:
        """Insert category rules, optionally replacing matching DB overrides."""
        rows = [
            {
                "rule_type": "category",
                "pattern": pattern.strip(),
                "category": category,
                "enabled": True,
                "source": source,
                "confidence": confidence,
            }
            for pattern, category in rules.items()
        ]
        if not rows:
            return 0

        stmt = insert(CategorizationRule).values(rows)
        if replace:
            stmt = stmt.on_conflict_do_update(
                constraint="uq_categorization_rules_type_pattern",
                set_={
                    "pattern": stmt.excluded.pattern,
                    "category": stmt.excluded.category,
                    "reimbursement_note": None,
                    "enabled": True,
                    "source": stmt.excluded.source,
                    "confidence": stmt.excluded.confidence,
                    "updated_at": func.now(),
                },
            )
        else:
            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_categorization_rules_type_pattern"
            )
        return await self._execute_upsert(stmt)

    async def upsert_reimbursement_rules(
        self,
        rules: Mapping[str, str],
        *,
        source: str,
        replace: bool = True,
    ) -> int:
        """Insert reimbursement rules, optionally replacing DB overrides."""
        rows = [
            {
                "rule_type": "reimbursable",
                "pattern": pattern.strip(),
                "reimbursement_note": note,
                "enabled": True,
                "source": source,
            }
            for pattern, note in rules.items()
        ]
        if not rows:
            return 0

        stmt = insert(CategorizationRule).values(rows)
        if replace:
            stmt = stmt.on_conflict_do_update(
                constraint="uq_categorization_rules_type_pattern",
                set_={
                    "pattern": stmt.excluded.pattern,
                    "category": None,
                    "reimbursement_note": stmt.excluded.reimbursement_note,
                    "enabled": True,
                    "source": stmt.excluded.source,
                    "confidence": None,
                    "updated_at": func.now(),
                },
            )
        else:
            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_categorization_rules_type_pattern"
            )
        return await self._execute_upsert(stmt)

    async def upsert_disabled_rules(
        self,
        rule_type: str,
        patterns: list[str],
        *,
        source: str,
    ) -> int:
        """Mask packaged or database rules without deleting their history."""
        if rule_type not in {"category", "reimbursable"}:
            raise ValueError(f"Unsupported categorization rule type: {rule_type}")

        rows = [
            {
                "rule_type": rule_type,
                "pattern": pattern.strip(),
                "category": None,
                "reimbursement_note": None,
                "enabled": False,
                "source": source,
                "confidence": None,
            }
            for pattern in patterns
        ]
        if not rows:
            return 0

        stmt = insert(CategorizationRule).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_categorization_rules_type_pattern",
            set_={
                "pattern": stmt.excluded.pattern,
                "category": None,
                "reimbursement_note": None,
                "enabled": False,
                "source": stmt.excluded.source,
                "confidence": None,
                "updated_at": func.now(),
            },
        )
        return await self._execute_upsert(stmt)
