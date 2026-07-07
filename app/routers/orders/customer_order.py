from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import joinedload
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import io
from app.dependencies import get_current_active_user, get_db
from app.utils.permissions import require_permission, Permission
from app.utils.db_queries import fetch_first
from app.utils.datetime_utils import OptionalNaiveDatetime
from app.routers.orders.helpers import order_customer_load_options, fetch_order_customer
from app.models import User, Customer
from app.models.order import Order_Customer, Order_Customer_Detail, Order_Cart, Order_Status, Order_Payment_File, Order_Service, Order_Activity_Log, Service_Activity_Log
from app.models.mou import MOU, MOU_Product, MOU_Device
from app.models.service_point import Service_Point
from app.models.serial_number import Serial_Number
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
            detail="User is not associated with any customer"
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


# Checkout - Convert cart to order
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
            detail="Cart is empty"
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
            detail="MOU not found or does not belong to your customer"
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


# Get customer's unified log (orders and services)
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


# Get specific order
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
            detail="Order not found"
        )
    
    return order


# Get activity log for an order
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
            detail="Order not found"
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


# Upload payment proof
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
            detail="Order not found"
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
            detail=f"File type not allowed for {file.filename}. Only jpg, jpeg, png, pdf are allowed"
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


# List payment proofs for an order
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
            detail="Access denied"
        )
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    payment_files = (await db.execute(
        select(Order_Payment_File).where(
            Order_Payment_File.order_id == order_id
        ).order_by(Order_Payment_File.uploaded_at.desc())
    )).scalars().all()
    
    return payment_files


# Download payment proof file
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
            detail="Payment file not found"
        )
    
    if current_user.customer_id:
        if payment_file.order_customer.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    elif current_user.role and current_user.role.scope in ["SALES", "ADMIN"]:
        if current_user.role.scope != "ADMIN" and payment_file.order_customer.customer.sales_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    file_path = Path(payment_file.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on server"
        )
    
    return FileResponse(
        path=str(file_path),
        filename=payment_file.original_filename,
        media_type='application/octet-stream'
    )


# Complete order (Customer and Sales)
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
            detail="Order not found"
        )
    
    if order.status.name != "shipped":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only complete shipped orders"
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


# Get resi proofs for an order
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
            detail="Access denied"
        )
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    resi_files = (await db.execute(
        select(Order_Payment_File).where(
            Order_Payment_File.order_id == order_id,
            Order_Payment_File.description.like('RESI_PROOF%')
        ).order_by(Order_Payment_File.uploaded_at.desc())
    )).scalars().all()
    
    return resi_files


# Download resi proof file
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
            detail="Resi proof file not found"
        )
    
    if current_user.customer_id:
        if resi_file.order_customer.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    elif current_user.role and current_user.role.scope in ["SALES", "ADMIN"]:
        if current_user.role.scope != "ADMIN" and resi_file.order_customer.customer.sales_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    file_path = Path(resi_file.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on server"
        )
    
    return FileResponse(
        path=str(file_path),
        filename=resi_file.original_filename,
        media_type='application/octet-stream'
    )


# Generate PDF Invoice
@router.get("/{order_id}/invoice")
async def generate_invoice(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate a PDF invoice for a specific order"""
    from app.utils.invoice import build_invoice_pdf
    
    order = await fetch_order_customer(db, order_id)
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    buffer = build_invoice_pdf(order)
    filename = f"invoice_{order.order_number}_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# Delete payment proof file
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
            detail="Payment file not found"
        )
    
    if current_user.customer_id:
        if payment_file.order_customer.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    elif current_user.role and current_user.role.scope in ["SALES", "ADMIN"]:
        if current_user.role.scope != "ADMIN" and payment_file.order_customer.customer.sales_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    file_path = Path(payment_file.file_path)
    if file_path.exists():
        file_path.unlink()
    
    await db.delete(payment_file)
    await db.commit()
    
    return None


# Delete any order file (payment proof, resi proof, or BAST)
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
            detail="Order file not found"
        )
    
    if current_user.customer_id:
        if order_file.order_customer.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied" 
            )
    elif current_user.role and current_user.role.scope in ["SALES", "ADMIN"]:
        if current_user.role.scope != "ADMIN" and order_file.order_customer.customer.sales_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    file_path = Path(order_file.file_path)
    if file_path.exists():
        file_path.unlink()
    
    await db.delete(order_file)
    await db.commit()
    
    return None
