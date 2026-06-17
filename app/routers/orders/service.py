from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, or_
from sqlalchemy.orm import joinedload
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import os
import pandas as pd
import io
from pathlib import Path
from app.dependencies import get_current_active_user, get_db
from app.utils.permissions import require_permission, Permission
from app.models import User, Customer
from app.models.order import Order_Service, Service_Activity_Log
from app.models.mou import MOU, MOU_Device
from app.models.serial_number import Serial_Number
from app.models.status import Status_Service
from app.schemas.orders.service import (
    OrderServiceCreate,
    OrderServiceResponse,
    ServiceScheduleRequest,
    ServiceProcessRequest,
    ServiceCompleteRequest,
    ServiceCancelRequest,
    MyCustomersServicesResponse,
    ServiceActivityLogResponse
)
from app.routers.service_point import ensure_service_point_exists
from app.utils.db_queries import fetch_first
from app.utils.excel_export import format_worksheet
from app.utils.datetime_utils import OptionalNaiveDatetime
from pydantic import BaseModel

class ServiceActivityLogListResponse(BaseModel):
    data: List[ServiceActivityLogResponse]
    total: int

router = APIRouter(prefix="/order-service", tags=["Order Service"])


def _require_customer_id(current_user: User) -> UUID:
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with any customer",
        )
    return current_user.customer_id


def _service_load_options(*, include_user_customer: bool = False):
    created_user_load = (
        joinedload(Order_Service.created_user).joinedload(User.customer)
        if include_user_customer
        else joinedload(Order_Service.created_user)
    )
    return [
        joinedload(Order_Service.mou),
        joinedload(Order_Service.status_service),
        joinedload(Order_Service.mou_device).joinedload(MOU_Device.serial_number).joinedload(Serial_Number.asset),
        joinedload(Order_Service.service_point),
        created_user_load,
        joinedload(Order_Service.activity_logs).joinedload(Service_Activity_Log.user),
    ]


async def fetch_order_service(
    db: AsyncSession,
    service_id: UUID,
    *,
    include_user_customer: bool = False,
) -> Order_Service | None:
    return (await db.execute(
        select(Order_Service)
        .options(*_service_load_options(include_user_customer=include_user_customer))
        .where(Order_Service.id == service_id)
    )).unique().scalar_one_or_none()


async def generate_service_number(db: AsyncSession) -> str:
    result = await db.execute(
        select(Order_Service.service_number).where(
            Order_Service.service_number.like("SVC-%")
        )
    )
    max_number = 0
    for service_number in result.scalars().all():
        try:
            max_number = max(max_number, int(service_number.split("-")[1]))
        except (IndexError, ValueError, AttributeError):
            continue
    return f"SVC-{max_number + 1:03d}"


async def get_or_create_service_status(db: AsyncSession, name: str) -> Status_Service:
    svc_status = await fetch_first(
        db, select(Status_Service).where(Status_Service.name == name)
    )

    if not svc_status:
        svc_status = Status_Service(code=name, name=name)
        db.add(svc_status)
        await db.flush()

    return svc_status


