from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import joinedload, aliased
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import io
import os
import pandas as pd
from app.dependencies import get_current_active_user, get_db
from app.utils.permissions import require_permission, Permission
from app.utils.db_queries import fetch_first
from app.utils.datetime_utils import OptionalNaiveDatetime
from app.utils.invoice import build_invoice_pdf
from app.routers.orders.helpers import (
    order_customer_load_options,
    fetch_order_customer,
    fetch_order_for_deletion,
    assert_can_delete_order,
    delete_order_files_from_disk,
)
from app.models import User, Customer
from app.models.order import Order_Customer, Order_Customer_Detail, Order_Cart, Order_Status, Order_Payment_File, Order_Service, Order_Activity_Log, Service_Activity_Log
from app.models.mou import MOU, MOU_Product, MOU_Device
from app.models.service_point import Service_Point
from app.models.serial_number import Serial_Number
from app.models.bank_account import Bank_Account
from app.schemas.orders.customer_order import (
    OrderCheckoutRequest,
    OrderCustomerResponse,
    OrderPaymentFileResponse,
    CustomerLogResponse,
    OrderActivityLogResponse
)
from pydantic import BaseModel

class ActivityLogListResponse(BaseModel):
    data: List[OrderActivityLogResponse]
    total: int

router = APIRouter(prefix="/orders", tags=["Customer Orders"])


async def generate_order_number(db: AsyncSession) -> str:
    """Generate the next order number in format ORD-001"""
    result = await db.execute(
        select(Order_Customer.order_number).where(
            Order_Customer.order_number.like("ORD-%")
        )
    )
    max_number = 0
    for order_number in result.scalars().all():
        try:
            max_number = max(max_number, int(order_number.split("-")[1]))
        except (IndexError, ValueError, AttributeError):
            continue
    return f"ORD-{max_number + 1:03d}"


def get_user_customer_id(current_user: User) -> UUID:
    """Get customer ID for the current user, raise error if not found"""
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User tidak terhubung dengan customer manapun"
        )
    return current_user.customer_id


async def _get_or_create_order_status(db: AsyncSession, name: str, description: str) -> Order_Status:
    """Get an order status by name, flush (not commit) if it needs to be created."""
    order_status = await fetch_first(
        db, select(Order_Status).where(Order_Status.name == name)
    )
    if not order_status:
        order_status = Order_Status(name=name, description=description)
        db.add(order_status)
        await db.flush()
    return order_status


async def get_pending_payment_status(db: AsyncSession) -> Order_Status:
    return await _get_or_create_order_status(db, "pending_payment", "Order created, awaiting payment confirmation")


async def get_paid_status(db: AsyncSession) -> Order_Status:
    return await _get_or_create_order_status(db, "paid", "Payment confirmed by sales")

async def get_waiting_approval_status(db: AsyncSession) -> Order_Status:
    return await _get_or_create_order_status(db, "waiting_approval", "Payment waiting for approval by sales")

async def get_shipped_status(db: AsyncSession) -> Order_Status:
    return await _get_or_create_order_status(db, "shipped", "Items shipped with resi proof")


async def get_completed_status(db: AsyncSession) -> Order_Status:
    return await _get_or_create_order_status(db, "completed", "Order completed and items received by customer")


