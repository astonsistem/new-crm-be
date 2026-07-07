from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload, aliased
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import os
import pandas as pd
import io
from pathlib import Path
from app.dependencies import get_current_active_user, get_db
from app.utils.permissions import require_permission, Permission
from app.utils.db_queries import fetch_first
from app.utils.datetime_utils import NaiveDatetime, OptionalNaiveDatetime
from app.routers.orders.helpers import order_customer_load_options, fetch_order_customer
from app.models import User, Customer
from app.models.order import Order_Customer, Order_Customer_Detail, Order_Status, Order_Payment_File, Order_Activity_Log, Order_Service
from app.models.expedition import Expedition
from app.models.mou import MOU, MOU_Product, MOU_Device
from app.models.service_point import Service_Point
from app.models.serial_number import Serial_Number
from app.models.status import Status_Service
from app.schemas.orders.customer_order import (
    ConfirmPaymentRequest,
    OrderCustomerResponse,
    OrderPaymentFileResponse,
    SalesOrderLogItem,
    SalesOrderLogResponse,
    SalesPerformanceItem,
    AdminSalesOrderLogResponse
)
from pydantic import BaseModel

# Wrapper response models for pagination with total count
class OrderListResponse(BaseModel):
    data: List[OrderCustomerResponse]
    total: int

router = APIRouter(prefix="/orders/sales", tags=["Sales Orders"])


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


async def _get_or_create_order_status(db: AsyncSession, name: str, description: str) -> Order_Status:
    order_status = await fetch_first(
        db, select(Order_Status).where(Order_Status.name == name)
    )
    if not order_status:
        order_status = Order_Status(name=name, description=description)
        db.add(order_status)
        await db.flush()
    return order_status


async def get_paid_status(db: AsyncSession) -> Order_Status:
    return await _get_or_create_order_status(db, "paid", "Payment confirmed by sales")

async def get_waiting_approval_status(db: AsyncSession) -> Order_Status:
    return await _get_or_create_order_status(db, "waiting_approval", "Payment waiting for approval by sales")

async def get_shipped_status(db: AsyncSession) -> Order_Status:
    """Get the shipped status, create if not exists"""
    return await _get_or_create_order_status(db, "shipped", "Items shipped with resi proof")


# Get all orders (Admin & Sales)
@router.get("/all", response_model=OrderListResponse)
async def get_all_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search across order number, customer name"),
    status_name: Optional[str] = Query(None, description="Filter by status: pending_payment, paid, shipped, etc."),
    customer_id: Optional[UUID] = Query(None, description="Filter by customer ID"),
    sales_id: Optional[UUID] = Query(None, description="Filter by sales person ID"),
    start_date: OptionalNaiveDatetime = Query(None, description="Filter orders created after this date"),
    end_date: OptionalNaiveDatetime = Query(None, description="Filter orders created before this date"),
    current_user: User = Depends(require_permission(Permission.READ_ORDER)),
    db: AsyncSession = Depends(get_db)
):
    """Get all orders (accessible by Admin and Sales)"""
    
    if end_date and end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    
    stmt = select(Order_Customer).options(*order_customer_load_options())
    count_inner = select(Order_Customer.id)
    customer_joined = False
    
    if search:
        stmt = stmt.outerjoin(Customer, Order_Customer.customer_id == Customer.id).where(
            func.lower(Order_Customer.order_number).contains(search.lower()) |
            func.lower(Customer.name).contains(search.lower())
        )
        count_inner = count_inner.outerjoin(Customer, Order_Customer.customer_id == Customer.id).where(
            func.lower(Order_Customer.order_number).contains(search.lower()) |
            func.lower(Customer.name).contains(search.lower())
        )
        customer_joined = True
    
    if status_name:
        stmt = stmt.join(Order_Status, Order_Customer.status_id == Order_Status.id).where(Order_Status.name == status_name)
        count_inner = count_inner.join(Order_Status, Order_Customer.status_id == Order_Status.id).where(Order_Status.name == status_name)
    
    if customer_id:
        stmt = stmt.where(Order_Customer.customer_id == customer_id)
        count_inner = count_inner.where(Order_Customer.customer_id == customer_id)
    
    if sales_id:
        if not customer_joined:
            stmt = stmt.join(Customer, Order_Customer.customer_id == Customer.id)
            count_inner = count_inner.join(Customer, Order_Customer.customer_id == Customer.id)
            customer_joined = True
        stmt = stmt.where(Customer.sales_id == sales_id)
        count_inner = count_inner.where(Customer.sales_id == sales_id)
    
    if start_date:
        stmt = stmt.where(Order_Customer.created_at >= start_date)
        count_inner = count_inner.where(Order_Customer.created_at >= start_date)
    if end_date:
        stmt = stmt.where(Order_Customer.created_at <= end_date)
        count_inner = count_inner.where(Order_Customer.created_at <= end_date)
    
    total = (await db.execute(
        select(func.count()).select_from(count_inner.subquery())
    )).scalar()
    
    orders = (await db.execute(
        stmt.order_by(Order_Customer.created_at.desc()).offset(skip).limit(limit)
    )).unique().scalars().all()
    
    return OrderListResponse(data=orders, total=total)


