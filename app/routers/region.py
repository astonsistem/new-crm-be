from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.region import Province, District
from app.schemas.region import (
    ProvinceCreate, ProvinceUpdate, ProvinceResponse, ProvinceWithDistrictsResponse,
    DistrictCreate, DistrictUpdate, DistrictResponse
)
from pydantic import BaseModel

# Wrapper response models for pagination with total count
class ProvinceListResponse(BaseModel):
    data: List[ProvinceResponse]
    total: int

class DistrictListResponse(BaseModel):
    data: List[DistrictResponse]
    total: int

router = APIRouter(prefix="/regions", tags=["Regions"])


# ========== PROVINCE ENDPOINTS ==========

# List provinces with pagination
@router.get("/provinces", response_model=ProvinceListResponse)
async def get_provinces(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search by province name"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all provinces with optional search and pagination
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **search**: Search by province name (optional)
    """
    stmt = select(Province).where(Province.deleted_at.is_(None))

    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(Province.name.ilike(search_pattern))

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar()

    stmt = stmt.offset(skip).limit(limit)
    provinces = (await db.execute(stmt)).scalars().all()

    return ProvinceListResponse(data=provinces, total=total)


# Get province by ID
@router.get("/provinces/{province_id}", response_model=ProvinceResponse)
async def get_province(
    province_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a province by its ID"""
    province = (await db.execute(
        select(Province).where(
            Province.id == province_id,
            Province.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not province:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Province not found"
        )

    return province


# Get province with its districts
@router.get("/provinces/{province_id}/districts", response_model=ProvinceWithDistrictsResponse)
async def get_province_with_districts(
    province_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a province with all its districts"""
    province = (await db.execute(
        select(Province)
        .options(selectinload(Province.districts))
        .where(
            Province.id == province_id,
            Province.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not province:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Province not found"
        )

    return province


# Create new province
@router.post("/provinces", response_model=ProvinceResponse, status_code=status.HTTP_201_CREATED)
async def create_province(
    province_data: ProvinceCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new province
    
    - **name**: Province name (required)
    """
    existing_province = (await db.execute(
        select(Province).where(
            Province.name == province_data.name,
            Province.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if existing_province:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Province with this name already exists"
        )

    new_province = Province(
        name=province_data.name
    )

    db.add(new_province)
    await db.commit()
    await db.refresh(new_province)

    return new_province


# Update province
@router.put("/provinces/{province_id}", response_model=ProvinceResponse)
async def update_province(
    province_id: UUID,
    province_data: ProvinceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing province
    
    - **name**: Province name (optional)
    """
    province = (await db.execute(
        select(Province).where(
            Province.id == province_id,
            Province.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not province:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Province not found"
        )

    update_data = province_data.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] != province.name:
        existing_province = (await db.execute(
            select(Province).where(
                Province.name == update_data["name"],
                Province.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if existing_province:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Province with this name already exists"
            )

    for field, value in update_data.items():
        setattr(province, field, value)

    await db.commit()
    await db.refresh(province)

    return province


# Soft delete province
@router.delete("/provinces/{province_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_province(
    province_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Soft delete a province
    
    - Sets deleted_at timestamp
    - Province can still be recovered later
    """
    province = (await db.execute(
        select(Province).where(
            Province.id == province_id,
            Province.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not province:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Province not found"
        )

    province.deleted_at = datetime.utcnow()
    await db.commit()

    return None


# ========== DISTRICT ENDPOINTS ==========

# List districts with pagination
@router.get("/districts", response_model=DistrictListResponse)
async def get_districts(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search by district name"),
    province_id: Optional[UUID] = Query(None, description="Filter by province ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all districts with optional search and filters
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **search**: Search by district name (optional)
    - **province_id**: Filter by province ID (optional)
    """
    base_stmt = select(District).where(District.deleted_at.is_(None))

    if search:
        search_pattern = f"%{search}%"
        base_stmt = base_stmt.where(District.name.ilike(search_pattern))

    if province_id:
        base_stmt = base_stmt.where(District.province_id == province_id)

    count_result = await db.execute(select(func.count()).select_from(base_stmt.subquery()))
    total = count_result.scalar()

    stmt = base_stmt.options(selectinload(District.province)).offset(skip).limit(limit)
    districts = (await db.execute(stmt)).scalars().all()

    return DistrictListResponse(data=districts, total=total)


# Get district by ID
@router.get("/districts/{district_id}", response_model=DistrictResponse)
async def get_district(
    district_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a district by its ID"""
    district = (await db.execute(
        select(District)
        .options(selectinload(District.province))
        .where(
            District.id == district_id,
            District.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not district:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="District not found"
        )

    return district


# Create new district
@router.post("/districts", response_model=DistrictResponse, status_code=status.HTTP_201_CREATED)
async def create_district(
    district_data: DistrictCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new district
    
    - **name**: District name (required)
    - **province_id**: Province ID that this district belongs to (required)
    """
    province = (await db.execute(
        select(Province).where(
            Province.id == district_data.province_id,
            Province.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not province:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Province not found"
        )

    existing_district = (await db.execute(
        select(District).where(
            District.name == district_data.name,
            District.province_id == district_data.province_id,
            District.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if existing_district:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="District with this name already exists in this province"
        )

    new_district = District(
        name=district_data.name,
        province_id=district_data.province_id
    )

    db.add(new_district)
    await db.commit()

    new_district = (await db.execute(
        select(District)
        .options(selectinload(District.province))
        .where(District.id == new_district.id)
    )).scalar_one()

    return new_district


# Update district
@router.put("/districts/{district_id}", response_model=DistrictResponse)
async def update_district(
    district_id: UUID,
    district_data: DistrictUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing district
    
    - **name**: District name (optional)
    - **province_id**: Province ID (optional)
    """
    district = (await db.execute(
        select(District).where(
            District.id == district_id,
            District.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not district:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="District not found"
        )

    update_data = district_data.model_dump(exclude_unset=True)

    if "province_id" in update_data:
        province = (await db.execute(
            select(Province).where(
                Province.id == update_data["province_id"],
                Province.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if not province:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Province not found"
            )

    new_name = update_data.get("name", district.name)
    new_province_id = update_data.get("province_id", district.province_id)

    if (new_name != district.name or new_province_id != district.province_id):
        existing_district = (await db.execute(
            select(District).where(
                District.name == new_name,
                District.province_id == new_province_id,
                District.id != district_id,
                District.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if existing_district:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="District with this name already exists in this province"
            )

    for field, value in update_data.items():
        setattr(district, field, value)

    await db.commit()

    district = (await db.execute(
        select(District)
        .options(selectinload(District.province))
        .where(District.id == district_id)
    )).scalar_one()

    return district


# Soft delete district
@router.delete("/districts/{district_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_district(
    district_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Soft delete a district
    
    - Sets deleted_at timestamp
    - District can still be recovered later
    """
    district = (await db.execute(
        select(District).where(
            District.id == district_id,
            District.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not district:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="District not found"
        )

    district.deleted_at = datetime.utcnow()
    await db.commit()

    return None
