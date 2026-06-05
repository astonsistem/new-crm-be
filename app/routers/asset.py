from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.dependencies import get_db
from app.models import User, Category
from app.models.asset import Asset
from app.models.serial_number import Serial_Number
from app.schemas.asset import AssetCreate, AssetUpdate, AssetResponse
from app.utils.permissions import require_permission, Permission
from pydantic import BaseModel


class AssetListResponse(BaseModel):
    data: List[AssetResponse]
    total: int


router = APIRouter(prefix="/assets", tags=["Assets"])


def _asset_opts():
    return [selectinload(Asset.category)]


@router.get("/", response_model=AssetListResponse)
async def get_assets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    category_id: Optional[UUID] = None,
    name: Optional[str] = Query(None, description="Filter by asset name (partial, case-insensitive)"),
    include_deleted: bool = False,
    current_user: User = Depends(require_permission(Permission.READ_ASSET)),
    db: AsyncSession = Depends(get_db)
):
    sn_subq = (
        select(Serial_Number.asset_id, func.count(Serial_Number.id).label("serial_number_count"))
        .group_by(Serial_Number.asset_id)
    ).subquery()

    stmt = (
        select(Asset, sn_subq.c.serial_number_count)
        .outerjoin(sn_subq, Asset.id == sn_subq.c.asset_id)
        .options(*_asset_opts())
    )

    if not include_deleted:
        stmt = stmt.where(Asset.deleted_at.is_(None))

    if category_id:
        stmt = stmt.where(Asset.category_id == category_id)

    if name:
        stmt = stmt.where(Asset.asset_name.ilike(f"%{name}%"))

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar()

    stmt = stmt.offset(skip).limit(limit)
    rows = (await db.execute(stmt)).all()

    assets_out = []
    for row in rows:
        asset = row[0]
        sn_count_val = row[1]
        assets_out.append(AssetResponse(
            id=asset.id,
            asset_name=asset.asset_name,
            asset_type=asset.asset_type,
            category_id=asset.category_id,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
            deleted_at=asset.deleted_at,
            category_name=asset.category.name if asset.category else None,
            serial_number_count=sn_count_val or 0,
        ))

    return AssetListResponse(data=assets_out, total=total)


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset_by_id(
    asset_id: UUID,
    current_user: User = Depends(require_permission(Permission.READ_ASSET)),
    db: AsyncSession = Depends(get_db)
):
    asset = (await db.execute(
        select(Asset).options(*_asset_opts()).where(Asset.id == asset_id)
    )).scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with id {asset_id} not found"
        )

    sn_count = (await db.execute(
        select(func.count(Serial_Number.id)).where(Serial_Number.asset_id == asset_id)
    )).scalar()

    return AssetResponse(
        id=asset.id,
        asset_name=asset.asset_name,
        asset_type=asset.asset_type,
        category_id=asset.category_id,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        deleted_at=asset.deleted_at,
        category_name=asset.category.name if asset.category else None,
        serial_number_count=sn_count or 0,
    )


@router.post("/", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    asset: AssetCreate,
    current_user: User = Depends(require_permission(Permission.CREATE_ASSET)),
    db: AsyncSession = Depends(get_db)
):
    category = (await db.execute(
        select(Category).where(Category.id == asset.category_id)
    )).scalar_one_or_none()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with id {asset.category_id} not found"
        )

    db_asset = Asset(**asset.model_dump())
    db.add(db_asset)
    await db.commit()
    await db.refresh(db_asset)

    sn_count = (await db.execute(
        select(func.count(Serial_Number.id)).where(Serial_Number.asset_id == db_asset.id)
    )).scalar()

    return AssetResponse(
        id=db_asset.id,
        asset_name=db_asset.asset_name,
        asset_type=db_asset.asset_type,
        category_id=db_asset.category_id,
        created_at=db_asset.created_at,
        updated_at=db_asset.updated_at,
        deleted_at=db_asset.deleted_at,
        category_name=category.name,  # use already-fetched category, no lazy load
        serial_number_count=sn_count or 0,
    )


@router.put("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: UUID,
    asset: AssetUpdate,
    current_user: User = Depends(require_permission(Permission.UPDATE_ASSET)),
    db: AsyncSession = Depends(get_db)
):
    db_asset = (await db.execute(
        select(Asset).where(Asset.id == asset_id)
    )).scalar_one_or_none()

    if not db_asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with id {asset_id} not found"
        )

    new_category = None
    if asset.category_id:
        new_category = (await db.execute(
            select(Category).where(Category.id == asset.category_id)
        )).scalar_one_or_none()
        if not new_category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with id {asset.category_id} not found"
            )

    update_data = asset.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_asset, key, value)

    db_asset.updated_at = datetime.utcnow()
    await db.commit()

    # Re-query with eager loading to get fresh category name
    db_asset = (await db.execute(
        select(Asset).options(*_asset_opts()).where(Asset.id == asset_id)
    )).scalar_one()

    sn_count = (await db.execute(
        select(func.count(Serial_Number.id)).where(Serial_Number.asset_id == asset_id)
    )).scalar()

    return AssetResponse(
        id=db_asset.id,
        asset_name=db_asset.asset_name,
        asset_type=db_asset.asset_type,
        category_id=db_asset.category_id,
        created_at=db_asset.created_at,
        updated_at=db_asset.updated_at,
        deleted_at=db_asset.deleted_at,
        category_name=db_asset.category.name if db_asset.category else None,
        serial_number_count=sn_count or 0,
    )


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    current_user: User = Depends(require_permission(Permission.DELETE_ASSET)),
    db: AsyncSession = Depends(get_db)
):
    db_asset = (await db.execute(
        select(Asset).where(Asset.id == asset_id)
    )).scalar_one_or_none()

    if not db_asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with id {asset_id} not found"
        )

    if db_asset.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asset is already deleted"
        )

    db_asset.deleted_at = datetime.utcnow()
    await db.commit()

    return None


@router.post("/{asset_id}/restore", response_model=AssetResponse)
async def restore_asset(
    asset_id: UUID,
    current_user: User = Depends(require_permission(Permission.UPDATE_ASSET)),
    db: AsyncSession = Depends(get_db)
):
    db_asset = (await db.execute(
        select(Asset).where(Asset.id == asset_id)
    )).scalar_one_or_none()

    if not db_asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with id {asset_id} not found"
        )

    if not db_asset.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asset is not deleted"
        )

    db_asset.deleted_at = None
    db_asset.updated_at = datetime.utcnow()
    await db.commit()

    # Re-query with eager loading
    db_asset = (await db.execute(
        select(Asset).options(*_asset_opts()).where(Asset.id == asset_id)
    )).scalar_one()

    sn_count = (await db.execute(
        select(func.count(Serial_Number.id)).where(Serial_Number.asset_id == asset_id)
    )).scalar()

    return AssetResponse(
        id=db_asset.id,
        asset_name=db_asset.asset_name,
        asset_type=db_asset.asset_type,
        category_id=db_asset.category_id,
        created_at=db_asset.created_at,
        updated_at=db_asset.updated_at,
        deleted_at=db_asset.deleted_at,
        category_name=db_asset.category.name if db_asset.category else None,
        serial_number_count=sn_count or 0,
    )
