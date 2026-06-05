from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
import os
import shutil
from pathlib import Path
from app.dependencies import get_db
from app.models import User, Product, Category
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse
from app.utils.permissions import require_permission, Permission
from pydantic import BaseModel


class ProductListResponse(BaseModel):
    data: List[ProductResponse]
    total: int


router = APIRouter(prefix="/products", tags=["Products"])

UPLOAD_DIR = Path("uploads/product_images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _product_opts():
    return [selectinload(Product.category)]


@router.get("/", response_model=ProductListResponse)
async def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    category_id: Optional[UUID] = None,
    name: Optional[str] = Query(None, description="Filter by product name (partial, case-insensitive)"),
    current_user: User = Depends(require_permission(Permission.READ_PRODUCT)),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Product).options(*_product_opts())

    if category_id:
        stmt = stmt.where(Product.category_id == category_id)

    if name:
        stmt = stmt.where(Product.product_name.ilike(f"%{name}%"))

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar()

    products = (await db.execute(stmt.offset(skip).limit(limit))).scalars().all()

    result = []
    for product in products:
        result.append(ProductResponse(
            id=product.id,
            product_name=product.product_name,
            category_id=product.category_id,
            default_price=product.default_price,
            unit=product.unit,
            image=product.image,
            category_name=product.category.name if product.category else None,
        ))

    return ProductListResponse(data=result, total=total)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product_by_id(
    product_id: UUID,
    current_user: User = Depends(require_permission(Permission.READ_PRODUCT)),
    db: AsyncSession = Depends(get_db)
):
    product = (await db.execute(
        select(Product).options(*_product_opts()).where(Product.id == product_id)
    )).scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )

    return ProductResponse(
        id=product.id,
        product_name=product.product_name,
        category_id=product.category_id,
        default_price=product.default_price,
        unit=product.unit,
        image=product.image,
        category_name=product.category.name if product.category else None,
    )


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product: ProductCreate,
    current_user: User = Depends(require_permission(Permission.CREATE_PRODUCT)),
    db: AsyncSession = Depends(get_db)
):
    category = (await db.execute(
        select(Category).where(Category.id == product.category_id)
    )).scalar_one_or_none()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with id {product.category_id} not found"
        )

    db_product = Product(**product.model_dump())
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)

    return ProductResponse(
        id=db_product.id,
        product_name=db_product.product_name,
        category_id=db_product.category_id,
        default_price=db_product.default_price,
        unit=db_product.unit,
        image=db_product.image,
        category_name=category.name,  # use already-fetched category, no lazy load
    )


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    product: ProductUpdate,
    current_user: User = Depends(require_permission(Permission.UPDATE_PRODUCT)),
    db: AsyncSession = Depends(get_db)
):
    db_product = (await db.execute(
        select(Product).where(Product.id == product_id)
    )).scalar_one_or_none()

    if not db_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )

    if product.category_id:
        category = (await db.execute(
            select(Category).where(Category.id == product.category_id)
        )).scalar_one_or_none()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with id {product.category_id} not found"
            )

    update_data = product.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_product, key, value)

    await db.commit()

    # Re-query with eager loading
    db_product = (await db.execute(
        select(Product).options(*_product_opts()).where(Product.id == product_id)
    )).scalar_one()

    return ProductResponse(
        id=db_product.id,
        product_name=db_product.product_name,
        category_id=db_product.category_id,
        default_price=db_product.default_price,
        unit=db_product.unit,
        image=db_product.image,
        category_name=db_product.category.name if db_product.category else None,
    )


@router.post("/{product_id}/upload-image", response_model=ProductResponse)
async def upload_product_image(
    product_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission(Permission.UPDATE_PRODUCT)),
    db: AsyncSession = Depends(get_db)
):
    allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
        )

    db_product = (await db.execute(
        select(Product).where(Product.id == product_id)
    )).scalar_one_or_none()
    if not db_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )

    if db_product.image:
        for ext in allowed_extensions:
            old_image_path = UPLOAD_DIR / f"{db_product.image}{ext}"
            if old_image_path.exists():
                old_image_path.unlink()
                break

    file_name = f"{product_id}{file_ext}"
    file_path = UPLOAD_DIR / file_name

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )

    db_product.image = str(product_id)
    await db.commit()

    # Re-query with eager loading
    db_product = (await db.execute(
        select(Product).options(*_product_opts()).where(Product.id == product_id)
    )).scalar_one()

    return ProductResponse(
        id=db_product.id,
        product_name=db_product.product_name,
        category_id=db_product.category_id,
        default_price=db_product.default_price,
        unit=db_product.unit,
        image=db_product.image,
        category_name=db_product.category.name if db_product.category else None,
    )


@router.get("/{product_id}/image")
async def get_product_image(
    product_id: UUID,
    current_user: User = Depends(require_permission(Permission.READ_PRODUCT)),
    db: AsyncSession = Depends(get_db)
):
    db_product = (await db.execute(
        select(Product).where(Product.id == product_id)
    )).scalar_one_or_none()
    if not db_product or not db_product.image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product image not found"
        )

    allowed_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
    image_path = None

    for ext in allowed_extensions:
        potential_path = UPLOAD_DIR / f"{product_id}{ext}"
        if potential_path.exists():
            image_path = potential_path
            break

    if not image_path or not image_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found on server"
        )

    return FileResponse(
        path=image_path,
        media_type=f"image/{image_path.suffix[1:]}",
        filename=f"product_{product_id}{image_path.suffix}"
    )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    current_user: User = Depends(require_permission(Permission.DELETE_PRODUCT)),
    db: AsyncSession = Depends(get_db)
):
    db_product = (await db.execute(
        select(Product).where(Product.id == product_id)
    )).scalar_one_or_none()

    if not db_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )

    await db.delete(db_product)
    await db.commit()

    return None
