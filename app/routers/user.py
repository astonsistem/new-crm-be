from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from uuid import UUID
from app.dependencies import get_current_active_user, get_db
from app.models import User, Role
from app.models.customer import Customer
from app.models.asis_sync import AsisCompany, AsisBranch, AsisWarehouse
from app.schemas import UserCreate, UserUpdate, UserResponse
from app.utils.security import get_password_hash
from app.utils.eager_loads import user_selectinload_options

router = APIRouter(prefix="/users", tags=["Users"])


def _user_opts():
    return user_selectinload_options()


# Get current user profile
@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current user profile - Protected endpoint
    Requires valid access token
    """
    from app.schemas.auth import CustomerDetail, AsisEntityBrief
    return UserResponse(
        id=current_user.id,
        name=current_user.name,
        username=current_user.username,
        role_id=current_user.role_id,
        role_name=current_user.role.name if current_user.role else None,
        role_scope=current_user.role.scope if current_user.role else None,
        is_active=current_user.is_active,
        customer_id=current_user.customer_id,
        customer=CustomerDetail(
            name=current_user.customer.name,
            PIC=current_user.customer.PIC,
            type=current_user.customer.type,
            email=current_user.customer.email,
            phone=current_user.customer.phone,
            address=current_user.customer.address,
            province_id=current_user.customer.province_id,
            province=current_user.customer.province,
            district_id=current_user.customer.district_id,
            district=current_user.customer.district,
            region_id=current_user.customer.region_id,
            sales_id=current_user.customer.sales_id,
            pusat_id=current_user.customer.pusat_id
        ) if current_user.customer else None,
        asis_company_id=current_user.asis_company_id,
        asis_company=AsisEntityBrief.model_validate(current_user.asis_company) if current_user.asis_company else None,
        asis_branch_id=current_user.asis_branch_id,
        asis_branch=AsisEntityBrief.model_validate(current_user.asis_branch) if current_user.asis_branch else None,
        asis_warehouse_id=current_user.asis_warehouse_id,
        asis_warehouse=AsisEntityBrief.model_validate(current_user.asis_warehouse) if current_user.asis_warehouse else None,
        last_login=current_user.last_login,
        created_at=current_user.created_at,
        created_by=current_user.created_by,
        updated_by=current_user.updated_by
    )


# List all users with pagination
@router.get("/", response_model=List[UserResponse])
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search users by name or username (partial, case-insensitive)"),
    is_active: Optional[bool] = None,
    role_id: Optional[UUID] = None,
    username: Optional[str] = Query(None, description="Filter by username (partial, case-insensitive)"),
    created_by: Optional[UUID] = Query(None, description="Filter by creator user ID"),
    province_id: Optional[UUID] = Query(None, description="Filter by province ID (via customer)"),
    district_id: Optional[UUID] = Query(None, description="Filter by district ID (via customer)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all users with optional filtering
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **is_active**: Filter by active status (optional)
    - **role_id**: Filter by role ID (optional)
    - **created_by**: Filter by creator user ID (optional)
    - **province_id**: Filter by province ID via customer (optional)
    - **district_id**: Filter by district ID via customer (optional)
    """
    stmt = select(User).options(*_user_opts())

    if username:
        stmt = stmt.where(User.username == username)

    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    if role_id is not None:
        stmt = stmt.where(User.role_id == role_id)

    if search is not None:
        stmt = stmt.where(
            (User.name.ilike(f"%{search}%")) | (User.username.ilike(f"%{search}%"))
        )

    if created_by is not None:
        stmt = stmt.where(User.created_by == created_by)

    if province_id is not None or district_id is not None:
        stmt = stmt.join(Customer, User.customer_id == Customer.id)
        if province_id is not None:
            stmt = stmt.where(Customer.province_id == province_id)
        if district_id is not None:
            stmt = stmt.where(Customer.district_id == district_id)

    stmt = stmt.offset(skip).limit(limit)
    users = (await db.execute(stmt)).scalars().unique().all()

    from app.schemas.auth import CustomerDetail
    result = []
    for user in users:
        result.append(UserResponse(
            id=user.id,
            name=user.name,
            username=user.username,
            role_id=user.role_id,
            role_name=user.role.name if user.role else None,
            role_scope=user.role.scope if user.role else None,
            is_active=user.is_active,
            customer_id=user.customer_id,
            customer=CustomerDetail(
                name=user.customer.name,
                PIC=user.customer.PIC,
                type=user.customer.type,
                email=user.customer.email,
                phone=user.customer.phone,
                address=user.customer.address,
                province_id=user.customer.province_id,
                province=user.customer.province,
                district_id=user.customer.district_id,
                district=user.customer.district,
                region_id=user.customer.region_id,
                sales_id=user.customer.sales_id,
                pusat_id=user.customer.pusat_id
            ) if user.customer else None,
            last_login=user.last_login,
            created_at=user.created_at,
            created_by=user.created_by,
            updated_by=user.updated_by
        ))

    return result


