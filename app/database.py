from datetime import datetime

from sqlalchemy import DateTime, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import get_settings
from app.utils.datetime_utils import to_naive_datetime

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,          # SQL query logging is handled via app/core/logging.py
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


@event.listens_for(Session, "before_flush")
def _normalize_naive_datetimes(session, flush_context, instances):
    """Strip timezone from DateTime columns before asyncpg encode."""
    for obj in list(session.new) + list(session.dirty):
        mapper = getattr(obj.__class__, "__mapper__", None)
        if mapper is None:
            continue
        for attr in mapper.column_attrs:
            col = attr.columns[0]
            if not isinstance(col.type, DateTime) or getattr(col.type, "timezone", False):
                continue
            val = getattr(obj, attr.key, None)
            if isinstance(val, datetime) and val.tzinfo is not None:
                setattr(obj, attr.key, to_naive_datetime(val))


async def get_db():
    """FastAPI dependency — yields an AsyncSession per request.
    Automatically rolls back any uncommitted changes when an exception propagates.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