@router.post("/checkout", response_model=OrderCustomerResponse, status_code=status.HTTP_201_CREATED)
async def checkout_cart(
    checkout_data: OrderCheckoutRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Convert cart items to order (Customer only)"""
    customer_id = get_user_customer_id(current_user)
    
    cart_items = (await db.execute(
        select(Order_Cart).where(Order_Cart.customer_id == customer_id)
    )).scalars().all()
    
    if not cart_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keranjang kosong"
        )
    
    mou = (await db.execute(
        select(MOU).where(
            MOU.id == checkout_data.mou_id,
            MOU.customer_id == customer_id,
            MOU.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    
    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU tidak ditemukan atau bukan milik customer Anda"
        )
    
    pending_status = await get_pending_payment_status(db)
    
    mou_product_ids = [item.mou_product_id for item in cart_items]
    mou_products = (await db.execute(
        select(MOU_Product).where(MOU_Product.id.in_(mou_product_ids))
    )).scalars().all()
    mou_product_map = {mp.id: mp for mp in mou_products}
    
    total = sum(
        item.quantity * mou_product_map[item.mou_product_id].contract_price
        for item in cart_items
    )
    
    order_number = await generate_order_number(db)
    
    new_order = Order_Customer(
        order_number=order_number,
        mou_id=checkout_data.mou_id,
        customer_id=customer_id,
        order_date=datetime.now(),
        total=total,
        status_id=pending_status.id
    )
    
    db.add(new_order)
    await db.flush()
    
    item_info_map = {}
    if checkout_data.items:
        for item in checkout_data.items:
            item_info_map[item.mou_product_id] = item

    for cart_item in cart_items:
        mou_product = mou_product_map[cart_item.mou_product_id]
        
        item_info = item_info_map.get(cart_item.mou_product_id)
        device_name = item_info.device_name if item_info else None
        serial_number = item_info.serial_number if item_info else None

        order_detail = Order_Customer_Detail(
            order_id=new_order.id,
            mou_product_id=cart_item.mou_product_id,
            quantity=cart_item.quantity,
            price=mou_product.contract_price,
            subtotal=cart_item.quantity * mou_product.contract_price,
            device_name=device_name,
            serial_number=serial_number
        )
        db.add(order_detail)
    
    await db.execute(
        delete(Order_Cart).where(Order_Cart.customer_id == customer_id)
    )

    db.add(Order_Activity_Log(
        order_id=new_order.id,
        status="order_created",
        description=f"Order {new_order.order_number} telah dibuat",
        created_by=current_user.id,
    ))

    await db.commit()
    order = await fetch_order_customer(db, new_order.id)
    return order

@router.get("/my-log", response_model=CustomerLogResponse)
async def get_my_log(
    customer_id: UUID = Query(..., description="Customer ID to get log for"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    status_name: Optional[str] = Query(None, description="Filter by order status"),
    start_date: OptionalNaiveDatetime = Query(None, description="Filter records from this date"),
    end_date: OptionalNaiveDatetime = Query(None, description="Filter records until this date"),
    include_orders: bool = Query(True, description="Include orders in response"),
    include_services: bool = Query(True, description="Include services in response"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get unified log of orders and services for a given customer"""
    
    if start_date:
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=0)
    
    orders = []
    services = []
    total_orders = 0
    total_services = 0
    
    if include_orders:
        order_stmt = select(Order_Customer).options(*order_customer_load_options()).where(Order_Customer.customer_id == customer_id)
        
        count_inner = select(Order_Customer.id).where(Order_Customer.customer_id == customer_id)
        
        if status_name:
            order_stmt = order_stmt.join(Order_Status, Order_Customer.status_id == Order_Status.id).where(Order_Status.name == status_name)
            count_inner = count_inner.join(Order_Status, Order_Customer.status_id == Order_Status.id).where(Order_Status.name == status_name)
        
        if start_date:
            order_stmt = order_stmt.where(Order_Customer.created_at >= start_date)
            count_inner = count_inner.where(Order_Customer.created_at >= start_date)
        if end_date:
            order_stmt = order_stmt.where(Order_Customer.created_at <= end_date)
            count_inner = count_inner.where(Order_Customer.created_at <= end_date)
        
        total_orders = (await db.execute(
            select(func.count()).select_from(count_inner.subquery())
        )).scalar()
        
        orders = (await db.execute(
            order_stmt.order_by(Order_Customer.created_at.desc()).offset(skip).limit(limit)
        )).unique().scalars().all()
    
    if include_services:
        mou_ids = (await db.execute(
            select(MOU.id).where(
                MOU.customer_id == customer_id,
                MOU.deleted_at.is_(None)
            )
        )).scalars().all()
        
        if mou_ids:
            svc_stmt = select(Order_Service).options(
                joinedload(Order_Service.mou),
                joinedload(Order_Service.status_service),
                joinedload(Order_Service.mou_device).joinedload(MOU_Device.serial_number).joinedload(Serial_Number.asset),
                joinedload(Order_Service.service_point).joinedload(Service_Point.user),
                joinedload(Order_Service.created_user),
                joinedload(Order_Service.activity_logs).joinedload(Service_Activity_Log.user),
            ).where(Order_Service.mou_id.in_(mou_ids))
            
            svc_count_inner = select(Order_Service.id).where(Order_Service.mou_id.in_(mou_ids))
            
            if start_date:
                svc_stmt = svc_stmt.where(Order_Service.created_at >= start_date)
                svc_count_inner = svc_count_inner.where(Order_Service.created_at >= start_date)
            if end_date:
                svc_stmt = svc_stmt.where(Order_Service.created_at <= end_date)
                svc_count_inner = svc_count_inner.where(Order_Service.created_at <= end_date)
            
            total_services = (await db.execute(
                select(func.count()).select_from(svc_count_inner.subquery())
            )).scalar()
            
            services = (await db.execute(
                svc_stmt.order_by(Order_Service.created_at.desc()).offset(skip).limit(limit)
            )).unique().scalars().all()
    
    payment_files = (await db.execute(
        select(Order_Payment_File)
        .join(Order_Customer, Order_Payment_File.order_id == Order_Customer.id)
        .where(Order_Customer.customer_id == customer_id)
        .order_by(Order_Payment_File.uploaded_at.desc())
    )).scalars().all()
    
    return CustomerLogResponse(
        orders=orders,
        services=services,
        payment=payment_files,
        total_orders=total_orders,
        total_services=total_services
    )


