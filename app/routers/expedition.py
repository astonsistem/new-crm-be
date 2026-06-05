from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List, Optional
from uuid import UUID
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.expedition import Expedition
from pydantic import BaseModel

# Schemas
class ExpeditionCreate(BaseModel):
    name: str
    url: Optional[str] = None

class ExpeditionResponse(BaseModel):
    id: UUID
    name: str
    url: Optional[str] = None

    class Config:
        from_attributes = True

class ExpeditionUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None

class ExpeditionListResponse(BaseModel):
    data: List[ExpeditionResponse]
    total: int

router = APIRouter(prefix="/expeditions", tags=["Expeditions"])


@router.get("/", response_model=ExpeditionListResponse)
async def get_expeditions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of all expeditions"""
    stmt = select(Expedition).where(Expedition.deleted_at.is_(None))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    expeditions = (await db.execute(stmt.offset(skip).limit(limit))).scalars().all()

    return ExpeditionListResponse(data=expeditions, total=total)


@router.post("/", response_model=ExpeditionResponse, status_code=status.HTTP_201_CREATED)
async def create_expedition(
    expedition: ExpeditionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new expedition"""
    existing = (await db.execute(
        select(Expedition).where(
            Expedition.name == expedition.name,
            Expedition.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expedition with name '{expedition.name}' already exists"
        )

    db_expedition = Expedition(**expedition.model_dump())
    db.add(db_expedition)
    await db.commit()
    await db.refresh(db_expedition)

    return db_expedition


@router.put("/{expedition_id}", response_model=ExpeditionResponse)
async def update_expedition(
    expedition_id: UUID,
    expedition: ExpeditionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an expedition"""
    db_expedition = (await db.execute(
        select(Expedition).where(
            Expedition.id == expedition_id,
            Expedition.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not db_expedition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expedition not found"
        )

    update_data = expedition.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != db_expedition.name:
        existing = (await db.execute(
            select(Expedition).where(
                Expedition.name == update_data["name"],
                Expedition.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Expedition with name '{update_data['name']}' already exists"
            )

    for key, value in update_data.items():
        setattr(db_expedition, key, value)

    await db.commit()
    await db.refresh(db_expedition)

    return db_expedition
