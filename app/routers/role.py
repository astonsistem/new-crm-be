from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Text, or_
from typing import List, Optional
from uuid import UUID

from app.dependencies import get_current_active_user, get_db
from app.models import User, Role
from app.schemas.role import RoleCreate, RoleResponse, RoleUpdate
from pydantic import BaseModel

# Wrapper response models for pagination with total count
class RoleListResponse(BaseModel):
    data: List[RoleResponse]
    total: int

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("/", response_model=RoleListResponse)
async def get_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    name: Optional[str] = Query(None, description="Search across role name, description, and scope (partial, case-insensitive)"),
    scope: Optional[str] = Query(None, description="Filter by role scope (ADMIN, SALES, CUSTOMER)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of all roles with pagination and optional search/filters."""
    stmt = select(Role)

    if name:
        search_filter = f"%{name}%"
        stmt = stmt.where(
            or_(
                Role.name.ilike(search_filter),
                Role.description.ilike(search_filter),
                cast(Role.scope, Text).ilike(search_filter)
            )
        )

    if scope:
        stmt = stmt.where(cast(Role.scope, Text).ilike(scope))

    total = (await db.execute(
        select(func.count()).select_from(stmt.with_only_columns(Role.id).subquery())
    )).scalar_one()
    roles = (await db.execute(stmt.offset(skip).limit(limit))).scalars().all()

    return RoleListResponse(data=roles, total=total)


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role_by_id(
    role_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a role by ID."""
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with id {role_id} not found"
        )

    return role


@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    data: RoleCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new role."""
    existing = (await db.execute(
        select(Role).where(Role.name == data.name)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role with name '{data.name}' already exists"
        )

    role = Role(**data.model_dump())
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: UUID,
    data: RoleUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing role."""
    role = (await db.execute(
        select(Role).where(Role.id == role_id)
    )).scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with id {role_id} not found"
        )

    update_data = data.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] != role.name:
        existing = (await db.execute(
            select(Role).where(Role.name == update_data["name"])
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role with name '{update_data['name']}' already exists"
            )

    for field, value in update_data.items():
        setattr(role, field, value)

    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a role. Gagal jika masih dipakai oleh user."""
    role = (await db.execute(
        select(Role).where(Role.id == role_id)
    )).scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role with id {role_id} not found"
        )

    user_count = (await db.execute(
        select(func.count()).select_from(User).where(User.role_id == role_id)
    )).scalar_one()

    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete role '{role.name}' — still assigned to {user_count} user(s)."
        )

    await db.delete(role)
    await db.commit()
    return None
