from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy import select, func
from typing import List, Optional
from uuid import UUID
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.mou import MOU, MOU_Device
from app.models.serial_number import Serial_Number
from app.schemas.mou_device import MOUDeviceCreate, MOUDeviceUpdate, MOUDeviceResponse
from app.routers.mou.mou_device_helpers import (
    build_mou_device_id_query,
    build_mou_devices_excel_response,
    enrich_mou_device_response,
    ensure_serial_assignable_to_mou,
    fetch_mou_devices_by_ids,
    mou_device_to_export_row,
)
from app.utils.eager_loads import mou_device_load_options
from pydantic import BaseModel

# Wrapper response models for pagination with total count
class MOUDeviceListResponse(BaseModel):
    data: List[MOUDeviceResponse]
    total: int

router = APIRouter(prefix="/mou-devices", tags=["MOU Devices"])


# Get all MOU devices with pagination and optional filters
@router.get("/", response_model=MOUDeviceListResponse)
async def get_all_mou_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search across serial number, asset name, customer name, MOU number"),
    mou_id: Optional[UUID] = Query(None, description="Filter by MOU ID"),
    customer_id: Optional[UUID] = Query(None, description="Filter by Customer ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by device status (ACTIVE, INACTIVE, SERVICE)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all MOU devices with optional filtering

    - **search**: Search across serial number, asset name, customer name, MOU number (optional)
    - **mou_id**: Filter by specific MOU (optional)
    - **customer_id**: Filter by specific customer (optional)
    - **status**: Filter by device status: ACTIVE, INACTIVE, SERVICE (optional)
    """
    id_stmt = build_mou_device_id_query(
        search=search,
        mou_id=mou_id,
        customer_id=customer_id,
        status_filter=status_filter,
    )

    total = (await db.execute(
        select(func.count()).select_from(id_stmt.subquery())
    )).scalar()

    paginated_ids = id_stmt.offset(skip).limit(limit)
    devices = (await db.execute(
        select(MOU_Device).options(*mou_device_load_options()).where(MOU_Device.id.in_(paginated_ids))
    )).scalars().all()

    result = [enrich_mou_device_response(device) for device in devices]

    return MOUDeviceListResponse(data=result, total=total)


@router.get("/my-devices", response_model=MOUDeviceListResponse)
async def get_my_mou_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    show_all: bool = Query(False, description="Show all devices (including inactive). Sales only."),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all devices assigned to the current customer's MOUs

    For customers: Returns ACTIVE and SERVICE devices (ready for use or being serviced)
    For sales: Can see all devices with show_all=true
    """
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No customer associated with this user"
        )

    mou_ids = (await db.execute(
        select(MOU.id).where(
            MOU.customer_id == current_user.customer_id,
            MOU.deleted_at.is_(None)
        )
    )).scalars().all()

    if not mou_ids:
        return MOUDeviceListResponse(data=[], total=0)

    conditions = [MOU_Device.mou_id.in_(mou_ids)]
    is_sales = current_user.role and current_user.role.scope == "SALES"
    if not is_sales or not show_all:
        conditions.append(MOU_Device.status.in_(["ACTIVE", "SERVICE"]))

    total = (await db.execute(
        select(func.count(MOU_Device.id)).where(*conditions)
    )).scalar()

    devices = (await db.execute(
        select(MOU_Device).options(*mou_device_load_options()).where(*conditions).offset(skip).limit(limit)
    )).scalars().all()

    return MOUDeviceListResponse(data=devices, total=total)


