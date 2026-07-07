from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pathlib import Path
from app.dependencies import get_current_active_user, get_db
from app.utils.permissions import require_permission, Permission
from app.utils.bast import build_bast_pdf
from app.routers.orders.helpers import fetch_order_customer
from app.models import User
from app.models.order import Order_Customer, Order_Payment_File, Order_Activity_Log
from app.models.mou import MOU_Device
from app.models.serial_number import Serial_Number
from app.schemas.orders.customer_order import OrderPaymentFileResponse

router = APIRouter(prefix="/bast", tags=["BAST (Berita Acara Serah Terima)"])


def get_user_customer_id(current_user: User) -> UUID:
    """Get customer ID for the current user, raise error if not found"""
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with any customer"
        )
    return current_user.customer_id


# Generate BAST PDF (Berita Acara Serah Terima)
@router.get("/{order_id}/generate")
async def generate_bast(
    order_id: UUID,
    current_user: User = Depends(require_permission(Permission.READ_ORDER)),
    db: AsyncSession = Depends(get_db)
):
    """Generate a BAST (Berita Acara Serah Terima) PDF for a specific order"""

    order = await fetch_order_customer(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    mou_devices = (await db.execute(
        select(MOU_Device)
        .options(
            joinedload(MOU_Device.serial_number).joinedload(Serial_Number.asset),
        )
        .where(MOU_Device.mou_id == order.mou_id)
        .order_by(MOU_Device.id)
    )).scalars().all()

    buffer = build_bast_pdf(order, mou_devices)
    filename = f"BAST_{order.order_number}_{datetime.now().strftime('%Y%m%d')}.pdf"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# Upload signed BAST
@router.post("/{order_id}/upload", response_model=OrderPaymentFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_signed_bast(
    order_id: UUID,
    file: UploadFile = File(...),
    title: Optional[str] = Query(None, description="Title for the uploaded image"),
    description: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload signed BAST for an order (Customer only)"""
    customer_id = get_user_customer_id(current_user)
    
    order = (await db.execute(
        select(Order_Customer).where(
            Order_Customer.id == order_id,
            Order_Customer.customer_id == customer_id
        )
    )).scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    allowed_extensions = {'.pdf', '.PDF', '.jpg', '.jpeg', '.png'}
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and image files are allowed for BAST uploads"
        )
    
    upload_dir = Path("uploads/bast_signed")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"BAST_SIGNED_{order.order_number}_{timestamp}_{file.filename}"
    file_path = upload_dir / filename
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    display_filename = f"{title}{Path(file.filename).suffix}" if title else file.filename
    
    bast_description = f"BAST_SIGNED: {description if description else 'Signed BAST document'}"
    bast_file = Order_Payment_File(
        order_id=order_id,
        file_path=str(file_path),
        original_filename=display_filename,
        title=title,
        description=bast_description,
        uploaded_by=current_user.id
    )
    
    db.add(bast_file)
    db.add(Order_Activity_Log(
        order_id=order_id,
        status="bast_uploaded",
        description="BAST yang telah ditandatangani telah diunggah oleh customer",
        created_by=current_user.id,
    ))
    await db.flush()
    await db.refresh(bast_file)
    await db.commit()

    return bast_file


# Get BAST files for an order
@router.get("/{order_id}/files", response_model=List[OrderPaymentFileResponse])
async def get_bast_files(
    order_id: UUID,
    current_user: User = Depends(require_permission(Permission.READ_ORDER)),
    db: AsyncSession = Depends(get_db)
):
    """Get BAST files for an order"""
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
    
    bast_files = (await db.execute(
        select(Order_Payment_File).where(
            Order_Payment_File.order_id == order_id,
            Order_Payment_File.description.like('BAST_SIGNED%')
        ).order_by(Order_Payment_File.uploaded_at.desc())
    )).scalars().all()
    
    return bast_files


# Get all BAST files for a customer
@router.get("/customer/{customer_id}/files", response_model=List[OrderPaymentFileResponse])
async def get_customer_bast_files(
    customer_id: UUID,
    current_user: User = Depends(require_permission(Permission.READ_ORDER)),
    db: AsyncSession = Depends(get_db)
):
    """Get all BAST files for a customer across all their orders"""
    if current_user.customer_id:
        if current_user.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    
    bast_files = (await db.execute(
        select(Order_Payment_File)
        .join(Order_Customer, Order_Payment_File.order_id == Order_Customer.id)
        .where(
            Order_Customer.customer_id == customer_id,
            Order_Payment_File.description.like('BAST_SIGNED%')
        ).order_by(Order_Payment_File.uploaded_at.desc())
    )).scalars().all()
    
    return bast_files


# Download BAST file
@router.get("/{order_id}/download")
async def download_bast_file(
    order_id: UUID,
    current_user: User = Depends(require_permission(Permission.READ_ORDER)),
    db: AsyncSession = Depends(get_db)
):
    """Download BAST file for an order"""
    if current_user.customer_id:
        order = (await db.execute(
            select(Order_Customer).where(
                Order_Customer.id == order_id,
                Order_Customer.customer_id == current_user.customer_id
            )
        )).scalar_one_or_none()
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
    else:
        order = (await db.execute(
            select(Order_Customer).where(Order_Customer.id == order_id)
        )).scalar_one_or_none()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
    
    bast_file = (await db.execute(
        select(Order_Payment_File).where(
            Order_Payment_File.order_id == order_id,
            Order_Payment_File.description.like('BAST_SIGNED%')
        ).order_by(Order_Payment_File.uploaded_at.desc())
    )).scalars().first()
    
    if not bast_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BAST file not found for this order"
        )
    
    file_path = Path(bast_file.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on server"
        )
    
    return FileResponse(
        path=str(file_path),
        filename=bast_file.original_filename,
        media_type='application/octet-stream'
    )