@router.get("/", response_model=List[OrderServiceResponse])
async def get_order_services(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search across service number, description, customer name, device info, or status"),
    mou_id: Optional[UUID] = None,
    status_service_id: Optional[UUID] = None,
    mou_device_id: Optional[UUID] = None,
    service_point_id: Optional[UUID] = Query(None, description="Filter by service point ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of all order services with optional filtering and search"""
    stmt = select(Order_Service).options(*_service_load_options())

    if search:
        from app.models.asset import Asset

        stmt = stmt.join(MOU, Order_Service.mou_id == MOU.id)\
                   .join(Customer, MOU.customer_id == Customer.id)\
                   .outerjoin(Status_Service, Order_Service.status_service_id == Status_Service.id)\
                   .outerjoin(MOU_Device, Order_Service.mou_device_id == MOU_Device.id)\
                   .outerjoin(Serial_Number, MOU_Device.serial_number_id == Serial_Number.id)\
                   .outerjoin(Asset, Serial_Number.asset_id == Asset.id)

        search_term = f"%{search.lower()}%"

        stmt = stmt.where(or_(
            Order_Service.service_number.ilike(search_term),
            Order_Service.description.ilike(search_term),
            Customer.name.ilike(search_term),
            Status_Service.name.ilike(search_term),
            Asset.asset_name.ilike(search_term),
            Serial_Number.serial_code.ilike(search_term)
        ))

    if mou_id:
        stmt = stmt.where(Order_Service.mou_id == mou_id)

    if status_service_id:
        stmt = stmt.where(Order_Service.status_service_id == status_service_id)

    if mou_device_id:
        stmt = stmt.where(Order_Service.mou_device_id == mou_device_id)

    if service_point_id:
        stmt = stmt.where(Order_Service.service_point_id == service_point_id)

    order_services = (await db.execute(stmt.offset(skip).limit(limit))).unique().scalars().all()

    return order_services


@router.get("/my-services", response_model=MyCustomersServicesResponse)
async def get_my_services(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    status_name: Optional[str] = Query(None, description="Filter by status name (e.g. REQUEST, PENDING, PROCESS, COMPLETE)"),
    start_date: OptionalNaiveDatetime = Query(None, description="Filter services after this date"),
    end_date: OptionalNaiveDatetime = Query(None, description="Filter services before this date"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get service orders for the currently logged-in customer."""
    customer_id = _require_customer_id(current_user)

    if end_date and end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59)

    mou_ids = (await db.execute(
        select(MOU.id).where(
            MOU.customer_id == customer_id,
            MOU.deleted_at.is_(None),
        )
    )).scalars().all()

    if not mou_ids:
        return MyCustomersServicesResponse(data=[], total_services=0)

    base_where = [Order_Service.mou_id.in_(mou_ids)]
    if start_date:
        base_where.append(Order_Service.created_at >= start_date)
    if end_date:
        base_where.append(Order_Service.created_at <= end_date)

    count_inner = select(Order_Service.id).where(*base_where)
    if status_name:
        count_inner = count_inner.join(Status_Service).where(Status_Service.name == status_name)

    total_services = (await db.execute(
        select(func.count()).select_from(count_inner.subquery())
    )).scalar()

    stmt = select(Order_Service).options(*_service_load_options()).where(*base_where)
    if status_name:
        stmt = stmt.join(Status_Service).where(Status_Service.name == status_name)

    services = (await db.execute(
        stmt.order_by(Order_Service.created_at.desc()).offset(skip).limit(limit)
    )).unique().scalars().all()

    response_items = []
    for service in services:
        item = OrderServiceResponse.model_validate(service)
        if service.completed_at and service.created_at:
            item.service_days = (service.completed_at - service.created_at).days + 1
        response_items.append(item)

    return MyCustomersServicesResponse(
        data=response_items,
        total_services=total_services,
    )


@router.get("/my-customers-services", response_model=MyCustomersServicesResponse)
async def get_my_customers_services(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    customer_id: Optional[UUID] = Query(None, description="Filter services by specific customer ID"),
    status_name: Optional[str] = Query(None, description="Filter by status name (e.g. REQUEST, PENDING, PROCESS, COMPLETE)"),
    start_date: OptionalNaiveDatetime = Query(None, description="Filter services after this date"),
    end_date: OptionalNaiveDatetime = Query(None, description="Filter services before this date"),
    current_user: User = Depends(require_permission(Permission.READ_SERVICE)),
    db: AsyncSession = Depends(get_db)
):
    """Get all service orders from customers created by current sales user"""

    if end_date and end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59)

    customer_stmt = select(Customer.id).where(Customer.sales_id == current_user.id)
    if customer_id:
        customer_stmt = customer_stmt.where(Customer.id == customer_id)

    customer_ids = (await db.execute(customer_stmt)).scalars().all()

    if not customer_ids:
        return MyCustomersServicesResponse(data=[], total_services=0)

    mou_ids = (await db.execute(
        select(MOU.id).where(
            MOU.customer_id.in_(customer_ids),
            MOU.deleted_at.is_(None)
        )
    )).scalars().all()

    if not mou_ids:
        return MyCustomersServicesResponse(data=[], total_services=0)

    base_where = [Order_Service.mou_id.in_(mou_ids)]
    if start_date:
        base_where.append(Order_Service.created_at >= start_date)
    if end_date:
        base_where.append(Order_Service.created_at <= end_date)

    count_inner = select(Order_Service.id).where(*base_where)
    if status_name:
        count_inner = count_inner.join(Status_Service).where(Status_Service.name == status_name)

    total_services = (await db.execute(
        select(func.count()).select_from(count_inner.subquery())
    )).scalar()

    stmt = select(Order_Service).options(
        *_service_load_options(include_user_customer=True)
    ).where(*base_where)

    if status_name:
        stmt = stmt.join(Status_Service).where(Status_Service.name == status_name)

    services = (await db.execute(
        stmt.order_by(Order_Service.created_at.desc()).offset(skip).limit(limit)
    )).unique().scalars().all()

    response_items = []
    for service in services:
        item = OrderServiceResponse.model_validate(service)
        if service.completed_at and service.created_at:
            item.service_days = (service.completed_at - service.created_at).days + 1
        if service.created_user and service.created_user.customer:
            item.created_user.name = service.created_user.customer.name
        response_items.append(item)

    return MyCustomersServicesResponse(
        data=response_items,
        total_services=total_services
    )


@router.get("/my-customers-services/export")
async def export_service_order_log(
    sales_id: Optional[UUID] = Query(None, description="Filter by sales user ID. If not provided, exports all services."),
    customer_id: Optional[UUID] = Query(None, description="Filter services by specific customer ID"),
    status_name: Optional[str] = Query(None, description="Filter by status name (e.g. PENDING, COMPLETED)"),
    start_date: OptionalNaiveDatetime = Query(None, description="Filter services after this date"),
    end_date: OptionalNaiveDatetime = Query(None, description="Filter services before this date"),
    current_user: User = Depends(require_permission(Permission.READ_SERVICE)),
    db: AsyncSession = Depends(get_db)
):
    """Export services log to Excel.

    - **sales_id**: Filter by sales user ID. If not provided, exports ALL services.
    - **customer_id**: Filter by customer ID (optional)
    - **status_name**: Filter by status name (optional)
    - **start_date / end_date**: Date range filter (optional)
    """

    if end_date and end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59)

    stmt = select(
        Order_Service,
        Customer.name.label('customer_name'),
        Customer.type.label('customer_type'),
        Customer.PIC.label('customer_pic'),
        Customer.pic_phone.label('customer_pic_phone'),
        Customer.phone.label('customer_phone'),
    ).options(
        joinedload(Order_Service.mou),
        joinedload(Order_Service.status_service),
        joinedload(Order_Service.mou_device).joinedload(MOU_Device.serial_number).joinedload(Serial_Number.asset),
        joinedload(Order_Service.created_user),
        joinedload(Order_Service.service_point),
    ).join(MOU, Order_Service.mou_id == MOU.id)\
     .join(Customer, MOU.customer_id == Customer.id)

    if sales_id:
        stmt = stmt.where(Customer.sales_id == sales_id)

    if customer_id:
        stmt = stmt.where(Customer.id == customer_id)

    if status_name:
        stmt = stmt.join(
            Status_Service, Order_Service.status_service_id == Status_Service.id
        ).where(Status_Service.name == status_name)

    if start_date:
        stmt = stmt.where(Order_Service.created_at >= start_date)
    if end_date:
        stmt = stmt.where(Order_Service.created_at <= end_date)

    services = (await db.execute(stmt.order_by(Order_Service.created_at.desc()))).all()

    excel_data = []

    for service_data in services:
        service = service_data[0]
        cust_name = service_data[1]
        cust_type = service_data[2]
        cust_pic = service_data[3]
        cust_pic_phone = service_data[4]
        cust_phone = service_data[5]

        asset_name = "N/A"
        serial_code = "N/A"
        if service.mou_device and service.mou_device.serial_number:
            asset_name = (
                service.mou_device.serial_number.asset.asset_name
                if service.mou_device.serial_number.asset
                else "N/A"
            )
            serial_code = service.mou_device.serial_number.serial_code

        created_by_name = service.created_user.name if service.created_user else "N/A"

        excel_data.append({
            'Service Number': service.service_number,
            'Service Date': service.service_date.strftime('%Y-%m-%d') if service.service_date else 'N/A',
            'Service Date Description': service.service_date_description or 'N/A',
            'Customer Name': cust_name,
            'Customer Type': cust_type,
            'Customer PIC': cust_pic or '',
            'Customer PIC Phone': cust_pic_phone or '',
            'Customer Phone': cust_phone or '',
            'Asset Name': asset_name,
            'Serial Code': serial_code,
            'Status': service.status_service.name if service.status_service else 'N/A',
            'Description': service.description or 'N/A',
            'Service Cost': float(service.service_cost) if service.service_cost is not None else 0,
            'Service Point': service.service_point.name if service.service_point else 'N/A',
            'Service Point Address': service.service_point.address if service.service_point else 'N/A',
            'MOU Number': service.mou.no_mou if service.mou else 'N/A',
            'Created By': created_by_name,
            'Created At': service.created_at.strftime('%Y-%m-%d'),
            'Completed At': service.completed_at.strftime('%Y-%m-%d') if service.completed_at else 'N/A',
            'Service Days': (service.completed_at - service.created_at).days + 1 if service.completed_at and service.created_at else 'N/A'
        })

    df = pd.DataFrame(excel_data) if excel_data else pd.DataFrame(columns=[
        'Service Number', 'Service Date', 'Service Date Description',
        'Customer Name', 'Customer Type', 'Customer PIC', 'Customer PIC Phone', 'Customer Phone',
        'Asset Name', 'Serial Code', 'Status',
        'Description', 'Service Cost', 'Service Point', 'Service Point Address',
        'MOU Number', 'Created By', 'Created At',
        'Completed At', 'Service Days'
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Service Order Log', index=False)

        format_worksheet(writer.sheets["Service Order Log"])

    output.seek(0)

    date_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    if sales_id:
        sales_user = (await db.execute(
            select(User).where(User.id == sales_id)
        )).scalar_one_or_none()
        export_name = sales_user.name.replace(" ", "_") if sales_user else "unknown"
        filename = f"service_order_log_{export_name}_{date_suffix}.xlsx"
    else:
        filename = f"all_services_{date_suffix}.xlsx"

    temp_file_path = f"uploads/temp_{filename}"
    os.makedirs("uploads", exist_ok=True)

    with open(temp_file_path, "wb") as f:
        f.write(output.getvalue())

    return FileResponse(
        path=temp_file_path,
        filename=filename,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@router.get("/{service_id}", response_model=OrderServiceResponse)
async def get_order_service(
    service_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific order service by ID"""
    order_service = await fetch_order_service(db, service_id)

    if not order_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order service not found"
        )

    return order_service


@router.get("/{service_id}/activity-log", response_model=ServiceActivityLogListResponse)
async def get_service_activity_log(
    service_id: UUID,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of records to return"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get activity log for a specific service with pagination"""
    service = (await db.execute(
        select(Order_Service).where(Order_Service.id == service_id)
    )).scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    total = (await db.execute(
        select(func.count(Service_Activity_Log.id)).where(Service_Activity_Log.service_id == service_id)
    )).scalar()

    logs = (await db.execute(
        select(Service_Activity_Log).options(
            joinedload(Service_Activity_Log.user)
        ).where(
            Service_Activity_Log.service_id == service_id
        ).order_by(Service_Activity_Log.created_at.asc())
        .offset(skip).limit(limit)
    )).scalars().all()

    return ServiceActivityLogListResponse(data=logs, total=total)


@router.post("/", response_model=OrderServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_order_service(
    service_data: OrderServiceCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new order service"""
    mou = (await db.execute(
        select(MOU).where(MOU.id == service_data.mou_id, MOU.deleted_at.is_(None))
    )).scalar_one_or_none()

    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU not found"
        )

    mou_device = (await db.execute(
        select(MOU_Device).options(
            joinedload(MOU_Device.serial_number)
        ).where(MOU_Device.id == service_data.mou_device_id)
    )).scalar_one_or_none()

    if not mou_device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU device not found"
        )

    if mou_device.mou_id != service_data.mou_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device does not belong to the specified MOU"
        )

    if mou_device.status != "ACTIVE":
        if mou_device.status == "INACTIVE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Device is not activated yet. Please contact sales to activate this device."
            )
        elif mou_device.status == "SERVICE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Device is already being serviced. Please wait for current service to complete."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device is not available for service. Current status: {mou_device.status}"
            )

    if service_data.service_point_id:
        await ensure_service_point_exists(db, service_data.service_point_id)

    request_status = await get_or_create_service_status(db, "REQUEST")
    service_number = await generate_service_number(db)

    mou_device.status = "SERVICE"
    mou_device.serial_number.status = "SERVICE"

    new_order_service = Order_Service(
        service_number=service_number,
        mou_id=service_data.mou_id,
        mou_device_id=service_data.mou_device_id,
        status_service_id=request_status.id,
        description=service_data.description,
        service_cost=service_data.service_cost,
        service_point_id=service_data.service_point_id,
        created_by=current_user.id
    )

    db.add(new_order_service)
    await db.flush()

    db.add(Service_Activity_Log(
        service_id=new_order_service.id,
        status="service_created",
        description=f"Service {new_order_service.service_number} telah dibuat dengan status REQUEST",
        created_by=current_user.id,
    ))
    await db.commit()

    order_service = await fetch_order_service(db, new_order_service.id)

    return order_service


@router.put("/{service_id}/schedule", response_model=OrderServiceResponse)
async def schedule_service_order(
    service_id: UUID,
    schedule_data: ServiceScheduleRequest,
    current_user: User = Depends(require_permission(Permission.UPDATE_SERVICE)),
    db: AsyncSession = Depends(get_db)
):
    """
    Sales schedules a service by setting the service date.
    Status changes from REQUEST to PENDING.
    """

    order_service = (await db.execute(
        select(Order_Service).options(
            joinedload(Order_Service.status_service)
        ).where(Order_Service.id == service_id)
    )).scalar_one_or_none()

    if not order_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order service not found"
        )

    if order_service.status_service and order_service.status_service.name != "REQUEST":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service must be in REQUEST status to schedule. Current status: {order_service.status_service.name}"
        )

    pending_status = await get_or_create_service_status(db, "PENDING")

    order_service.status_service_id = pending_status.id
    order_service.service_date = schedule_data.service_date
    order_service.service_date_description = schedule_data.service_date_description
    if schedule_data.service_cost is not None:
        order_service.service_cost = schedule_data.service_cost
    if schedule_data.service_point_id is not None:
        await ensure_service_point_exists(db, schedule_data.service_point_id)
        order_service.service_point_id = schedule_data.service_point_id

    schedule_description = f"Service telah dijadwalkan untuk tanggal {schedule_data.service_date.strftime('%Y-%m-%d')}"
    if schedule_data.service_date_description:
        schedule_description += f" - {schedule_data.service_date_description}"

    activity_log = Service_Activity_Log(
        service_id=service_id,
        status="service_scheduled",
        description=schedule_description,
        created_by=current_user.id
    )
    db.add(activity_log)

    await db.commit()

    order_service = await fetch_order_service(db, service_id)

    return order_service


@router.put("/{service_id}/process", response_model=OrderServiceResponse)
async def process_service_order(
    service_id: UUID,
    process_data: Optional[ServiceProcessRequest] = None,
    current_user: User = Depends(require_permission(Permission.UPDATE_SERVICE)),
    db: AsyncSession = Depends(get_db)
):
    """
    Sales moves a service to in-progress.
    Status changes from PENDING to PROCESS.
    """

    order_service = (await db.execute(
        select(Order_Service).options(
            joinedload(Order_Service.status_service)
        ).where(Order_Service.id == service_id)
    )).scalar_one_or_none()

    if not order_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order service not found"
        )

    if order_service.status_service and order_service.status_service.name != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service must be in PENDING status to process. Current status: {order_service.status_service.name}"
        )

    process_status = await get_or_create_service_status(db, "PROCESS")

    order_service.status_service_id = process_status.id
    if process_data and process_data.service_cost is not None:
        order_service.service_cost = process_data.service_cost
    if process_data and process_data.service_point_id is not None:
        await ensure_service_point_exists(db, process_data.service_point_id)
        order_service.service_point_id = process_data.service_point_id

    activity_log = Service_Activity_Log(
        service_id=service_id,
        status="service_in_process",
        description=(process_data.description if process_data else None) or "Service sudah mulai dikerjakan",
        created_by=current_user.id
    )
    db.add(activity_log)

    await db.commit()

    order_service = await fetch_order_service(db, service_id)

    return order_service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order_service(
    service_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an order service"""
    order_service = (await db.execute(
        select(Order_Service).where(Order_Service.id == service_id)
    )).scalar_one_or_none()

    if not order_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order service not found"
        )

    await db.delete(order_service)
    await db.commit()

    return None


@router.put("/{service_id}/complete", response_model=OrderServiceResponse)
async def complete_service_order(
    service_id: UUID,
    complete_data: Optional[ServiceCompleteRequest] = None,
    current_user: User = Depends(require_permission(Permission.UPDATE_SERVICE)),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a service order as completed and activate the device.
    Status can change from PENDING or PROCESS to COMPLETE.
    Sets completed_at and calculates service_days.
    """

    order_service = (await db.execute(
        select(Order_Service).options(
            joinedload(Order_Service.mou_device).joinedload(MOU_Device.serial_number),
            joinedload(Order_Service.status_service)
        ).where(Order_Service.id == service_id)
    )).scalar_one_or_none()

    if not order_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order service not found"
        )

    if order_service.status_service and order_service.status_service.name == "COMPLETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service is already completed"
        )

    allowed_statuses = ["PENDING", "PROCESS"]
    if order_service.status_service and order_service.status_service.name not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service must be in PENDING or PROCESS status to complete. Current status: {order_service.status_service.name}"
        )

    complete_status = await get_or_create_service_status(db, "COMPLETE")

    order_service.status_service_id = complete_status.id
    order_service.completed_at = datetime.now()
    if complete_data and complete_data.service_cost is not None:
        order_service.service_cost = complete_data.service_cost

    if order_service.mou_device.status == "SERVICE":
        order_service.mou_device.status = "ACTIVE"
        order_service.mou_device.serial_number.status = "ACTIVE"

    activity_log = Service_Activity_Log(
        service_id=service_id,
        status="service_completed",
        description=(complete_data.description if complete_data else None) or "Service telah diselesaikan dan perangkat siap digunakan",
        created_by=current_user.id
    )
    db.add(activity_log)

    await db.commit()

    order_service = await fetch_order_service(db, service_id)

    service_days = None
    if order_service.completed_at and order_service.created_at:
        service_days = (order_service.completed_at - order_service.created_at).days + 1

    response = OrderServiceResponse.model_validate(order_service)
    response.service_days = service_days

    return response


@router.put("/{service_id}/cancel", response_model=OrderServiceResponse)
async def cancel_service_order(
    service_id: UUID,
    cancel_data: Optional[ServiceCancelRequest] = None,
    current_user: User = Depends(require_permission(Permission.UPDATE_SERVICE)),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel a service order and reactivate the device.
    Status can change from REQUEST, PENDING, or PROCESS to CANCELLED.
    """

    order_service = (await db.execute(
        select(Order_Service).options(
            joinedload(Order_Service.mou_device).joinedload(MOU_Device.serial_number),
            joinedload(Order_Service.status_service)
        ).where(Order_Service.id == service_id)
    )).scalar_one_or_none()

    if not order_service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order service not found"
        )

    current_status = order_service.status_service.name if order_service.status_service else None

    if current_status == "CANCELLED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service is already cancelled"
        )

    if current_status == "COMPLETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel a completed service"
        )

    allowed_statuses = ["REQUEST", "PENDING", "PROCESS"]
    if current_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service must be in REQUEST, PENDING, or PROCESS status to cancel. Current status: {current_status}"
        )

    cancelled_status = await get_or_create_service_status(db, "CANCELLED")

    order_service.status_service_id = cancelled_status.id

    if order_service.mou_device.status == "SERVICE":
        order_service.mou_device.status = "ACTIVE"
        order_service.mou_device.serial_number.status = "ACTIVE"

    activity_log = Service_Activity_Log(
        service_id=service_id,
        status="service_cancelled",
        description=(cancel_data.description if cancel_data else None) or "Service telah dibatalkan",
        created_by=current_user.id
    )
    db.add(activity_log)

    await db.commit()

    order_service = await fetch_order_service(db, service_id)

    return OrderServiceResponse.model_validate(order_service)
