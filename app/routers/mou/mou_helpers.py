"""MOU expiry, renewal, and close helpers."""

import os
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mou import MOU, MOU_Device, MOU_Product
from app.models.status import Status_MOU
from app.utils.db_queries import fetch_scalar_first
from app.utils.eager_loads import mou_load_options


async def get_status_mou_id(db: AsyncSession, name: str) -> UUID:
    status_id = await fetch_scalar_first(
        db, select(Status_MOU.id).where(Status_MOU.name == name)
    )
    if not status_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MOU status '{name}' is not configured",
        )
    return status_id


async def fetch_active_mou(db: AsyncSession, mou_id: UUID) -> MOU:
    mou = (await db.execute(
        select(MOU).options(*mou_load_options()).where(
            MOU.id == mou_id,
            MOU.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU not found",
        )
    return mou


def ensure_mou_expired(mou: MOU) -> None:
    if mou.end_date >= datetime.now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MOU has not passed its end date yet",
        )


def ensure_mou_status_active(mou: MOU) -> None:
    status_name = mou.status_mou.name if mou.status_mou else None
    if status_name != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only ACTIVE MOUs can be renewed or closed",
        )


def _copy_contract_file(source_path: str | None, new_mou_id: UUID) -> str | None:
    if not source_path or not os.path.exists(source_path):
        return None

    upload_dir = Path("uploads/mou_contracts")
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_ext = Path(source_path).suffix
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    destination = upload_dir / f"{new_mou_id}_{timestamp}{file_ext}"
    shutil.copy2(source_path, destination)
    return str(destination)


async def copy_mou_products(db: AsyncSession, old_mou_id: UUID, new_mou_id: UUID) -> None:
    products = (await db.execute(
        select(MOU_Product).where(
            MOU_Product.mou_id == old_mou_id,
            MOU_Product.deleted_at.is_(None),
        )
    )).scalars().all()

    for product in products:
        db.add(MOU_Product(
            mou_id=new_mou_id,
            product_id=product.product_id,
            contract_price=product.contract_price,
            active=product.active,
        ))


async def copy_mou_devices(db: AsyncSession, old_mou_id: UUID, new_mou_id: UUID) -> None:
    devices = (await db.execute(
        select(MOU_Device).where(MOU_Device.mou_id == old_mou_id)
    )).scalars().all()

    for device in devices:
        db.add(MOU_Device(
            mou_id=new_mou_id,
            serial_number_id=device.serial_number_id,
            location=device.location,
            status=device.status,
        ))


async def close_expired_mou(db: AsyncSession, mou: MOU) -> MOU:
    ensure_mou_status_active(mou)
    ensure_mou_expired(mou)
    inactive_status_id = await get_status_mou_id(db, "INACTIVE")
    mou.status_mou_id = inactive_status_id
    await db.commit()
    return await fetch_active_mou(db, mou.id)


async def renew_expired_mou(
    db: AsyncSession,
    mou: MOU,
    *,
    start_date: datetime,
    end_date: datetime,
    created_by: UUID,
    generate_mou_number,
) -> tuple[MOU, MOU]:
    ensure_mou_status_active(mou)
    ensure_mou_expired(mou)

    if end_date <= start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be after start date",
        )

    active_status_id = await get_status_mou_id(db, "ACTIVE")
    inactive_status_id = await get_status_mou_id(db, "INACTIVE")

    old_mou_id = mou.id
    new_no_mou = await generate_mou_number(db)

    new_mou = MOU(
        no_mou=new_no_mou,
        customer_id=mou.customer_id,
        status_mou_id=active_status_id,
        start_date=start_date,
        end_date=end_date,
        description=mou.description,
        contract_file=None,
        created_by=created_by,
    )
    db.add(new_mou)
    await db.flush()

    new_mou.contract_file = _copy_contract_file(mou.contract_file, new_mou.id)

    await copy_mou_products(db, old_mou_id, new_mou.id)
    await copy_mou_devices(db, old_mou_id, new_mou.id)

    mou.status_mou_id = inactive_status_id

    await db.commit()

    old_mou = await fetch_active_mou(db, old_mou_id)
    renewed_mou = await fetch_active_mou(db, new_mou.id)
    return old_mou, renewed_mou