# Helper functions for export
def _normalize_customer_type(raw) -> str:
    if raw is None:
        return "N/A"
    return raw.value if hasattr(raw, "value") else str(raw)


def _export_region_name(
    *,
    region_name: str | None,
    customer_name: str,
    customer_type: str,
) -> str:
    """Region = name from customers.region_id; REGION type uses own customer name."""
    if region_name:
        return region_name
    if customer_type == "REGION":
        return customer_name
    return ""


def _unpack_export_customer_row(row) -> dict:
    customer_name = row[1] or ""
    customer_type = _normalize_customer_type(row[2])
    return {
        "customer_name": customer_name,
        "customer_type": customer_type,
        "customer_pic": row[3],
        "customer_pic_phone": row[4],
        "customer_phone": row[5],
        "sales_name": row[6] or "",
        "region_name": _export_region_name(
            region_name=row[7],
            customer_name=customer_name,
            customer_type=customer_type,
        ),
    }


@router.get("/my-log/export")
async def export_my_log(
    customer_id: UUID = Query(..., description="Customer ID to export log for"),
    status_name: Optional[str] = Query(None, description="Filter by order status"),
    include_orders: bool = Query(True, description="Include orders in export"),
    include_services: bool = Query(True, description="Include services in export"),
    start_date: OptionalNaiveDatetime = Query(None, description="Filter records after this date"),
    end_date: OptionalNaiveDatetime = Query(None, description="Filter records before this date"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Export customer order log to Excel.
    
    - **customer_id**: Customer ID to export (required)
    - **status_name**: Filter by order status (optional)
    - **include_orders**: Include orders in export (default: true)
    - **include_services**: Include services in export (default: true)
    - **start_date**: Filter records after this date (optional)
    - **end_date**: Filter records before this date (optional)
    """
    
    if end_date and end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    
    if not include_orders and not include_services:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimal salah satu dari 'include_orders' atau 'include_services' harus true"
        )
    
    excel_data = []
    RegionCustomer = aliased(Customer, name="region_customer")

    if include_orders:
        orders_stmt = select(
            Order_Customer,
            Customer.name.label("customer_name"),
            Customer.type.label("customer_type"),
            Customer.PIC.label("customer_pic"),
            Customer.pic_phone.label("customer_pic_phone"),
            Customer.phone.label("customer_phone"),
            User.name.label("sales_name"),
            RegionCustomer.name.label("region_name"),
        ).options(
            joinedload(Order_Customer.mou),
            joinedload(Order_Customer.status),
            joinedload(Order_Customer.order_details).joinedload(Order_Customer_Detail.mou_product).joinedload(MOU_Product.product),
        ).join(Customer, Order_Customer.customer_id == Customer.id
        ).outerjoin(User, Customer.sales_id == User.id
        ).outerjoin(RegionCustomer, Customer.region_id == RegionCustomer.id
        ).where(Order_Customer.customer_id == customer_id)
        
        if status_name:
            orders_stmt = orders_stmt.join(Order_Status, Order_Customer.status_id == Order_Status.id).where(Order_Status.name == status_name)
        
        if start_date:
            orders_stmt = orders_stmt.where(Order_Customer.created_at >= start_date)
        if end_date:
            orders_stmt = orders_stmt.where(Order_Customer.created_at <= end_date)
        
        order_rows = (await db.execute(
            orders_stmt.order_by(Order_Customer.created_at.desc())
        )).unique().all()
        
        for row in order_rows:
            order = row[0]
            fields = _unpack_export_customer_row(row)

            if not order.order_details:
                excel_data.append({
                    'Type': 'Order',
                    'Order Number': order.order_number,
                    'Date': order.order_date.strftime('%Y-%m-%d'),
                    'Completion Date': order.completed_at.strftime('%Y-%m-%d') if order.completed_at else '',
                    'Status': order.status.name if order.status else 'N/A',
                    'Region': fields["region_name"],
                    'Customer Name': fields["customer_name"],
                    'Customer Type': fields["customer_type"],
                    'Customer PIC': fields["customer_pic"] or '',
                    'Customer PIC Phone': fields["customer_pic_phone"] or '',
                    'Customer Phone': fields["customer_phone"] or '',
                    'Sales': fields["sales_name"],
                    'MOU Number': order.mou.no_mou if order.mou else 'N/A',
                    'Product/Device': 'N/A',
                    'Quantity': 0,
                    'Unit Price': 0,
                    'Subtotal': 0,
                    'Total': float(order.total),
                    'Description': 'No details available'
                })
            else:
                for detail in order.order_details:
                    excel_data.append({
                        'Type': 'Order',
                        'Order Number': order.order_number,
                        'Date': order.order_date.strftime('%Y-%m-%d'),
                        'Completion Date': order.completed_at.strftime('%Y-%m-%d') if order.completed_at else '',
                        'Status': order.status.name if order.status else 'N/A',
                        'Region': fields["region_name"],
                        'Customer Name': fields["customer_name"],
                        'Customer Type': fields["customer_type"],
                        'Customer PIC': fields["customer_pic"] or '',
                        'Customer PIC Phone': fields["customer_pic_phone"] or '',
                        'Customer Phone': fields["customer_phone"] or '',
                        'Sales': fields["sales_name"],
                        'MOU Number': order.mou.no_mou if order.mou else 'N/A',
                        'Product/Device': detail.mou_product.product.product_name,
                        'Quantity': detail.quantity,
                        'Unit Price': float(detail.price),
                        'Subtotal': float(detail.subtotal),
                        'Total': float(order.total),
                        'Description': f"Product from MOU {order.mou.no_mou}" if order.mou else 'N/A'
                    })
    
    if include_services:
        mou_ids = (await db.execute(
            select(MOU.id).where(
                MOU.customer_id == customer_id,
                MOU.deleted_at.is_(None)
            )
        )).scalars().all()
        
        if mou_ids:
            services_stmt = select(
                Order_Service,
                Customer.name.label("customer_name"),
                Customer.type.label("customer_type"),
                Customer.PIC.label("customer_pic"),
                Customer.pic_phone.label("customer_pic_phone"),
                Customer.phone.label("customer_phone"),
                User.name.label("sales_name"),
                RegionCustomer.name.label("region_name"),
            ).options(
                joinedload(Order_Service.mou),
                joinedload(Order_Service.status_service),
                joinedload(Order_Service.mou_device).joinedload(MOU_Device.serial_number).joinedload(Serial_Number.asset),
                joinedload(Order_Service.service_point).joinedload(Service_Point.user),
            ).join(MOU, Order_Service.mou_id == MOU.id
            ).join(Customer, MOU.customer_id == Customer.id
            ).outerjoin(User, Customer.sales_id == User.id
            ).outerjoin(RegionCustomer, Customer.region_id == RegionCustomer.id
            ).where(Order_Service.mou_id.in_(mou_ids))
            
            if start_date:
                services_stmt = services_stmt.where(Order_Service.created_at >= start_date)
            if end_date:
                services_stmt = services_stmt.where(Order_Service.created_at <= end_date)
            
            service_rows = (await db.execute(
                services_stmt.order_by(Order_Service.created_at.desc())
            )).unique().all()
            
            for row in service_rows:
                service = row[0]
                fields = _unpack_export_customer_row(row)

                device_info = "N/A"
                if service.mou_device and service.mou_device.serial_number:
                    device_info = f"{service.mou_device.serial_number.asset.asset_name} - {service.mou_device.serial_number.serial_code}"
                
                excel_data.append({
                    'Type': 'Service',
                    'Order Number': service.service_number,
                    'Date': service.created_at.strftime('%Y-%m-%d'),
                    'Completion Date': service.completed_at.strftime('%Y-%m-%d') if service.completed_at else '',
                    'Status': service.status_service.name if service.status_service else 'N/A',
                    'Region': fields["region_name"],
                    'Customer Name': fields["customer_name"],
                    'Customer Type': fields["customer_type"],
                    'Customer PIC': fields["customer_pic"] or '',
                    'Customer PIC Phone': fields["customer_pic_phone"] or '',
                    'Customer Phone': fields["customer_phone"] or '',
                    'Sales': fields["sales_name"],
                    'Service Point': service.service_point.name if service.service_point else 'N/A',
                    'MOU Number': service.mou.no_mou if service.mou else 'N/A',
                    'Product/Device': device_info,
                    'Quantity': 1,
                    'Unit Price': float(service.service_cost) if service.service_cost is not None else 0,
                    'Subtotal': float(service.service_cost) if service.service_cost is not None else 0,
                    'Total': float(service.service_cost) if service.service_cost is not None else 0,
                    'Description': service.description or 'Service request'
                })
    
    df = pd.DataFrame(excel_data)
    
    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date', ascending=False)
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    
    output = io.BytesIO()
    sheet_name = 'Customer Order Log'
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        worksheet = writer.sheets[sheet_name]
        
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    output.seek(0)
    
    date_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Get customer name for filename
    customer = (await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )).scalar_one_or_none()
    
    export_name = customer.name.replace(" ", "_") if customer else "unknown"
    
    filter_info = ""
    if start_date or end_date:
        if start_date and end_date:
            filter_info = f"_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}"
        elif start_date:
            filter_info = f"_from_{start_date.strftime('%Y%m%d')}"
        elif end_date:
            filter_info = f"_until_{end_date.strftime('%Y%m%d')}"
    
    type_filter = ""
    if not include_orders and include_services:
        type_filter = "_services_only"
    elif include_orders and not include_services:
        type_filter = "_orders_only"
    
    filename = f"customer_order_log_{export_name}{filter_info}{type_filter}_{date_suffix}.xlsx"
    
    temp_file_path = f"uploads/temp_{filename}"
    os.makedirs("uploads", exist_ok=True)
    
    with open(temp_file_path, "wb") as f:
        f.write(output.getvalue())
    
    return FileResponse(
        path=temp_file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=None
    )


@router.get("/{order_id}", response_model=OrderCustomerResponse)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific order details"""
    
    order = await fetch_order_customer(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order tidak ditemukan"
        )
    
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Hapus order customer beserta detail, activity log, dan file terkait.

    - Customer: order milik sendiri, status pending_payment / waiting_approval
    - Sales: order customer milik sales, status pending_payment / waiting_approval
    - Admin: semua order (permission order.delete)
    """
    order = await fetch_order_for_deletion(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order tidak ditemukan",
        )

    assert_can_delete_order(order, current_user)
    delete_order_files_from_disk(order.payment_files)

    await db.delete(order)
    await db.commit()
    return None


@router.get("/{order_id}/activity-log", response_model=ActivityLogListResponse)
async def get_order_activity_log(
    order_id: UUID,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of records to return"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get activity log for a specific order with pagination"""
    order = (await db.execute(
        select(Order_Customer).where(Order_Customer.id == order_id)
    )).scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order tidak ditemukan"
        )

    total = (await db.execute(
        select(func.count(Order_Activity_Log.id)).where(Order_Activity_Log.order_id == order_id)
    )).scalar()

    logs = (await db.execute(
        select(Order_Activity_Log).options(
            joinedload(Order_Activity_Log.user)
        ).where(
            Order_Activity_Log.order_id == order_id
        ).order_by(Order_Activity_Log.created_at.asc())
        .offset(skip).limit(limit)
    )).scalars().all()

    return ActivityLogListResponse(data=logs, total=total)


@router.post("/{order_id}/payment-proof", response_model=OrderPaymentFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_payment_proof(
    order_id: UUID,
    file: UploadFile = File(...),
    title: Optional[str] = Query(None, description="Title for the uploaded images"),
    description: Optional[str] = Query(None),
    current_user: User = Depends(require_permission(Permission.CREATE_ORDER)),
    db: AsyncSession = Depends(get_db)
):
    """Upload payment proof for an order (Customer and Sales)"""
    if current_user.customer_id:
        order = (await db.execute(
            select(Order_Customer).where(
                Order_Customer.id == order_id,
                Order_Customer.customer_id == current_user.customer_id
            )
        )).scalar_one_or_none()
    else:
        order = (await db.execute(
            select(Order_Customer).where(Order_Customer.id == order_id)
        )).scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order tidak ditemukan"
        )
    
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.pdf'}
    upload_dir = Path("uploads/payment_proofs")
    upload_dir.mkdir(parents=True, exist_ok=True)

    existing_payment_files = (await db.execute(
        select(Order_Payment_File).where(
            Order_Payment_File.order_id == order_id,
            (Order_Payment_File.description.is_(None)) |
            (~Order_Payment_File.description.like('RESI_PROOF%')) &
            (~Order_Payment_File.description.like('BAST_SIGNED%'))
        )
    )).scalars().all()

    for old_file in existing_payment_files:
        old_file_path = Path(old_file.file_path)
        if old_file_path.exists():
            old_file_path.unlink()
        await db.delete(old_file)

    await db.flush()
    
    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipe file tidak diizinkan untuk {file.filename}. Hanya jpg, jpeg, png, dan pdf yang diperbolehkan"
        )
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{order_id}_{timestamp}_{file.filename}"
    file_path = upload_dir / filename
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    display_filename = f"{title}{Path(file.filename).suffix}" if title else file.filename
    
    payment_file = Order_Payment_File(
        order_id=order_id,
        file_path=str(file_path),
        original_filename=display_filename,
        title=title,
        description=description,
        uploaded_by=current_user.id,
    )
    db.add(payment_file)
    db.add(Order_Activity_Log(
        order_id=order_id,
        status="payment_uploaded",
        description="Pembayaran telah dikirim, menunggu konfirmasi sales",
        created_by=current_user.id,
    ))

    await db.flush()
    await db.refresh(payment_file)
    await db.commit()

    return payment_file