# Get user by ID
@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific user by ID
    """
    user = (await db.execute(
        select(User).options(*_user_opts()).where(User.id == user_id)
    )).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    from app.schemas.auth import CustomerDetail
    return UserResponse(
        id=user.id,
        name=user.name,
        username=user.username,
        role_id=user.role_id,
        role_name=user.role.name if user.role else None,
        role_scope=user.role.scope if user.role else None,
        is_active=user.is_active,
        customer_id=user.customer_id,
        customer=CustomerDetail(
            name=user.customer.name,
            PIC=user.customer.PIC,
            type=user.customer.type,
            email=user.customer.email,
            phone=user.customer.phone,
            address=user.customer.address,
            province_id=user.customer.province_id,
            province=user.customer.province,
            district_id=user.customer.district_id,
            district=user.customer.district,
            region_id=user.customer.region_id,
            sales_id=user.customer.sales_id,
            pusat_id=user.customer.pusat_id
        ) if user.customer else None,
        last_login=user.last_login,
        created_at=user.created_at,
        created_by=user.created_by,
        updated_by=user.updated_by
    )


# Create new user
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new user
    
    - **name**: Full name of the user
    - **username**: Unique username for login
    - **password**: Password (min 6 characters)
    - **role_id**: ID of the role to assign (for admin/internal users)
    - **customer_id**: ID of the customer to assign (for customer users)
    
    Note: User must have either role_id OR customer_id, not both
    """
    existing_user = (await db.execute(select(User).where(User.username == user_data.username))).scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )

    role = None
    customer = None

    if user_data.role_id:
        role = (await db.execute(select(Role).where(Role.id == user_data.role_id))).scalar_one_or_none()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found"
            )

    if user_data.customer_id:
        from app.models import Customer
        customer = (await db.execute(
            select(Customer).where(
                Customer.id == user_data.customer_id,
                Customer.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )

    hashed_password = get_password_hash(user_data.password)

    new_user = User(
        name=user_data.name,
        username=user_data.username,
        password=hashed_password,
        role_id=user_data.role_id,
        customer_id=user_data.customer_id,
        is_active=True,
        created_by=current_user.id
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    from app.schemas.auth import CustomerDetail
    return UserResponse(
        id=new_user.id,
        name=new_user.name,
        username=new_user.username,
        role_id=new_user.role_id,
        role_name=role.name if role else None,
        role_scope=role.scope if role else None,
        customer_id=new_user.customer_id,
        customer=CustomerDetail(
            name=customer.name,
            type=customer.type,
            email=customer.email,
            phone=customer.phone
        ) if customer else None,
        is_active=new_user.is_active,
        last_login=new_user.last_login,
        created_at=new_user.created_at,
        created_by=new_user.created_by,
        updated_by=new_user.updated_by
    )


# Update user
@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing user
    
    - All fields are optional
    - Only provided fields will be updated
    - Password will be hashed if provided
    """
    user = (await db.execute(
        select(User).options(*_user_opts()).where(User.id == user_id)
    )).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    update_data = user_data.model_dump(exclude_unset=True)

    if "username" in update_data and update_data["username"] != user.username:
        existing_user = (await db.execute(
            select(User).where(User.username == update_data["username"])
        )).scalar_one_or_none()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )

    if "role_id" in update_data:
        role = (await db.execute(select(Role).where(Role.id == update_data["role_id"]))).scalar_one_or_none()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found"
            )

    if "asis_company_id" in update_data and update_data["asis_company_id"] is not None:
        ok = (await db.execute(
            select(AsisCompany.id).where(AsisCompany.id == update_data["asis_company_id"])
        )).scalar_one_or_none()
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ASIS Company tidak ditemukan.")

    if "asis_branch_id" in update_data and update_data["asis_branch_id"] is not None:
        ok = (await db.execute(
            select(AsisBranch.id).where(AsisBranch.id == update_data["asis_branch_id"])
        )).scalar_one_or_none()
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ASIS Branch tidak ditemukan.")

    if "asis_warehouse_id" in update_data and update_data["asis_warehouse_id"] is not None:
        ok = (await db.execute(
            select(AsisWarehouse.id).where(AsisWarehouse.id == update_data["asis_warehouse_id"])
        )).scalar_one_or_none()
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ASIS Warehouse tidak ditemukan.")

    if "password" in update_data:
        update_data["password"] = get_password_hash(update_data["password"])

    for field, value in update_data.items():
        setattr(user, field, value)

    user.updated_by = current_user.id

    await db.commit()
    # Re-query with eager loading — db.refresh() strips loaded relationships
    user = (await db.execute(
        select(User).options(*_user_opts()).where(User.id == user_id)
    )).scalar_one()

    from app.schemas.auth import CustomerDetail, AsisEntityBrief
    return UserResponse(
        id=user.id,
        name=user.name,
        username=user.username,
        role_id=user.role_id,
        role_name=user.role.name if user.role else None,
        role_scope=user.role.scope if user.role else None,
        is_active=user.is_active,
        customer_id=user.customer_id,
        customer=CustomerDetail(
            name=user.customer.name,
            type=user.customer.type,
            email=user.customer.email,
            phone=user.customer.phone,
            address=user.customer.address,
            province_id=user.customer.province_id,
            province=user.customer.province,
            district_id=user.customer.district_id,
            district=user.customer.district,
            region_id=user.customer.region_id,
            sales_id=user.customer.sales_id,
            pusat_id=user.customer.pusat_id
        ) if user.customer else None,
        asis_company_id=user.asis_company_id,
        asis_company=AsisEntityBrief.model_validate(user.asis_company) if user.asis_company else None,
        asis_branch_id=user.asis_branch_id,
        asis_branch=AsisEntityBrief.model_validate(user.asis_branch) if user.asis_branch else None,
        asis_warehouse_id=user.asis_warehouse_id,
        asis_warehouse=AsisEntityBrief.model_validate(user.asis_warehouse) if user.asis_warehouse else None,
        last_login=user.last_login,
        created_at=user.created_at,
        created_by=user.created_by,
        updated_by=user.updated_by
    )


# Soft delete user (deactivate)
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Soft delete (deactivate) a user
    
    - Sets is_active to False
    - User can still be reactivated later
    """
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )

    user.is_active = False
    await db.commit()

    return None


# Reactivate user
@router.patch("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Reactivate a deactivated user
    
    - Sets is_active to True
    """
    user = (await db.execute(
        select(User).options(*_user_opts()).where(User.id == user_id)
    )).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.is_active = True
    await db.commit()
    # Re-query with eager loading — db.refresh() strips loaded relationships
    user = (await db.execute(
        select(User).options(*_user_opts()).where(User.id == user_id)
    )).scalar_one()

    from app.schemas.auth import CustomerDetail
    return UserResponse(
        id=user.id,
        name=user.name,
        username=user.username,
        role_id=user.role_id,
        role_name=user.role.name if user.role else None,
        role_scope=user.role.scope if user.role else None,
        is_active=user.is_active,
        customer_id=user.customer_id,
        customer=CustomerDetail(
            name=user.customer.name,
            type=user.customer.type,
            email=user.customer.email,
            phone=user.customer.phone,
            address=user.customer.address,
            province_id=user.customer.province_id,
            province=user.customer.province,
            district_id=user.customer.district_id,
            district=user.customer.district,
            region_id=user.customer.region_id,
            sales_id=user.customer.sales_id,
            pusat_id=user.customer.pusat_id
        ) if user.customer else None,
        last_login=user.last_login,
        created_at=user.created_at,
        created_by=user.created_by,
        updated_by=user.updated_by
    )


# Hard delete user (permanent)
@router.delete("/{user_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_permanent(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    await db.delete(user)
    await db.commit()

    return None
