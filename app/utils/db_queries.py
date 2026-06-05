"""Safe async query helpers — avoid MissingGreenlet and MultipleResultsFound."""

from typing import Any, TypeVar

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


async def fetch_first(session: AsyncSession, stmt: Select[tuple[T]]) -> T | None:
    """
    Return the first matching ORM row or None.

    Use with order_by when the filter may match multiple rows (e.g. 'latest active MOU').
    Applies limit(1) + unique() so MultipleResultsFound cannot occur.
    """
    result = await session.execute(stmt.limit(1))
    return result.unique().scalars().first()


async def fetch_scalar_first(session: AsyncSession, stmt: Select) -> Any | None:
    """Return the first scalar value or None (safe for non-unique filters)."""
    return (await session.execute(stmt.limit(1))).scalar_one_or_none()


async def fetch_one(session: AsyncSession, stmt: Select[tuple[T]]) -> T | None:
    """Return exactly one ORM row or None. Adds limit(1) as a safety net."""
    return (await session.execute(stmt.limit(1))).unique().scalar_one_or_none()


async def row_exists(session: AsyncSession, stmt: Select) -> bool:
    """True when at least one row matches. Never raises MultipleResultsFound."""
    return (await session.execute(stmt.limit(1))).first() is not None