# Sales endpoints - View all orders from their customers  
@router.get("/my-customers-orders", response_model=OrderListResponse)
async def get_my_customers_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    status_name: Optional[str] = Query(None, description="Filter by status: pending_payment, paid, etc."),
    current_user: User = Depends(require_permission(Permission.READ_SALES)),
    db: AsyncSession = Depends(get_db)
):
    """Get all orders from customers created by current sales user"""
    
    stmt = select(Order_Customer).options(*order_customer_load_options()).join(Customer, Order_Customer.customer_id == Customer.id).where(
        Customer.sales_id == current_user.id
    )
    
    count_inner = select(Order_Customer.id).join(
        Customer, Order_Customer.customer_id == Customer.id
    ).where(Customer.sales_id == current_user.id)
    
    if status_name:
        stmt = stmt.join(Order_Status, Order_Customer.status_id == Order_Status.id).where(Order_Status.name == status_name)
        count_inner = count_inner.join(Order_Status, Order_Customer.status_id == Order_Status.id).where(Order_Status.name == status_name)
    
    total = (await db.execute(
        select(func.count()).select_from(count_inner.subquery())
    )).scalar()
    
    orders = (await db.execute(
        stmt.order_by(Order_Customer.created_at.desc()).offset(skip).limit(limit)
    )).unique().scalars().all()
    
    return OrderListResponse(data=orders, total=total)


# Sales Order Log - View completed orders for current sales user
@router.get("/sales-order-log", response_model=SalesOrderLogResponse)
async def get_sales_order_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    customer_id: Optional[UUID] = Query(None, description="Filter orders by specific customer ID"),
    start_date: OptionalNaiveDatetime = Query(None, description="Filter orders completed after this date"),
    end_date: OptionalNaiveDatetime = Query(None, description="Filter orders completed before this date"),
    current_user: User = Depends(require_permission(Permission.READ_SALES)),
    db: AsyncSession = Depends(get_db)
):
    """Get completed orders log for current sales user"""
    
    if end_date and end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    
    base_conditions = [
        Customer.sales_id == current_user.id,
        Order_Customer.completed_at.isnot(None)
    ]
    if customer_id:
        base_conditions.append(Order_Customer.customer_id == customer_id)
    if start_date:
        base_conditions.append(Order_Customer.completed_at >= start_date)
    if end_date:
        base_conditions.append(Order_Customer.completed_at <= end_date)
    
    count_inner = select(Order_Customer.id).join(
        Customer, Order_Customer.customer_id == Customer.id
    ).where(*base_conditions)
    
    total_orders = (await db.execute(
        select(func.count()).select_from(count_inner.subquery())
    )).scalar()
    
    total_revenue = (await db.execute(
        select(func.sum(Order_Customer.total)).join(
            Customer, Order_Customer.customer_id == Customer.id
        ).where(*base_conditions)
    )).scalar() or 0
    
    rows_stmt = select(
        Order_Customer,
        Customer.name.label('customer_name'),
        Customer.type.label('customer_type'),
        Customer.PIC.label('customer_pic'),
        Customer.pic_phone.label('customer_pic_phone'),
        Customer.phone.label('customer_phone'),
    ).options(
        joinedload(Order_Customer.order_details).joinedload(Order_Customer_Detail.mou_product).joinedload(MOU_Product.product)
    ).join(Customer, Order_Customer.customer_id == Customer.id).where(*base_conditions)
    
    rows = (await db.execute(
        rows_stmt.order_by(Order_Customer.completed_at.desc()).offset(skip).limit(limit)
    )).unique().all()
    
    log_items = []
    for row in rows:
        order = row[0]
        customer_name = row[1]
        customer_type = row[2]
        customer_pic = row[3]
        customer_pic_phone = row[4]
        customer_phone = row[5]

        log_items.append(SalesOrderLogItem(
            id=order.id,
            order_number=order.order_number,
            order_date=order.order_date,
            completed_at=order.completed_at,
            total=order.total,
            customer_name=customer_name,
            customer_type=customer_type,
            customer_pic=customer_pic,
            customer_pic_phone=customer_pic_phone,
            customer_phone=customer_phone,
            order_details=order.order_details
        ))
    
    return SalesOrderLogResponse(
        data=log_items,
        total_orders=total_orders,
        total_revenue=total_revenue
    )


