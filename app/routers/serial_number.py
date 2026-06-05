from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from typing import List, Optional
from uuid import UUID
from app.dependencies import get_db
from app.models import User
from app.models.serial_number import Serial_Number
from app.models.asset import Asset
from app.schemas.serial_number import (
    SerialNumberCreate, 
    SerialNumberUpdate, 
    SerialNumberResponse,
    SerialNumberStatus
)
from app.utils.permissions import require_permission, Permission

router = APIRouter(prefix="/serial-numbers", tags=["Serial Numbers"])


@router.get("/", response_model=List[SerialNumberResponse])
async def get_serial_numbers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    asset_id: Optional[UUID] = None,
    serial_code: Optional[str] = Query(None, description="Filter by serial code (partial, case-insensitive)"),
    status: Optional[SerialNumberStatus] = None,
    current_user: User = Depends(require_permission(Permission.READ_SERIAL_NUMBER)),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all serial numbers with pagination and optional filters
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **asset_id**: Filter by asset ID (optional)
    - **serial_code**: Filter by serial code, partial match (optional)
    - **status**: Filter by status (ACTIVE, INACTIVE, SERVICE) (optional)
    """
    stmt = select(Serial_Number).options(joinedload(Serial_Number.asset))

    if asset_id:
        stmt = stmt.where(Serial_Number.asset_id == asset_id)

    if serial_code:
        stmt = stmt.where(Serial_Number.serial_code.ilike(f"%{serial_code}%"))

    if status:
        stmt = stmt.where(Serial_Number.status == status.value)

    stmt = stmt.offset(skip).limit(limit)
    serial_numbers = (await db.execute(stmt)).scalars().all()

    return serial_numbers


@router.get("/{serial_number_id}", response_model=SerialNumberResponse)
async def get_serial_number_by_id(
    serial_number_id: UUID,
    current_user: User = Depends(require_permission(Permission.READ_SERIAL_NUMBER)),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a serial number by ID
    
    - **serial_number_id**: Serial Number ID (required)
    """
    serial_number = (await db.execute(
        select(Serial_Number).options(joinedload(Serial_Number.asset)).where(Serial_Number.id == serial_number_id)
    )).scalar_one_or_none()

    if not serial_number:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Serial number with id {serial_number_id} not found"
        )

    return serial_number


@router.post("/", response_model=SerialNumberResponse, status_code=status.HTTP_201_CREATED)
async def create_serial_number(
    serial_number: SerialNumberCreate,
    current_user: User = Depends(require_permission(Permission.CREATE_SERIAL_NUMBER)),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new serial number
    
    - **serial_code**: Unique serial code (required)
    - **asset_id**: Asset ID (required)
    """
    asset = (await db.execute(
        select(Asset).where(
            Asset.id == serial_number.asset_id,
            Asset.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset with id {serial_number.asset_id} not found"
        )

    existing_serial = (await db.execute(
        select(Serial_Number).where(Serial_Number.serial_code == serial_number.serial_code)
    )).scalar_one_or_none()

    if existing_serial:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Serial number with code {serial_number.serial_code} already exists"
        )

    db_serial_number = Serial_Number(**serial_number.model_dump(), status="INACTIVE")
    db.add(db_serial_number)
    await db.commit()
    await db.refresh(db_serial_number)

    serial_with_asset = (await db.execute(
        select(Serial_Number).options(joinedload(Serial_Number.asset)).where(Serial_Number.id == db_serial_number.id)
    )).scalar_one_or_none()

    return serial_with_asset


@router.put("/{serial_number_id}", response_model=SerialNumberResponse)
async def update_serial_number(
    serial_number_id: UUID,
    serial_number: SerialNumberUpdate,
    current_user: User = Depends(require_permission(Permission.UPDATE_SERIAL_NUMBER)),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a serial number
    
    - **serial_number_id**: Serial Number ID (required)
    - Can update serial_code, asset_id, or status
    """
    db_serial_number = (await db.execute(
        select(Serial_Number).where(Serial_Number.id == serial_number_id)
    )).scalar_one_or_none()

    if not db_serial_number:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Serial number with id {serial_number_id} not found"
        )

    if serial_number.asset_id:
        asset = (await db.execute(
            select(Asset).where(
                Asset.id == serial_number.asset_id,
                Asset.deleted_at.is_(None)
            )
        )).scalar_one_or_none()

        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset with id {serial_number.asset_id} not found"
            )

    if serial_number.serial_code and serial_number.serial_code != db_serial_number.serial_code:
        existing_serial = (await db.execute(
            select(Serial_Number).where(Serial_Number.serial_code == serial_number.serial_code)
        )).scalar_one_or_none()

        if existing_serial:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Serial number with code {serial_number.serial_code} already exists"
            )

    update_data = serial_number.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_serial_number, key, value)

    await db.commit()
    await db.refresh(db_serial_number)

    serial_with_asset = (await db.execute(
        select(Serial_Number).options(joinedload(Serial_Number.asset)).where(Serial_Number.id == db_serial_number.id)
    )).scalar_one_or_none()

    return serial_with_asset


@router.delete("/{serial_number_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_serial_number(
    serial_number_id: UUID,
    current_user: User = Depends(require_permission(Permission.DELETE_SERIAL_NUMBER)),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a serial number permanently
    
    - **serial_number_id**: Serial Number ID (required)
    - ⚠️ This action cannot be undone
    """
    db_serial_number = (await db.execute(
        select(Serial_Number).where(Serial_Number.id == serial_number_id)
    )).scalar_one_or_none()

    if not db_serial_number:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Serial number with id {serial_number_id} not found"
        )

    await db.delete(db_serial_number)
    await db.commit()

    return None
