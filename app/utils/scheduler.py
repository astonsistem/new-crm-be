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
    """Mark ACTIVE MOUs past their end_date as INACTIVE (runs in the main event loop)."""
    async with AsyncSessionLocal() as db:
        try:
            inactive_status_id = await fetch_scalar_first(
                db, select(Status_MOU.id).where(Status_MOU.name == "INACTIVE")
            )
            if not inactive_status_id:
                logger.warning(
                    "INACTIVE status not found in status_mou table — skipping MOU expiry job."
                )
                return

            active_status_id = await fetch_scalar_first(
                db, select(Status_MOU.id).where(Status_MOU.name == "ACTIVE")
            )
            if not active_status_id:
                logger.warning(
                    "ACTIVE status not found in status_mou table — skipping MOU expiry job."
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
                for mou in expired_mous:
                    mou.status_mou_id = inactive_status_id
                await db.commit()
                logger.info("Expired %d MOU(s): %s", len(expired_mous), mou_numbers)
            else:
                logger.debug("No expired MOUs found.")

        except Exception:
            await db.rollback()
            logger.exception("Error while running MOU expiry job.")


def start_scheduler() -> None:
    """Start the async scheduler. Must be called inside a running asyncio event loop."""
    _scheduler.add_job(_expire_mous, "cron", hour=0, minute=0, id="expire_mous_daily")
    _scheduler.add_job(_expire_mous, "date", id="expire_mous_startup")
    _scheduler.start()
    logger.info("MOU expiry scheduler started — runs daily at midnight.")


def stop_scheduler() -> None:
    """Stop the scheduler on application shutdown."""
    _scheduler.shutdown(wait=False)
    logger.info("MOU expiry scheduler stopped.")