@router.get("/{order_id}/payment-proofs", response_model=List[OrderPaymentFileResponse])
async def get_payment_proofs(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get payment proofs for an order"""
    if current_user.customer_id:
        order = (await db.execute(
            select(Order_Customer).where(
                Order_Customer.id == order_id,
                Order_Customer.customer_id == current_user.customer_id
            )
        )).scalar_one_or_none()
    elif current_user.role and current_user.role.scope in ["SALES", "ADMIN"]:
        order = (await db.execute(
            select(Order_Customer)
            .join(Customer, Order_Customer.customer_id == Customer.id)
            .where(
                Order_Customer.id == order_id,
                Customer.sales_id == current_user.id
            )
        )).scalar_one_or_none()
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak"
        )
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order tidak ditemukan"
        )
    
    payment_files = (await db.execute(
        select(Order_Payment_File).where(
            Order_Payment_File.order_id == order_id
        ).order_by(Order_Payment_File.uploaded_at.desc())
    )).scalars().all()
    
    return payment_files

@router.get("/payment-proofs/{file_id}/download")
async def download_payment_proof(
    file_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Download payment proof file"""
    payment_file = (await db.execute(
        select(Order_Payment_File).options(
            joinedload(Order_Payment_File.order_customer).joinedload(Order_Customer.customer)
        ).where(Order_Payment_File.id == file_id)
    )).scalar_one_or_none()
    
    if not payment_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File pembayaran tidak ditemukan"
        )
    
    if current_user.customer_id:
        if payment_file.order_customer.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak"
            )
    elif current_user.role and current_user.role.scope in ["SALES", "ADMIN"]:
        if current_user.role.scope != "ADMIN" and payment_file.order_customer.customer.sales_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak"
        )
    
    file_path = Path(payment_file.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File tidak ditemukan di server"
        )
    
    return FileResponse(
        path=str(file_path),
        filename=payment_file.original_filename,
        media_type='application/octet-stream'
    )


