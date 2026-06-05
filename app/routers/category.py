from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List, Optional
from uuid import UUID
from app.dependencies import get_current_active_user, get_db
from app.models import User, Category
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("/", response_model=List[CategoryResponse])
async def get_categories(
    skip: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search categories by name or description (partial, case-insensitive)"),
    limit: int = Query(100, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all categories with pagination
    """
    stmt = select(Category)

    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(Category.name.ilike(search_pattern))

    categories = (await db.execute(stmt.offset(skip).limit(limit))).scalars().all()

    return categories


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category_by_id(
    category_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a category by ID
    """
    category = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with id {category_id} not found"
        )

    return category


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category: CategoryCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new category
    """
    existing_category = (await db.execute(select(Category).where(Category.name == category.name))).scalar_one_or_none()
    if existing_category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category with name '{category.name}' already exists"
        )

    db_category = Category(**category.model_dump())
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)

    return db_category


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    category: CategoryUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a category
    """
    db_category = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()

    if not db_category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with id {category_id} not found"
        )

    if category.name and category.name != db_category.name:
        existing_category = (await db.execute(select(Category).where(Category.name == category.name))).scalar_one_or_none()
        if existing_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category with name '{category.name}' already exists"
            )

    update_data = category.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_category, key, value)

    await db.commit()
    await db.refresh(db_category)

    return db_category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a category
    """
    db_category = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()

    if not db_category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with id {category_id} not found"
        )

    await db.delete(db_category)
    await db.commit()

    return None