@router.get("/export")
async def export_mou_devices(
    search: Optional[str] = Query(None, description="Search across serial number, asset name, customer name, MOU number"),
    mou_id: Optional[UUID] = Query(None, description="Filter by MOU ID"),
    customer_id: Optional[UUID] = Query(None, description="Filter by Customer ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by device status (ACTIVE, INACTIVE, SERVICE)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Export MOU devices to Excel. Uses the same filters as the list endpoint."""
    id_stmt = build_mou_device_id_query(
        search=search,
        mou_id=mou_id,
        customer_id=customer_id,
        status_filter=status_filter,
    )

    devices = await fetch_mou_devices_by_ids(db, id_stmt)
    rows = [
        mou_device_to_export_row(enrich_mou_device_response(device))
        for device in devices
    ]

    return build_mou_devices_excel_response(rows)


@router.get("/{mou_id}", response_model=MOUDeviceListResponse)
async def get_mou_devices(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all devices (printers) assigned to a specific MOU

    - **mou_id**: MOU ID (required)
    """
    mou = (await db.execute(
        select(MOU).where(MOU.id == mou_id)
    )).scalar_one_or_none()
    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU not found"
        )

    total = (await db.execute(
        select(func.count(MOU_Device.id)).where(MOU_Device.mou_id == mou_id)
    )).scalar()

    device_list = (await db.execute(
        select(MOU_Device).options(*mou_device_load_options()).where(MOU_Device.mou_id == mou_id)
    )).scalars().all()

    return MOUDeviceListResponse(data=device_list, total=total)


@router.get("/device/{device_id}", response_model=MOUDeviceResponse)
async def get_mou_device(
    device_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific MOU device by ID

    - **device_id**: MOU Device ID (required)
    """
    device = (await db.execute(
        select(MOU_Device).options(*mou_device_load_options()).where(MOU_Device.id == device_id)
    )).scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU device not found"
        )

    return device


@router.post("/{mou_id}", response_model=MOUDeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_mou_device(
    mou_id: UUID,
    device: MOUDeviceCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Assign a device (printer) to an MOU

    - **mou_id**: MOU ID in URL (required)
    - **serial_number_id**: Serial number ID of the device to assign (required)
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

    serial_number = (await db.execute(
        select(Serial_Number).where(Serial_Number.id == device.serial_number_id)
    )).scalar_one_or_none()

    if not serial_number:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Serial number not found"
        )

    ensure_serial_assignable_to_mou(serial_number)

    existing = (await db.execute(
        select(MOU_Device).where(
            MOU_Device.mou_id == mou_id,
            MOU_Device.serial_number_id == device.serial_number_id
        )
    )).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This device is already assigned to this MOU"
        )

    new_device = MOU_Device(
        mou_id=mou_id,
        serial_number_id=device.serial_number_id,
        location=device.location,
        status="ACTIVE"
    )
    db.add(new_device)

    serial_number.status = "ACTIVE"

    await db.commit()
    await db.refresh(new_device)

    device_with_relations = (await db.execute(
        select(MOU_Device).options(*mou_device_load_options()).where(MOU_Device.id == new_device.id)
    )).scalar_one_or_none()

    return device_with_relations


@router.put("/{device_id}", response_model=MOUDeviceResponse)
async def update_mou_device(
    device_id: UUID,
    device_update: MOUDeviceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an MOU device assignment

    - **device_id**: MOU Device ID (required)
    - Can update mou_id or serial_number_id
    """
    device = (await db.execute(
        select(MOU_Device).where(MOU_Device.id == device_id)
    )).scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU device not found"
        )

    update_data = device_update.model_dump(exclude_unset=True)

    if "mou_id" in update_data:
        mou = (await db.execute(
            select(MOU).where(
                MOU.id == update_data["mou_id"],
                MOU.deleted_at.is_(None)
            )
        )).scalar_one_or_none()

        if not mou:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="MOU not found"
            )

    if "serial_number_id" in update_data:
        serial_number = (await db.execute(
            select(Serial_Number).where(Serial_Number.id == update_data["serial_number_id"])
        )).scalar_one_or_none()

        if not serial_number:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Serial number not found"
            )

        ensure_serial_assignable_to_mou(serial_number)

    for key, value in update_data.items():
        setattr(device, key, value)

    await db.commit()
    await db.refresh(device)

    device_with_relations = (await db.execute(
        select(MOU_Device).options(*mou_device_load_options()).where(MOU_Device.id == device.id)
    )).scalar_one_or_none()

    return device_with_relations


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mou_device(
    device_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove a device assignment from MOU permanently

    - **device_id**: MOU Device ID (required)
    - ⚠️ This action cannot be undone
    """
    device = (await db.execute(
        select(MOU_Device).where(MOU_Device.id == device_id)
    )).scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU device not found"
        )

    await db.delete(device)
    await db.commit()

    return None


# Activate device (Sales only) - Change status from INACTIVE to ACTIVE
@router.put("/{device_id}/activate", response_model=MOUDeviceResponse)
async def activate_mou_device(
    device_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Activate an MOU device (Sales only)

    Changes device status from INACTIVE to ACTIVE so customers can use it for service orders
    """
    if not current_user.role or current_user.role.scope != "SALES":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only sales users can activate devices"
        )

    device = (await db.execute(
        select(MOU_Device).options(
            joinedload(MOU_Device.serial_number)
        ).where(MOU_Device.id == device_id)
    )).scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU device not found"
        )

    if device.status == "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device is already active"
        )

    if device.status == "SERVICE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot activate device while it's being serviced"
        )

    ensure_serial_assignable_to_mou(device.serial_number)

    device.status = "ACTIVE"
    device.serial_number.status = "ACTIVE"

    await db.commit()
    await db.refresh(device)

    device_with_relations = (await db.execute(
        select(MOU_Device).options(*mou_device_load_options()).where(MOU_Device.id == device.id)
    )).scalar_one_or_none()

    return device_with_relations


# Deactivate device (Sales only) - Change status from ACTIVE to INACTIVE
@router.put("/{device_id}/deactivate", response_model=MOUDeviceResponse)
async def deactivate_mou_device(
    device_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Deactivate an MOU device (Sales only)

    Changes device status from ACTIVE to INACTIVE
    """
    if not current_user.role or current_user.role.scope != "SALES":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only sales users can deactivate devices"
        )

    device = (await db.execute(
        select(MOU_Device).options(
            joinedload(MOU_Device.serial_number)
        ).where(MOU_Device.id == device_id)
    )).scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU device not found"
        )

    if device.status == "INACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device is already inactive"
        )

    if device.status == "SERVICE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate device while it's being serviced"
        )

    device.status = "INACTIVE"
    device.serial_number.status = "INACTIVE"

    await db.commit()
    await db.refresh(device)

    device_with_relations = (await db.execute(
        select(MOU_Device).options(*mou_device_load_options()).where(MOU_Device.id == device.id)
    )).scalar_one_or_none()

    return device_with_relations