@router.put("/{order_id}/complete", response_model=OrderCustomerResponse)
async def complete_order(
    order_id: UUID,
    current_user: User = Depends(require_permission(Permission.CREATE_ORDER)),
    db: AsyncSession = Depends(get_db)
):
    """Complete order when customer receives items (Customer and Sales access)"""
    if current_user.customer_id:
        order = (await db.execute(
            select(Order_Customer).options(
                joinedload(Order_Customer.status)
            ).where(
                Order_Customer.id == order_id,
                Order_Customer.customer_id == current_user.customer_id
            )
        )).scalar_one_or_none()
    else:
        order = (await db.execute(
            select(Order_Customer).options(
                joinedload(Order_Customer.status)
            ).where(Order_Customer.id == order_id)
        )).scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order tidak ditemukan"
        )
    
    if order.status.name != "shipped":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hanya bisa menyelesaikan order dengan status dikirim (shipped)"
        )
    
    completed_status = await get_completed_status(db)
    order.status_id = completed_status.id
    order.completed_at = datetime.now()
    order.completed_by = current_user.id

    db.add(Order_Activity_Log(
        order_id=order_id,
        status="completed",
        description="Order sudah diterima oleh customer",
        created_by=current_user.id,
    ))
    await db.commit()
    order = await fetch_order_customer(db, order_id)
    return order

