from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List
from uuid import UUID
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.mou import MOU
from app.models.status import Status_MOU, Status_Service
from app.models.order import Order_Service
from app.schemas.status import (
    StatusMOUCreate, StatusMOUUpdate, StatusMOUResponse,
    StatusServiceCreate, StatusServiceUpdate, StatusServiceResponse
)

router = APIRouter(prefix="/status-mou", tags=["STATUS MOU"])



# List all MOU statuses
@router.get("/", response_model=List[StatusMOUResponse])
async def get_mou_statuses(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: str = Query(None, description="Search MOU statuses by code or name (partial, case-insensitive)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all MOU statuses
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    """
    stmt = select(Status_MOU)

    if search:
        stmt = stmt.where(
            (Status_MOU.code.ilike(f"%{search}%")) | (Status_MOU.name.ilike(f"%{search}%"))
        )

    statuses = (await db.execute(stmt.offset(skip).limit(limit))).scalars().all()
    return statuses


# Get status by ID
@router.get("/{status_id}", response_model=StatusMOUResponse)
async def get_mou_status(
    status_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific MOU status by ID
    """
    status_mou = (await db.execute(select(Status_MOU).where(Status_MOU.id == status_id))).scalar_one_or_none()

    if not status_mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status not found"
        )

    return status_mou


# Create new MOU status
@router.post("/", response_model=StatusMOUResponse, status_code=status.HTTP_201_CREATED)
async def create_mou_status(
    status_data: StatusMOUCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new MOU status
    
    - **code**: Unique status code (required)
    - **name**: Status name (optional)
    """
    existing_status = (await db.execute(select(Status_MOU).where(Status_MOU.code == status_data.code))).scalar_one_or_none()
    if existing_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status code already exists"
        )

    new_status = Status_MOU(
        code=status_data.code,
        name=status_data.name
    )

    db.add(new_status)
    await db.commit()
    await db.refresh(new_status)

    return new_status


# Update MOU status
@router.put("/{status_id}", response_model=StatusMOUResponse)
async def update_mou_status(
    status_id: UUID,
    status_data: StatusMOUUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing MOU status
    
    - All fields are optional
    - Only provided fields will be updated
    """
    status_mou = (await db.execute(select(Status_MOU).where(Status_MOU.id == status_id))).scalar_one_or_none()

    if not status_mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status not found"
        )

    update_data = status_data.model_dump(exclude_unset=True)

    if "code" in update_data and update_data["code"] != status_mou.code:
        existing_status = (await db.execute(select(Status_MOU).where(Status_MOU.code == update_data["code"]))).scalar_one_or_none()
        if existing_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status code already exists"
            )

    for field, value in update_data.items():
        setattr(status_mou, field, value)

    await db.commit()
    await db.refresh(status_mou)

    return status_mou


# Delete MOU status
@router.delete("/{status_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mou_status(
    status_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete an MOU status permanently
    
    - ⚠️ This action cannot be undone
    """
    status_mou = (await db.execute(select(Status_MOU).where(Status_MOU.id == status_id))).scalar_one_or_none()

    if not status_mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status not found"
        )

    mou_count = (await db.execute(select(func.count()).select_from(MOU).where(MOU.status_mou_id == status_id))).scalar()
    if mou_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete status. It is being used by {mou_count} MOU(s)"
        )

    await db.delete(status_mou)
    await db.commit()

    return None
