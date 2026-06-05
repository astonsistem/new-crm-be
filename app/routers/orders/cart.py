from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID
from app.dependencies import get_current_active_user, get_db
from app.models import User, Order_Cart, Product, Category
from app.models.mou import MOU_Product, MOU
from app.schemas.orders.cart import (
    CartItemCreate, 
    CartItemUpdate, 
    CartItemResponse, 
    CartSummary,
    ProductDetail
)
from decimal import Decimal

router = APIRouter(prefix="/cart", tags=["Shopping Cart"])


@router.get("/", response_model=List[CartItemResponse])
async def get_cart(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all items in current user's cart
    
    - Requires customer user (users with customer_id)
    """
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customer users can have a shopping cart"
        )
    
    result = await db.execute(
        select(Order_Cart)
        .options(
            selectinload(Order_Cart.mou_product)
            .selectinload(MOU_Product.product)
            .selectinload(Product.category)
        )
        .where(Order_Cart.customer_id == current_user.customer_id)
    )
    cart_items = result.scalars().all()
    
    response = []
    for item in cart_items:
        mou_product = item.mou_product
        product = mou_product.product
        category = product.category
        
        product_detail = ProductDetail(
            product_id=product.id,
            product_name=product.product_name,
            category_name=category.name,
            contract_price=mou_product.contract_price
        )
        
        subtotal = item.quantity * mou_product.contract_price
        
        response.append(CartItemResponse(
            id=item.id,
            customer_id=item.customer_id,
            mou_product_id=item.mou_product_id,
            quantity=item.quantity,
            added_at=item.added_at,
            product=product_detail,
            subtotal=subtotal
        ))
    
    return response


@router.get("/summary", response_model=CartSummary)
async def get_cart_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get cart summary with total items and total amount
    """
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customer users can have a shopping cart"
        )
    
    result = await db.execute(
        select(Order_Cart)
        .options(
            selectinload(Order_Cart.mou_product)
            .selectinload(MOU_Product.product)
            .selectinload(Product.category)
        )
        .where(Order_Cart.customer_id == current_user.customer_id)
    )
    cart_items = result.scalars().all()
    
    total_items = 0
    total_amount = Decimal('0')
    items_response = []
    
    for item in cart_items:
        mou_product = item.mou_product
        product = mou_product.product
        category = product.category
        
        product_detail = ProductDetail(
            product_id=product.id,
            product_name=product.product_name,
            category_name=category.name,
            contract_price=mou_product.contract_price
        )
        
        subtotal = item.quantity * mou_product.contract_price
        total_items += item.quantity
        total_amount += subtotal
        
        items_response.append(CartItemResponse(
            id=item.id,
            customer_id=item.customer_id,
            mou_product_id=item.mou_product_id,
            quantity=item.quantity,
            added_at=item.added_at,
            product=product_detail,
            subtotal=subtotal
        ))
    
    return CartSummary(
        total_items=total_items,
        total_amount=total_amount,
        items=items_response
    )


@router.post("/", response_model=CartItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_cart(
    cart_item: CartItemCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add item to cart or update quantity if already exists
    
    - If item already in cart, adds to existing quantity
    - **mou_product_id**: Product from customer's MOU
    - **quantity**: Number of items to add
    """
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customer users can add items to cart"
        )
    
    mou_product = (await db.execute(
        select(MOU_Product).where(
            MOU_Product.id == cart_item.mou_product_id,
            MOU_Product.active == True
        )
    )).scalar_one_or_none()
    
    if not mou_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found or not active"
        )
    
    mou = (await db.execute(
        select(MOU).where(
            MOU.id == mou_product.mou_id,
            MOU.customer_id == current_user.customer_id
        )
    )).scalar_one_or_none()
    
    if not mou:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This product is not available in your contract"
        )
    
    existing_item = (await db.execute(
        select(Order_Cart).where(
            Order_Cart.customer_id == current_user.customer_id,
            Order_Cart.mou_product_id == cart_item.mou_product_id
        )
    )).scalar_one_or_none()
    
    if existing_item:
        existing_item.quantity += cart_item.quantity
        await db.flush()
        cart_db = existing_item
    else:
        new_cart_item = Order_Cart(
            customer_id=current_user.customer_id,
            mou_product_id=cart_item.mou_product_id,
            quantity=cart_item.quantity,
        )
        db.add(new_cart_item)
        await db.flush()
        cart_db = new_cart_item

    cart_id = cart_db.id
    await db.commit()

    cart_db = (await db.execute(
        select(Order_Cart)
        .options(
            selectinload(Order_Cart.mou_product)
            .selectinload(MOU_Product.product)
            .selectinload(Product.category)
        )
        .where(Order_Cart.id == cart_id)
    )).scalar_one()

    mou_product = cart_db.mou_product
    product = mou_product.product
    category = product.category
    
    product_detail = ProductDetail(
        product_id=product.id,
        product_name=product.product_name,
        category_name=category.name,
        contract_price=mou_product.contract_price
    )
    
    subtotal = cart_db.quantity * mou_product.contract_price

    return CartItemResponse(
        id=cart_db.id,
        customer_id=cart_db.customer_id,
        mou_product_id=cart_db.mou_product_id,
        quantity=cart_db.quantity,
        added_at=cart_db.added_at,
        product=product_detail,
        subtotal=subtotal
    )


@router.put("/{cart_item_id}", response_model=CartItemResponse)
async def update_cart_item(
    cart_item_id: UUID,
    cart_update: CartItemUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update cart item quantity
    
    - Only the owner can update their cart items
    """
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customer users can update cart"
        )
    
    cart_item = (await db.execute(
        select(Order_Cart).where(
            Order_Cart.id == cart_item_id,
            Order_Cart.customer_id == current_user.customer_id
        )
    )).scalar_one_or_none()
    
    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found"
        )
    
    cart_item.quantity = cart_update.quantity
    await db.commit()
    
    cart_item_loaded = (await db.execute(
        select(Order_Cart)
        .options(
            selectinload(Order_Cart.mou_product)
            .selectinload(MOU_Product.product)
            .selectinload(Product.category)
        )
        .where(Order_Cart.id == cart_item_id)
    )).scalar_one_or_none()
    
    mou_product = cart_item_loaded.mou_product
    product = mou_product.product
    category = product.category
    
    product_detail = ProductDetail(
        product_id=product.id,
        product_name=product.product_name,
        category_name=category.name,
        contract_price=mou_product.contract_price
    )
    
    subtotal = cart_item_loaded.quantity * mou_product.contract_price
    
    return CartItemResponse(
        id=cart_item_loaded.id,
        customer_id=cart_item_loaded.customer_id,
        mou_product_id=cart_item_loaded.mou_product_id,
        quantity=cart_item_loaded.quantity,
        added_at=cart_item_loaded.added_at,
        product=product_detail,
        subtotal=subtotal
    )


@router.delete("/{cart_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_cart(
    cart_item_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove item from cart
    """
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customer users can remove items from cart"
        )
    
    cart_item = (await db.execute(
        select(Order_Cart).where(
            Order_Cart.id == cart_item_id,
            Order_Cart.customer_id == current_user.customer_id
        )
    )).scalar_one_or_none()
    
    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found"
        )
    
    await db.delete(cart_item)
    await db.commit()
    
    return None


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Clear all items from cart
    """
    if not current_user.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customer users can clear cart"
        )
    
    await db.execute(
        delete(Order_Cart).where(Order_Cart.customer_id == current_user.customer_id)
    )
    await db.commit()
    
    return None
