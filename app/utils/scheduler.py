import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from datetime import datetime
from app.database import AsyncSessionLocal
from app.models.mou import MOU
from app.models.status import Status_MOU
from app.utils.db_queries import fetch_first, fetch_scalar_first
from app.core.logging import get_logger

logger = get_logger("app.scheduler")

# AsyncIOScheduler runs jobs directly on the running asyncio event loop —
# no background threads, no asyncio.run(), no risk of closing the proactor.
_scheduler = AsyncIOScheduler()


async def _expire_mous() -> None:
    """Log ACTIVE MOUs past end_date. Renewal/close is handled via API endpoints."""
    try:
        async with AsyncSessionLocal() as db:
            try:
                active_status_id = await fetch_scalar_first(
                    db, select(Status_MOU.id).where(Status_MOU.name == "ACTIVE")
                )
                if not active_status_id:
                    logger.warning(
                        "ACTIVE status not found in status_mou table — skipping MOU expiry check."
                    )
                    return

                expired_mous = (await db.execute(
                    select(MOU).where(
                        MOU.status_mou_id == active_status_id,
                        MOU.end_date < datetime.now(),
                        MOU.deleted_at.is_(None),
                    )
                )).scalars().all()

                if expired_mous:
                    mou_numbers = [m.no_mou for m in expired_mous]
                    logger.info(
                        "%d MOU(s) past end_date awaiting renewal decision: %s",
                        len(expired_mous),
                        mou_numbers,
                    )
                else:
                    logger.debug("No expired MOUs found.")

            except Exception:
                logger.exception("Error while running MOU expiry check.")
    except asyncio.CancelledError:
        logger.debug("MOU expiry job cancelled during server shutdown.")


async def run_mou_expiry_check() -> None:
    """Run MOU expiry once during startup (before the server accepts requests)."""
    await _expire_mous()


def start_scheduler() -> None:
    """Start the async scheduler. Must be called inside a running asyncio event loop."""
    if _scheduler.running:
        return
    _scheduler.add_job(_expire_mous, "cron", hour=0, minute=0, id="expire_mous_daily")
    _scheduler.start()
    logger.info("MOU expiry scheduler started — logs expired MOUs daily at midnight.")


def stop_scheduler() -> None:
    """Stop the scheduler on application shutdown."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("MOU expiry scheduler stopped.")