@router.get("/{order_id}/resi-proofs", response_model=List[OrderPaymentFileResponse])
async def get_resi_proofs(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get resi proofs for an order"""
    if current_user.customer_id:
        order = (await db.execute(
            select(Order_Customer).where(
                Order_Customer.id == order_id,
                Order_Customer.customer_id == current_user.customer_id
            )
        )).scalar_one_or_none()
    elif current_user.role and current_user.role.scope in ["SALES", "ADMIN"]:
        order = (await db.execute(
            select(Order_Customer)
            .join(Customer, Order_Customer.customer_id == Customer.id)
            .where(
                Order_Customer.id == order_id,
                Customer.sales_id == current_user.id
            )
        )).scalar_one_or_none()
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak"
        )
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order tidak ditemukan"
        )
    
    resi_files = (await db.execute(
        select(Order_Payment_File).where(
            Order_Payment_File.order_id == order_id,
            Order_Payment_File.description.like('RESI_PROOF%')
        ).order_by(Order_Payment_File.uploaded_at.desc())
    )).scalars().all()
    
    return resi_files


@router.get("/resi-proofs/{file_id}/download")
async def download_resi_proof(
    file_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Download resi proof file"""
    resi_file = (await db.execute(
        select(Order_Payment_File).options(
            joinedload(Order_Payment_File.order_customer).joinedload(Order_Customer.customer)
        ).where(
            Order_Payment_File.id == file_id,
            Order_Payment_File.description.like('RESI_PROOF%')
        )
    )).scalar_one_or_none()
    
    if not resi_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File bukti resi tidak ditemukan"
        )
    
    if current_user.customer_id:
        if resi_file.order_customer.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak"
            )
    elif current_user.role and current_user.role.scope in ["SALES", "ADMIN"]:
        if current_user.role.scope != "ADMIN" and resi_file.order_customer.customer.sales_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak"
        )
    
    file_path = Path(resi_file.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File tidak ditemukan di server"
        )
    
    return FileResponse(
        path=str(file_path),
        filename=resi_file.original_filename,
        media_type='application/octet-stream'
    )

