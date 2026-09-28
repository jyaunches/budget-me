"""Tests for funding sources repository."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from budget_me.db.models.funding_source import FundingSource, FundingSourceType
from budget_me.db.repos.funding_sources_repo import FundingSourcesRepository


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    return session


@pytest.fixture
def repo(mock_session):
    """Create a funding sources repository."""
    return FundingSourcesRepository(mock_session)


@pytest.mark.asyncio
async def test_get_all_returns_sources(repo, mock_session):
    """Test get_all returns all funding sources."""
    mock_sources = [
        FundingSource(
            name="Example Investment",
            source_type="investment",
            available_amount=Decimal("12345.67"),
            active=True,
        ),
        FundingSource(
            name="Savings",
            source_type="savings",
            available_amount=Decimal("10000.00"),
            active=False,
        ),
    ]

    # Mock the execute result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_sources
    mock_session.execute.return_value = mock_result

    sources = await repo.get_all()

    assert len(sources) == 2
    assert sources[0].name == "Example Investment"
    assert sources[1].name == "Savings"


@pytest.mark.asyncio
async def test_get_active_returns_only_active(repo, mock_session):
    """Test get_active returns only active funding sources."""
    mock_sources = [
        FundingSource(
            name="Example Investment",
            source_type="investment",
            available_amount=Decimal("12345.67"),
            active=True,
        ),
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_sources
    mock_session.execute.return_value = mock_result

    sources = await repo.get_active()

    assert len(sources) == 1
    assert sources[0].active is True


@pytest.mark.asyncio
async def test_create_adds_source(repo, mock_session):
    """Test create adds a new funding source."""
    await repo.create(
        name="Emergency Fund",
        source_type=FundingSourceType.SAVINGS.value,
        available_amount=Decimal("15000.00"),
        notes="High yield savings",
    )

    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_modifies_source(repo, mock_session):
    """Test update modifies an existing source."""
    from uuid import uuid4

    source_id = uuid4()

    mock_source = FundingSource(
        name="Old Name",
        source_type="investment",
        available_amount=Decimal("10000.00"),
    )
    mock_source.id = source_id

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_source
    mock_session.execute.return_value = mock_result

    updated = await repo.update(
        source_id=source_id,
        available_amount=Decimal("12000.00"),
    )

    assert updated.available_amount == Decimal("12000.00")
    mock_session.commit.assert_awaited_once()