# Export Sales Order Log to Excel
@router.get("/order-log/export")
async def export_sales_order_log(
    sales_id: Optional[UUID] = Query(None, description="Filter by sales person ID"),
    customer_id: Optional[UUID] = Query(None, description="Filter orders by specific customer ID"),
    status_name: Optional[str] = Query(None, description="Filter by order status: pending_payment, paid, shipped, etc."),
    include_orders: bool = Query(True, description="Include orders in export"),
    include_services: bool = Query(True, description="Include services in export"),
    start_date: OptionalNaiveDatetime = Query(None, description="Filter records after this date"),
    end_date: OptionalNaiveDatetime = Query(None, description="Filter records before this date"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Export sales order log to Excel.
    Universal endpoint for both sales and customer users.
    
    - **sales_id**: Filter by sales person ID (optional)
    - **customer_id**: Filter by customer ID (optional)
    - **status_name**: Filter by order status (optional)
    - **include_orders**: Include orders in export (default: true)
    - **include_services**: Include services in export (default: true)
    """
    
    if end_date and end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    
    if not include_orders and not include_services:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of 'include_orders' or 'include_services' must be true"
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
        ).outerjoin(RegionCustomer, Customer.region_id == RegionCustomer.id)
        
        if sales_id:
            orders_stmt = orders_stmt.where(Customer.sales_id == sales_id)
        
        if customer_id:
            orders_stmt = orders_stmt.where(Order_Customer.customer_id == customer_id)
        
        if status_name:
            orders_stmt = orders_stmt.join(Order_Status, Order_Customer.status_id == Order_Status.id).where(Order_Status.name == status_name)
        
        if start_date:
            orders_stmt = orders_stmt.where(Order_Customer.created_at >= start_date)
        if end_date:
            orders_stmt = orders_stmt.where(Order_Customer.created_at <= end_date)
        
        order_rows = (await db.execute(
            orders_stmt.order_by(Order_Customer.completed_at.desc())
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
        customer_stmt = select(Customer.id).where(Customer.deleted_at.is_(None))
        if sales_id:
            customer_stmt = customer_stmt.where(Customer.sales_id == sales_id)
        if customer_id:
            customer_stmt = customer_stmt.where(Customer.id == customer_id)
        
        customer_ids = (await db.execute(customer_stmt)).scalars().all()
        
        if customer_ids:
            mou_ids = (await db.execute(
                select(MOU.id).where(
                    MOU.customer_id.in_(customer_ids),
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
                        'Completion Date': '',
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
    sheet_name = 'Sales Order Log'
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
    
    if sales_id:
        sales_user = (await db.execute(
            select(User).where(User.id == sales_id)
        )).scalar_one_or_none()
        export_name = sales_user.name.replace(" ", "_") if sales_user else "unknown"
    else:
        export_name = current_user.name.replace(" ", "_")
    
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
    
    filename = f"sales_order_log_{export_name}{filter_info}{type_filter}_{date_suffix}.xlsx"
    
    temp_file_path = f"uploads/temp_{filename}"
    os.makedirs("uploads", exist_ok=True)
    
    with open(temp_file_path, "wb") as f:
        f.write(output.getvalue())
    
    return FileResponse(
        path=temp_file_path,
        filename=filename,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# Admin Sales Performance Overview 
@router.get("/admin/sales-performance", response_model=AdminSalesOrderLogResponse)
async def get_sales_performance_overview(
    start_date: OptionalNaiveDatetime = Query(None, description="Filter orders completed after this date"),
    end_date: OptionalNaiveDatetime = Query(None, description="Filter orders completed before this date"),
    current_user: User = Depends(require_permission(Permission.READ_SALES)),
    db: AsyncSession = Depends(get_db)
):
    """Get sales performance overview across all sales users (Admin only)"""
    
    if end_date and end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    
    perf_stmt = select(
        User.id.label('sales_id'),
        User.name.label('sales_name'),
        User.username.label('sales_username'),
        func.count(Order_Customer.id).label('completed_orders'),
        func.coalesce(func.sum(Order_Customer.total), 0).label('total_revenue')
    ).select_from(User).join(
        Customer, User.id == Customer.sales_id
    ).join(
        Order_Customer, Customer.id == Order_Customer.customer_id
    ).where(Order_Customer.completed_at.isnot(None))
    
    if start_date:
        perf_stmt = perf_stmt.where(Order_Customer.completed_at >= start_date)
    if end_date:
        perf_stmt = perf_stmt.where(Order_Customer.completed_at <= end_date)
    
    perf_stmt = perf_stmt.group_by(
        User.id, User.name, User.username
    ).order_by(func.sum(Order_Customer.total).desc())
    
    sales_performance = (await db.execute(perf_stmt)).all()
    
    total_sales_users = len(sales_performance)
    overall_orders = sum(item.completed_orders for item in sales_performance)
    overall_revenue = sum(item.total_revenue for item in sales_performance)
    
    performance_items = [
        SalesPerformanceItem(
            sales_id=item.sales_id,
            sales_name=item.sales_name,
            sales_username=item.sales_username,
            completed_orders=item.completed_orders,
            total_revenue=item.total_revenue
        ) for item in sales_performance
    ]
    
    return AdminSalesOrderLogResponse(
        sales_performance=performance_items,
        total_sales_users=total_sales_users,
        overall_orders=overall_orders,
        overall_revenue=overall_revenue
    )

# Waiting approval payment (Customer and Sales)
@router.put("/{order_id}/waiting-approval-payment", response_model=OrderCustomerResponse)
async def waiting_approval_payment(
    order_id: UUID,
    current_user: User = Depends(require_permission(Permission.CREATE_ORDER)),
    db: AsyncSession = Depends(get_db)
):
    """Set order status to waiting approval payment (Customer and Sales access)."""
    if current_user.customer_id:
        order = (await db.execute(
            select(Order_Customer).where(
                Order_Customer.id == order_id,
                Order_Customer.customer_id == current_user.customer_id,
            )
        )).scalar_one_or_none()
    else:
        order = (await db.execute(
            select(Order_Customer).where(Order_Customer.id == order_id)
        )).scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    waiting_approval_status = await get_waiting_approval_status(db)

    order.status_id = waiting_approval_status.id

    db.add(Order_Activity_Log(
        order_id=order_id,
        status="waiting_approval_payment",
        description="Pembayaran menunggu persetujuan sales",
        created_by=current_user.id,
    ))
    await db.commit()
    
    order = await fetch_order_customer(db, order_id)
    
    return order

# Confirm payment (Customer and Sales)
@router.put("/{order_id}/confirm-payment", response_model=OrderCustomerResponse)
async def confirm_payment(
    order_id: UUID,
    confirm_data: ConfirmPaymentRequest,
    current_user: User = Depends(require_permission(Permission.CREATE_ORDER)),
    db: AsyncSession = Depends(get_db)
):
    """Confirm payment for an order (Customer and Sales access).

    Supports both regular payments and free/promotional orders.
    """
    if current_user.customer_id:
        order = (await db.execute(
            select(Order_Customer).where(
                Order_Customer.id == order_id,
                Order_Customer.customer_id == current_user.customer_id,
            )
        )).scalar_one_or_none()
    else:
        order = (await db.execute(
            select(Order_Customer).where(Order_Customer.id == order_id)
        )).scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    paid_status = await get_paid_status(db)

    order.status_id = paid_status.id
    order.payment_confirmed_at = datetime.now()
    order.payment_confirmed_by = current_user.id

    db.add(Order_Activity_Log(
        order_id=order_id,
        status="payment_confirmed",
        description="Pembayaran telah dikonfirmasi sales",
        created_by=current_user.id,
    ))
    await db.commit()
    
    order = await fetch_order_customer(db, order_id)
    
    return order


# Upload resi image (Sales only)
@router.post("/{order_id}/resi-proof", response_model=OrderPaymentFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_resi_proof(
    order_id: UUID,
    expedition_id: UUID = Form(..., description="ID of the expedition/shipping carrier"),
    no_resi: str = Form(..., description="Resi/tracking number"),
    shipping_date: NaiveDatetime = Form(..., description="Shipping date"),
    estimated_arrived: NaiveDatetime = Form(..., description="Estimated arrival date"),
    file: UploadFile = File(...),
    title: Optional[str] = Form(None, description="Title for the uploaded image"),
    description: Optional[str] = Form(None),
    current_user: User = Depends(require_permission(Permission.UPDATE_ORDER)),
    db: AsyncSession = Depends(get_db)
):
    """Upload resi (shipping receipt) proof for a paid order (Sales only)
    
    Requires selecting an expedition and providing an estimated delivery date.
    """
    
    order = (await db.execute(
        select(Order_Customer).options(
            joinedload(Order_Customer.status)
        ).join(Customer, Order_Customer.customer_id == Customer.id).where(
            Order_Customer.id == order_id,
            Customer.sales_id == current_user.id
        )
    )).scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found or not from your customers"
        )
    
    if order.status.name != "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only upload resi for paid orders"
        )
    
    expedition = (await db.execute(
        select(Expedition).where(
            Expedition.id == expedition_id,
            Expedition.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not expedition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expedition not found"
        )
    
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.pdf'}
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image files (jpg, jpeg, png) and PDF files are allowed"
        )
    
    upload_dir = Path("uploads/resi_proofs")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"resi_{order_id}_{timestamp}_{file.filename}"
    file_path = upload_dir / filename
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    display_filename = f"{title}{Path(file.filename).suffix}" if title else file.filename
    
    resi_file = Order_Payment_File(
        order_id=order_id,
        file_path=str(file_path),
        original_filename=display_filename,
        title=title,
        description=f"RESI_PROOF: {description}" if description else "RESI_PROOF",
        uploaded_by=current_user.id
    )
    
    db.add(resi_file)
    
    shipped_status = await get_shipped_status(db)
    order.status_id = shipped_status.id
    order.expedition_id = expedition_id
    order.no_resi = no_resi
    order.shipping_date = shipping_date
    order.estimated_arrived = estimated_arrived
    order.shipping_confirmed_at = datetime.now()
    order.shipping_confirmed_by = current_user.id
    
    activity_log = Order_Activity_Log(
        order_id=order_id,
        status="shipped",
        description=f"Order telah dikirim via {expedition.name}, Resi: {no_resi}",
        created_by=current_user.id
    )
    db.add(activity_log)
    
    await db.commit()
    await db.refresh(resi_file)
    
    return resi_file
