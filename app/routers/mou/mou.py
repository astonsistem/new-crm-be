from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.mou import MOU
from app.models.status import Status_MOU
from app.models.customer import Customer
from app.models.order import Order_Customer, Order_Service
from app.schemas.mou import MOUCreate, MOUUpdate, MOUResponse, MOURenewRequest, MOURenewResponse
from app.routers.mou.mou_files import read_contract_file_base64
from app.routers.mou.mou_helpers import (
    close_expired_mou,
    fetch_active_mou,
    get_status_mou_id,
    renew_expired_mou,
)
from app.utils.eager_loads import mou_load_options
from app.utils.db_queries import fetch_first, fetch_scalar_first, row_exists
import re

router = APIRouter(prefix="/mou", tags=["MOU"])

class MOUListResponse(BaseModel):
    data: List[MOUResponse]
    total: int


def _build_mou_response(mou: MOU, *, include_contract_base64: bool = False) -> MOUResponse:
    response = MOUResponse.model_validate(mou)
    if not include_contract_base64 or not mou.contract_file:
        return response
    contract_file_base64 = read_contract_file_base64(mou.contract_file)
    if contract_file_base64 is None:
        return response
    return response.model_copy(update={"contract_file_base64": contract_file_base64})

# Get current customer's MOU
@router.get("/me", response_model=MOUResponse)
async def get_my_mou(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the latest active MOU for the currently logged-in customer
    
    Returns the most recently created active MOU associated with the user's customer account
    """
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No customer associated with this user"
        )
    
    active_status_id = await fetch_scalar_first(
        db, select(Status_MOU.id).where(Status_MOU.name == "ACTIVE")
    )
    if not active_status_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active MOU status not configured",
        )

    latest_active_mou = await fetch_first(
        db,
        select(MOU).options(*mou_load_options()).where(
            MOU.customer_id == current_user.customer_id,
            MOU.deleted_at.is_(None),
            MOU.status_mou_id == active_status_id,
        ).order_by(MOU.created_at.desc()),
    )
    
    if not latest_active_mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active MOU found for this customer"
        )
    
    return latest_active_mou


# List all MOUs with pagination
@router.get("/", response_model=MOUListResponse)
async def get_mous(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=200),
    search: Optional[str] = Query(None, description="Search across MOU number, customer name, creator name, and status name"),
    customer_id: Optional[UUID] = None,
    customer_name: Optional[str] = Query(None, description="Filter by customer name (partial match)"),
    status_mou_id: Optional[UUID] = None,
    status_name: Optional[str] = Query(None, description="Filter by status name (partial match)"),
    created_by: Optional[UUID] = Query(None, description="Filter by creator user ID"),
    created_by_name: Optional[str] = Query(None, description="Filter by creator name (partial match)"),
    include_deleted: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all MOUs with optional filtering
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **search**: Search across MOU number, customer name, creator name, status name (optional)
    - **customer_id**: Filter by customer ID (optional)
    - **customer_name**: Filter by customer name (optional)
    - **status_mou_id**: Filter by status ID (optional)
    - **status_name**: Filter by status name (optional)
    - **created_by**: Filter by creator user ID (optional)
    - **created_by_name**: Filter by creator name (optional)
    - **include_deleted**: Include soft-deleted MOUs (default: false)
    """
    conditions = []
    join_customer = False
    join_status = False
    join_user = False

    if not include_deleted:
        conditions.append(MOU.deleted_at.is_(None))

    if search:
        join_customer = True
        join_status = True
        join_user = True
        conditions.append(
            func.lower(MOU.no_mou).contains(search.lower()) |
            func.lower(Customer.name).contains(search.lower()) |
            func.lower(User.name).contains(search.lower()) |
            func.lower(Status_MOU.name).contains(search.lower())
        )

    if customer_id:
        conditions.append(MOU.customer_id == customer_id)

    if customer_name:
        join_customer = True
        conditions.append(Customer.name.ilike(f"%{customer_name}%"))

    if status_mou_id:
        conditions.append(MOU.status_mou_id == status_mou_id)

    if status_name:
        join_status = True
        conditions.append(Status_MOU.name.ilike(f"%{status_name}%"))

    if created_by:
        conditions.append(MOU.created_by == created_by)

    if created_by_name:
        join_user = True
        conditions.append(User.name.ilike(f"%{created_by_name}%"))

    id_stmt = select(MOU.id)
    if join_customer:
        id_stmt = id_stmt.outerjoin(Customer, MOU.customer_id == Customer.id)
    if join_status:
        id_stmt = id_stmt.outerjoin(Status_MOU, MOU.status_mou_id == Status_MOU.id)
    if join_user:
        id_stmt = id_stmt.outerjoin(User, MOU.created_by == User.id)
    if conditions:
        id_stmt = id_stmt.where(*conditions)

    total = (await db.execute(
        select(func.count()).select_from(id_stmt.subquery())
    )).scalar()

    paginated_ids = id_stmt.offset(skip).limit(limit)
    mous = (await db.execute(
        select(MOU).options(*mou_load_options()).where(MOU.id.in_(paginated_ids))
    )).scalars().all()

    return MOUListResponse(data=mous, total=total)


@router.get('/mou-list', response_model=MOUListResponse)
async def get_mou_list_by_customer(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    include_deleted: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of MOUs for the currently logged-in customer
    
    Returns all MOUs associated with the user's customer account
    """
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No customer associated with this user"
        )

    conditions = [MOU.customer_id == current_user.customer_id]
    if not include_deleted:
        conditions.append(MOU.deleted_at.is_(None))

    total = (await db.execute(
        select(func.count(MOU.id)).where(*conditions)
    )).scalar()

    mous = (await db.execute(
        select(MOU).options(*mou_load_options()).where(*conditions).offset(skip).limit(limit)
    )).scalars().all()

    return MOUListResponse(data=mous, total=total)


# Get MOUs created by current user
@router.get("/my-created", response_model=MOUListResponse)
async def get_my_created_mous(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(200, ge=1, le=200, description="Maximum number of records to return"),
    customer_id: Optional[UUID] = Query(None, description="Filter by customer ID"),
    status_mou_id: Optional[UUID] = Query(None, description="Filter by status ID"),
    include_deleted: bool = Query(False, description="Include soft-deleted MOUs"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all MOUs created by the current user
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **customer_id**: Filter by customer ID (optional)
    - **status_mou_id**: Filter by status ID (optional)
    - **include_deleted**: Include soft-deleted MOUs (default: false)
    """
    conditions = [MOU.created_by == current_user.id]
    if not include_deleted:
        conditions.append(MOU.deleted_at.is_(None))
    if customer_id:
        conditions.append(MOU.customer_id == customer_id)
    if status_mou_id:
        conditions.append(MOU.status_mou_id == status_mou_id)

    total = (await db.execute(
        select(func.count(MOU.id)).where(*conditions)
    )).scalar()

    mous = (await db.execute(
        select(MOU).options(*mou_load_options()).where(*conditions).offset(skip).limit(limit)
    )).scalars().all()

    return MOUListResponse(data=mous, total=total)


@router.get("/expired", response_model=MOUListResponse)
async def get_expired_mous(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    customer_id: Optional[UUID] = Query(None, description="Filter by customer ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List MOUs that have passed end_date and are still ACTIVE (awaiting renewal decision)."""
    active_status_id = await get_status_mou_id(db, "ACTIVE")
    conditions = [
        MOU.deleted_at.is_(None),
        MOU.status_mou_id == active_status_id,
        MOU.end_date < datetime.now(),
    ]
    if customer_id:
        conditions.append(MOU.customer_id == customer_id)

    total = (await db.execute(
        select(func.count(MOU.id)).where(*conditions)
    )).scalar()

    mous = (await db.execute(
        select(MOU).options(*mou_load_options()).where(*conditions)
        .order_by(MOU.end_date.desc()).offset(skip).limit(limit)
    )).scalars().all()

    return MOUListResponse(data=mous, total=total)


# Get MOU by ID
@router.get("/{mou_id}", response_model=MOUResponse)
async def get_mou(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific MOU by ID
    """
    mou = (await db.execute(
        select(MOU).options(*mou_load_options()).where(
            MOU.id == mou_id,
            MOU.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU not found"
        )

    return _build_mou_response(mou, include_contract_base64=True)


async def generate_mou_number(db: AsyncSession) -> str:
    """
    Generate next MOU number in format MOU-001, MOU-002, etc.
    Uses numeric max (not string sort) to avoid ordering bugs.
    """
    result = await db.execute(
        select(MOU.no_mou).where(MOU.no_mou.like("MOU-%"))
    )
    max_number = 0
    for no_mou in result.scalars().all():
        match = re.search(r"MOU-(\d+)", no_mou or "")
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"MOU-{max_number + 1:03d}"


# Create new MOU
@router.post("/", response_model=MOUResponse, status_code=status.HTTP_201_CREATED)
async def create_mou(
    mou_data: MOUCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new MOU
    
    - **customer_id**: Customer ID (required)
    - **status_mou_id**: Status ID (required)
    - **start_date**: MOU start date (required)
    - **end_date**: MOU end date (required)
    - **description**: MOU description (optional)
    - **contract_file**: Contract file path (optional)
    
    Note: MOU number will be auto-generated in format MOU-001, MOU-002, etc.
    """
    auto_generated_no_mou = await generate_mou_number(db)

    customer = (await db.execute(
        select(Customer).where(Customer.id == mou_data.customer_id)
    )).scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    status_mou = (await db.execute(
        select(Status_MOU).where(Status_MOU.id == mou_data.status_mou_id)
    )).scalar_one_or_none()
    if not status_mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Status not found"
        )

    if mou_data.end_date <= mou_data.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be after start date"
        )

    new_mou = MOU(
        no_mou=auto_generated_no_mou,
        customer_id=mou_data.customer_id,
        status_mou_id=mou_data.status_mou_id,
        start_date=mou_data.start_date,
        end_date=mou_data.end_date,
        description=mou_data.description,
        contract_file=mou_data.contract_file,
        created_by=current_user.id
    )

    db.add(new_mou)
    await db.commit()
    await db.refresh(new_mou)

    mou_with_relations = (await db.execute(
        select(MOU).options(*mou_load_options()).where(MOU.id == new_mou.id)
    )).scalar_one_or_none()

    return mou_with_relations


@router.put("/{mou_id}/renew", response_model=MOURenewResponse)
async def renew_mou(
    mou_id: UUID,
    renew_data: MOURenewRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Renew an expired MOU.

    Creates a new ACTIVE MOU with a new ID and MOU number, copies products/devices/contract,
    and marks the old MOU as INACTIVE.
    """
    mou = await fetch_active_mou(db, mou_id)
    old_mou, new_mou = await renew_expired_mou(
        db,
        mou,
        start_date=renew_data.start_date,
        end_date=renew_data.end_date,
        created_by=current_user.id,
        generate_mou_number=generate_mou_number,
    )
    return MOURenewResponse(old_mou=old_mou, new_mou=new_mou)


@router.put("/{mou_id}/close", response_model=MOUResponse)
async def close_mou(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Close an expired MOU without renewal.

    Sets the MOU status to INACTIVE when end_date has passed.
    """
    mou = await fetch_active_mou(db, mou_id)
    closed_mou = await close_expired_mou(db, mou)
    return closed_mou


# Update MOU
@router.put("/{mou_id}", response_model=MOUResponse)
async def update_mou(
    mou_id: UUID,
    mou_data: MOUUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing MOU
    
    - All fields are optional
    - Only provided fields will be updated
    """
    mou = (await db.execute(
        select(MOU).options(*mou_load_options()).where(
            MOU.id == mou_id,
            MOU.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU not found"
        )

    has_order = await row_exists(
        db, select(Order_Customer.id).where(Order_Customer.mou_id == mou_id)
    )
    has_service = await row_exists(
        db, select(Order_Service.id).where(Order_Service.mou_id == mou_id)
    )
    if has_order or has_service:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot update MOU that already has an associated order or service"
        )

    update_data = mou_data.model_dump(exclude_unset=True)

    if "no_mou" in update_data and update_data["no_mou"] != mou.no_mou:
        existing_mou = (await db.execute(
            select(MOU).where(MOU.no_mou == update_data["no_mou"])
        )).scalar_one_or_none()
        if existing_mou:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MOU number already exists"
            )

    if "customer_id" in update_data:
        customer = (await db.execute(
            select(Customer).where(Customer.id == update_data["customer_id"])
        )).scalar_one_or_none()
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )

    if "status_mou_id" in update_data:
        status_mou = (await db.execute(
            select(Status_MOU).where(Status_MOU.id == update_data["status_mou_id"])
        )).scalar_one_or_none()
        if not status_mou:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Status not found"
            )

    start_date = update_data.get("start_date", mou.start_date)
    end_date = update_data.get("end_date", mou.end_date)
    if end_date <= start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be after start date"
        )

    for field, value in update_data.items():
        setattr(mou, field, value)

    await db.commit()
    await db.refresh(mou)

    mou_with_relations = (await db.execute(
        select(MOU).options(*mou_load_options()).where(MOU.id == mou.id)
    )).scalar_one_or_none()

    return mou_with_relations


# Soft delete MOU
@router.delete("/{mou_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mou(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Soft delete an MOU
    
    - Sets deleted_at timestamp
    - MOU can still be recovered later
    """
    mou = (await db.execute(
        select(MOU).where(
            MOU.id == mou_id,
            MOU.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU not found"
        )

    mou.deleted_at = datetime.utcnow()
    await db.commit()

    return None


# Restore deleted MOU
@router.patch("/{mou_id}/restore", response_model=MOUResponse)
async def restore_mou(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Restore a soft-deleted MOU
    
    - Clears deleted_at timestamp
    """
    mou = (await db.execute(
        select(MOU).options(*mou_load_options()).where(
            MOU.id == mou_id,
            MOU.deleted_at.isnot(None)
        )
    )).scalar_one_or_none()

    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deleted MOU not found"
        )

    mou.deleted_at = None
    await db.commit()

    # Re-query with eager loading — db.refresh() strips loaded relationships
    mou = (await db.execute(
        select(MOU).options(*mou_load_options()).where(MOU.id == mou_id)
    )).scalar_one()

    return mou


# Hard delete MOU (permanent)
@router.delete("/{mou_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mou_permanent(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Permanently delete an MOU from the database
    
    - ⚠️ This action cannot be undone
    - Will also delete all associated MOU products
    """
    mou = (await db.execute(
        select(MOU).where(MOU.id == mou_id)
    )).scalar_one_or_none()

    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU not found"
        )

    await db.delete(mou)
    await db.commit()

    return None