@router.get("/{order_id}/invoice")
async def generate_invoice(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate a PDF invoice for a specific order"""
    order = await fetch_order_customer(db, order_id)
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order tidak ditemukan"
        )

    bank_accounts = (await db.execute(
        select(Bank_Account).where(
            Bank_Account.deleted_at.is_(None),
            Bank_Account.is_active.is_(True),
            Bank_Account.is_default.is_(True),
        ).order_by(Bank_Account.bank_name.asc())
    )).scalars().all()

    if not bank_accounts:
        bank_accounts = (await db.execute(
            select(Bank_Account).where(
                Bank_Account.deleted_at.is_(None),
                Bank_Account.is_active.is_(True),
            ).order_by(Bank_Account.bank_name.asc())
        )).scalars().all()
    
    buffer = build_invoice_pdf(order, bank_accounts=bank_accounts)
    filename = f"invoice_{order.order_number}_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.delete("/payment-proofs/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment_proof(
    file_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a payment proof file by ID"""
    payment_file = (await db.execute(
        select(Order_Payment_File).options(
            joinedload(Order_Payment_File.order_customer).joinedload(Order_Customer.customer)
        ).where(Order_Payment_File.id == file_id)
    )).scalar_one_or_none()
    
    if not payment_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File pembayaran tidak ditemukan"
        )
    
    if current_user.customer_id:
        if payment_file.order_customer.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak"
            )
    elif current_user.role and current_user.role.scope in ["SALES", "ADMIN"]:
        if current_user.role.scope != "ADMIN" and payment_file.order_customer.customer.sales_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak"
        )
    
    file_path = Path(payment_file.file_path)
    if file_path.exists():
        file_path.unlink()
    
    await db.delete(payment_file)
    await db.commit()
    
    return None


@router.delete("/order-files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order_file(
    file_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete any order file by ID (payment proof, resi proof, or BAST)
    
    Unified endpoint that replaces the separate delete endpoints for:
    - Payment proof files
    - Resi proof files  
    - BAST signed files
    
    Permission checks:
    - Customer: can only delete files from their own orders
    - Sales: can delete files from their customers' orders
    - Admin: can delete any file
    """
    order_file = (await db.execute(
        select(Order_Payment_File).options(
            joinedload(Order_Payment_File.order_customer).joinedload(Order_Customer.customer)
        ).where(Order_Payment_File.id == file_id)
    )).scalar_one_or_none()
    
    if not order_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File order tidak ditemukan"
        )
    
    if current_user.customer_id:
        if order_file.order_customer.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak" 
            )
    elif current_user.role and current_user.role.scope in ["SALES", "ADMIN"]:
        if current_user.role.scope != "ADMIN" and order_file.order_customer.customer.sales_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak"
        )
    
    file_path = Path(order_file.file_path)
    if file_path.exists():
        file_path.unlink()
    
    await db.delete(order_file)
    await db.commit()
    
    return None