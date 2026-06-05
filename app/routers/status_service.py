from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List
from uuid import UUID
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.status import Status_Service
from app.models.order import Order_Service
from app.schemas.status import StatusServiceCreate, StatusServiceUpdate, StatusServiceResponse

router = APIRouter(prefix="/status-service", tags=["STATUS SERVICE"])


# List all Service statuses
@router.get("/", response_model=List[StatusServiceResponse])
async def get_service_statuses(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all Service statuses
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    """
    statuses = (await db.execute(select(Status_Service).offset(skip).limit(limit))).scalars().all()
    return statuses


# Get service status by ID
@router.get("/{status_id}", response_model=StatusServiceResponse)
async def get_service_status(
    status_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific Service status by ID
    """
    status_service = (await db.execute(select(Status_Service).where(Status_Service.id == status_id))).scalar_one_or_none()

    if not status_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service status not found"
        )

    return status_service


# Create new Service status
@router.post("/", response_model=StatusServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service_status(
    status_data: StatusServiceCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new Service status
    
    - **code**: Unique status code (required)
    - **name**: Status name (optional)
    """
    existing_status = (await db.execute(select(Status_Service).where(Status_Service.code == status_data.code))).scalar_one_or_none()
    if existing_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service status code already exists"
        )

    new_status = Status_Service(
        code=status_data.code,
        name=status_data.name
    )

    db.add(new_status)
    await db.commit()
    await db.refresh(new_status)

    return new_status


# Update Service status
@router.put("/{status_id}", response_model=StatusServiceResponse)
async def update_service_status(
    status_id: UUID,
    status_data: StatusServiceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing Service status
    
    - All fields are optional
    - Only provided fields will be updated
    """
    status_service = (await db.execute(select(Status_Service).where(Status_Service.id == status_id))).scalar_one_or_none()

    if not status_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service status not found"
        )

    update_data = status_data.model_dump(exclude_unset=True)

    if "code" in update_data and update_data["code"] != status_service.code:
        existing_status = (await db.execute(select(Status_Service).where(Status_Service.code == update_data["code"]))).scalar_one_or_none()
        if existing_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service status code already exists"
            )

    for field, value in update_data.items():
        setattr(status_service, field, value)

    await db.commit()
    await db.refresh(status_service)

    return status_service


# Delete Service status
@router.delete("/{status_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_status(
    status_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a Service status permanently
    
    - ⚠️ This action cannot be undone
    """
    status_service = (await db.execute(select(Status_Service).where(Status_Service.id == status_id))).scalar_one_or_none()

    if not status_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service status not found"
        )

    service_count = (await db.execute(select(func.count()).select_from(Order_Service).where(Order_Service.status_service_id == status_id))).scalar()
    if service_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete status. It is being used by {service_count} service order(s)"
        )

    await db.delete(status_service)
    await db.commit()

    return None
