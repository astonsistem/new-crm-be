"""Normalize datetimes for TIMESTAMP WITHOUT TIME ZONE columns (asyncpg)."""

from datetime import datetime
from typing import Annotated, Any, Optional

from pydantic import BeforeValidator


def to_naive_datetime(value: Any) -> datetime | None:
    """Convert tz-aware datetimes to naive local time for DB storage."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


NaiveDatetime = Annotated[datetime, BeforeValidator(to_naive_datetime)]
OptionalNaiveDatetime = Annotated[Optional[datetime], BeforeValidator(to_naive_datetime)]
