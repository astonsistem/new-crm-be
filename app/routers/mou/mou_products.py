from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.mou import MOU, MOU_Product
from app.models.product import Product
from app.models.order import Order_Customer, Order_Customer_Detail, Order_Cart, Order_Status
from app.schemas.mou import MOUProductCreate, MOUProductUpdate, MOUProductResponse
from app.utils.eager_loads import mou_product_load_options
from pydantic import BaseModel

# Wrapper response models for pagination with total count
class MOUProductListResponse(BaseModel):
    data: List[MOUProductResponse]
    total: int
    
router = APIRouter(prefix="/mou-products", tags=["MOU PRODUCTS"])


# Get all MOU products with pagination and optional filters
@router.get("/", response_model=MOUProductListResponse)
async def get_all_mou_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    mou_id: Optional[UUID] = Query(None, description="Filter by MOU ID"),
    active_only: bool = Query(True, description="Show only active products"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all MOU products with optional filtering

    - **mou_id**: Filter by specific MOU (optional)
    - **active_only**: Show only active products (default: true)
    """
    conditions = [MOU_Product.deleted_at.is_(None)]
    if mou_id:
        conditions.append(MOU_Product.mou_id == mou_id)
    if active_only:
        conditions.append(MOU_Product.active == True)

    total = (await db.execute(
        select(func.count(MOU_Product.id)).where(*conditions)
    )).scalar()

    products = (await db.execute(
        select(MOU_Product).options(*mou_product_load_options()).where(*conditions).offset(skip).limit(limit)
    )).scalars().all()

    result = []
    for product in products:
        item = MOUProductResponse.model_validate(product)
        if product.mou and product.mou.customer:
            item.customer_id = product.mou.customer_id
            item.customer_name = product.mou.customer.name
            item.customer_pic = product.mou.customer.PIC
            item.customer_pic_phone = product.mou.customer.pic_phone
            item.customer_phone = product.mou.customer.phone
        result.append(item)

    return MOUProductListResponse(data=result, total=total)


# List all products for a specific MOU
@router.get("/{mou_id}", response_model=MOUProductListResponse)
async def get_mou_products(
    mou_id: UUID,
    active_only: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all products for a specific MOU
    
    - **mou_id**: MOU ID (required)
    - **active_only**: Show only active products (default: true)
    """
    mou = (await db.execute(
        select(MOU).where(MOU.id == mou_id)
    )).scalar_one_or_none()
    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU not found"
        )

    conditions = [
        MOU_Product.mou_id == mou_id,
        MOU_Product.deleted_at.is_(None)
    ]
    if active_only:
        conditions.append(MOU_Product.active == True)

    total = (await db.execute(
        select(func.count(MOU_Product.id)).where(*conditions)
    )).scalar()

    products = (await db.execute(
        select(MOU_Product).options(*mou_product_load_options()).where(*conditions)
    )).scalars().unique().all()

    result = []
    for product in products:
        item = MOUProductResponse.model_validate(product)
        if product.mou and product.mou.customer:
            item.customer_id = product.mou.customer_id
            item.customer_name = product.mou.customer.name
            item.customer_pic = product.mou.customer.PIC
            item.customer_pic_phone = product.mou.customer.pic_phone
            item.customer_phone = product.mou.customer.phone
        result.append(item)

    return MOUProductListResponse(data=result, total=total)


# Get MOU product by ID
@router.get("/{product_id}", response_model=MOUProductResponse)
async def get_mou_product(
    product_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific MOU product by ID
    """
    mou_product = (await db.execute(
        select(MOU_Product).options(*mou_product_load_options()).where(
            MOU_Product.id == product_id,
            MOU_Product.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not mou_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU product not found"
        )

    return mou_product


# Add product to MOU
@router.post("/{mou_id}", response_model=MOUProductResponse, status_code=status.HTTP_201_CREATED)
async def add_product_to_mou(
    mou_id: UUID,
    product_data: MOUProductCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a product to an MOU
    
    - **mou_id**: MOU ID in URL (will override mou_id in body)
    - **product_id**: Product ID (required)
    - **contract_price**: Contract price (required)
    - **active**: Product active status (default: true)
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

    product = (await db.execute(
        select(Product).where(Product.id == product_data.product_id)
    )).scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    existing = (await db.execute(
        select(MOU_Product).where(
            MOU_Product.mou_id == mou_id,
            MOU_Product.product_id == product_data.product_id
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product already added to this MOU"
        )

    new_mou_product = MOU_Product(
        mou_id=mou_id,
        product_id=product_data.product_id,
        contract_price=product_data.contract_price,
        active=product_data.active
    )

    db.add(new_mou_product)
    await db.commit()

    # Re-query with eager loading — db.refresh() strips loaded relationships
    new_mou_product = (await db.execute(
        select(MOU_Product).options(*mou_product_load_options()).where(MOU_Product.id == new_mou_product.id)
    )).scalar_one()

    return new_mou_product


# Update MOU product
@router.put("/{mou_product_id}", response_model=MOUProductResponse)
async def update_mou_product(
    mou_product_id: UUID,
    product_data: MOUProductUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    mou_product = (await db.execute(
        select(MOU_Product).where(MOU_Product.id == mou_product_id)
    )).scalar_one_or_none()

    if not mou_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU product not found"
        )

    update_data = product_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(mou_product, field, value)

    await db.commit()

    # Re-query with eager loading — db.refresh() strips loaded relationships
    mou_product = (await db.execute(
        select(MOU_Product).options(*mou_product_load_options()).where(MOU_Product.id == mou_product_id)
    )).scalar_one()

    return mou_product


# Delete MOU product (soft delete)
@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mou_product(
    product_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Soft delete an MOU product
    
    - Cannot delete if product is used in active (non-completed) orders or shopping carts
    """
    mou_product = (await db.execute(
        select(MOU_Product).where(
            MOU_Product.id == product_id,
            MOU_Product.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not mou_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU product not found"
        )

    active_order_count = (await db.execute(
        select(func.count()).select_from(
            select(Order_Customer_Detail.id)
            .join(Order_Customer, Order_Customer_Detail.order_id == Order_Customer.id)
            .join(Order_Status, Order_Customer.status_id == Order_Status.id)
            .where(
                Order_Customer_Detail.mou_product_id == product_id,
                Order_Status.name != "completed"
            )
            .subquery()
        )
    )).scalar()

    if active_order_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete MOU product. It is used in {active_order_count} active (non-completed) order(s). Only products in completed orders can be deleted."
        )

    cart_count = (await db.execute(
        select(func.count(Order_Cart.id)).where(Order_Cart.mou_product_id == product_id)
    )).scalar()

    if cart_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete MOU product. It is currently in {cart_count} shopping cart(s). Please remove it from all carts before deletion or set it to inactive instead."
        )

    mou_product.deleted_at = datetime.now()
    mou_product.active = False
    await db.commit()

    return None
