from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.dependencies import get_current_active_user, get_db
from app.models import Customer, User
from app.models.region import District, Province
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerUpdate,
)
from app.utils.db_queries import fetch_one, fetch_scalar_first, row_exists

router = APIRouter(prefix="/customers", tags=["Customers"])


def _customer_load_options():
    return (
        joinedload(Customer.sales_user),
        joinedload(Customer.province),
        joinedload(Customer.district),
    )


def _apply_deleted_filter(conditions: list, include_deleted: bool) -> None:
    if not include_deleted:
        conditions.append(Customer.deleted_at.is_(None))


def _append_search_filter(conditions: list, search: str) -> None:
    search_pattern = f"%{search}%"
    conditions.append(
        (Customer.name.ilike(search_pattern))
        | (Customer.email.ilike(search_pattern))
        | (Customer.phone.ilike(search_pattern))
        | (Customer.address.ilike(search_pattern))
        | (Customer.PIC.ilike(search_pattern))
        | (Customer.pic_phone.ilike(search_pattern))
    )


async def _query_customer_list(
    db: AsyncSession,
    conditions: list,
    skip: int,
    limit: int,
) -> CustomerListResponse:
    total = await fetch_scalar_first(
        db,
        select(func.count()).select_from(Customer).where(*conditions),
    ) or 0
    result = await db.execute(
        select(Customer)
        .options(*_customer_load_options())
        .where(*conditions)
        .offset(skip)
        .limit(limit)
    )
    customers = result.scalars().unique().all()
    return CustomerListResponse(
        data=[CustomerResponse.model_validate(customer) for customer in customers],
        total=total,
    )


async def _fetch_customer_with_relations(
    db: AsyncSession,
    customer_id: UUID,
) -> Customer:
    customer = await fetch_one(
        db,
        select(Customer).options(*_customer_load_options()).where(Customer.id == customer_id),
    )
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return customer


async def _fetch_linked_username(db: AsyncSession, customer_id: UUID) -> str | None:
    return await fetch_scalar_first(
        db,
        select(User.username).where(
            User.customer_id == customer_id,
            User.deleted_at.is_(None),
        ),
    )


async def _deactivate_linked_users(db: AsyncSession, customer_id: UUID) -> None:
    result = await db.execute(
        select(User).where(
            User.customer_id == customer_id,
            User.deleted_at.is_(None),
        )
    )
    for user in result.scalars().all():
        user.is_active = False


async def _activate_linked_users(db: AsyncSession, customer_id: UUID) -> None:
    result = await db.execute(
        select(User).where(
            User.customer_id == customer_id,
            User.deleted_at.is_(None),
        )
    )
    for user in result.scalars().all():
        user.is_active = True


async def _ensure_unique_email(
    db: AsyncSession,
    email: str,
    *,
    exclude_customer_id: UUID | None = None,
) -> None:
    conditions = [Customer.email == email, Customer.deleted_at.is_(None)]
    if exclude_customer_id:
        conditions.append(Customer.id != exclude_customer_id)
    if await row_exists(db, select(Customer.id).where(*conditions)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer with this email already exists",
        )


async def _ensure_sales_user_exists(db: AsyncSession, sales_id: UUID) -> None:
    if not await row_exists(db, select(User.id).where(User.id == sales_id)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales user not found",
        )


async def _ensure_company_exists(db: AsyncSession, company_id: UUID) -> Customer:
    company = await fetch_one(
        db,
        select(Customer).where(
            Customer.id == company_id,
            Customer.type == "COMPANY",
            Customer.deleted_at.is_(None),
        ),
    )
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company (pusat) not found",
        )
    return company


async def _ensure_region_exists(
    db: AsyncSession,
    region_id: UUID,
    *,
    expected_pusat_id: UUID | None = None,
) -> Customer:
    region = await fetch_one(
        db,
        select(Customer).where(
            Customer.id == region_id,
            Customer.type == "REGION",
            Customer.deleted_at.is_(None),
        ),
    )
    if not region:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Region not found",
        )
    if expected_pusat_id and region.pusat_id != expected_pusat_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Region does not belong to the specified company",
        )
    return region


async def _ensure_province_exists(db: AsyncSession, province_id: UUID) -> None:
    if not await row_exists(
        db,
        select(Province.id).where(
            Province.id == province_id,
            Province.deleted_at.is_(None),
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Province not found",
        )


async def _ensure_district_exists(
    db: AsyncSession,
    district_id: UUID,
    province_id: UUID,
) -> None:
    district = await fetch_one(
        db,
        select(District).where(
            District.id == district_id,
            District.deleted_at.is_(None),
        ),
    )
    if not district:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="District not found",
        )
    if district.province_id != province_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="District does not belong to the specified province",
        )


async def _validate_customer_create(db: AsyncSession, customer_data: CustomerCreate) -> None:
    if customer_data.email:
        await _ensure_unique_email(db, customer_data.email)

    await _ensure_sales_user_exists(db, customer_data.sales_id)

    if customer_data.pusat_id:
        await _ensure_company_exists(db, customer_data.pusat_id)

    if customer_data.region_id:
        await _ensure_region_exists(
            db,
            customer_data.region_id,
            expected_pusat_id=customer_data.pusat_id,
        )

    if customer_data.province_id:
        await _ensure_province_exists(db, customer_data.province_id)

    if customer_data.district_id:
        if not customer_data.province_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="district_id requires province_id to be set",
            )
        await _ensure_district_exists(
            db,
            customer_data.district_id,
            customer_data.province_id,
        )


async def _validate_customer_update(
    db: AsyncSession,
    customer: Customer,
    update_data: dict,
) -> None:
    if update_data.get("sales_id"):
        await _ensure_sales_user_exists(db, update_data["sales_id"])

    if (
        "email" in update_data
        and update_data["email"]
        and update_data["email"] != customer.email
    ):
        await _ensure_unique_email(
            db,
            update_data["email"],
            exclude_customer_id=customer.id,
        )

    new_type = update_data.get("type", customer.type)
    new_pusat_id = update_data.get("pusat_id", customer.pusat_id)
    new_region_id = update_data.get("region_id", customer.region_id)

    if new_type == "COMPANY":
        if new_pusat_id is not None or new_region_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="COMPANY type cannot have pusat_id or region_id",
            )
    elif new_type == "REGION":
        if new_pusat_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="REGION type must have pusat_id",
            )
        if new_region_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="REGION type cannot have region_id",
            )
    elif new_type == "BRANCH":
        if new_pusat_id is None or new_region_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="BRANCH type must have both pusat_id and region_id",
            )

    if update_data.get("pusat_id"):
        await _ensure_company_exists(db, update_data["pusat_id"])

    if update_data.get("region_id"):
        await _ensure_region_exists(
            db,
            update_data["region_id"],
            expected_pusat_id=new_pusat_id,
        )

    if update_data.get("province_id"):
        await _ensure_province_exists(db, update_data["province_id"])

    if update_data.get("district_id"):
        new_province_id = update_data.get("province_id", customer.province_id)
        if not new_province_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="district_id requires province_id to be set",
            )
        await _ensure_district_exists(
            db,
            update_data["district_id"],
            new_province_id,
        )


# List all customers with pagination
@router.get("/", response_model=CustomerListResponse)
async def get_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=200),
    search: Optional[str] = None,
    email: Optional[str] = Query(None, description="Filter by exact email (case-sensitive)"),
    type: Optional[str] = Query(None, description="Filter by customer type: COMPANY, REGION, BRANCH"),
    pusat_id: Optional[UUID] = Query(None, description="Filter by company ID"),
    region_id: Optional[UUID] = Query(None, description="Filter by region ID"),
    sales_id: Optional[UUID] = Query(None, description="Filter by sales person ID"),
    province_id: Optional[UUID] = Query(None, description="Filter by province ID"),
    district_id: Optional[UUID] = Query(None, description="Filter by district ID"),
    include_deleted: bool = Query(
        False,
        description="If true, include soft-deleted customers. If false, only active customers.",
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all customers with optional search and filters
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **search**: Search by name, email, phone, address, or PIC (optional)
    - **email**: Filter by exact email match (case-sensitive)
    - **type**: Filter by customer type (COMPANY, REGION, BRANCH)
    - **pusat_id**: Filter by company ID
    - **region_id**: Filter by region ID
    - **sales_id**: Filter by sales person ID
    - **province_id**: Filter by province ID
    - **district_id**: Filter by district ID
    - **include_deleted**: false = hide deleted (default), true = show all
    """
    conditions = []
    _apply_deleted_filter(conditions, include_deleted)

    if search:
        _append_search_filter(conditions, search)

    if email:
        conditions.append(Customer.email == email)

    if type:
        conditions.append(Customer.type == type)

    if pusat_id:
        conditions.append(Customer.pusat_id == pusat_id)

    if region_id:
        conditions.append(Customer.region_id == region_id)

    if sales_id:
        conditions.append(Customer.sales_id == sales_id)

    if province_id:
        conditions.append(Customer.province_id == province_id)

    if district_id:
        conditions.append(Customer.district_id == district_id)

    return await _query_customer_list(db, conditions, skip, limit)


# Get current user's customers (for sales people)
@router.get("/me", response_model=CustomerListResponse)
async def get_my_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=500),
    search: Optional[str] = None,
    email: Optional[str] = Query(None, description="Filter by exact email (case-sensitive)"),
    type: Optional[str] = Query(None, description="Filter by customer type: COMPANY, REGION, BRANCH"),
    pusat_id: Optional[UUID] = Query(None, description="Filter by company ID"),
    region_id: Optional[UUID] = Query(None, description="Filter by region ID"),
    province_id: Optional[UUID] = Query(None, description="Filter by province ID"),
    district_id: Optional[UUID] = Query(None, description="Filter by district ID"),
    include_deleted: bool = Query(
        False,
        description="If true, include soft-deleted customers. If false, only active customers.",
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all customers assigned to the currently logged-in user (sales person)
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **search**: Search by name, email, phone, address, or PIC (optional)
    - **email**: Filter by exact email match (case-sensitive)
    - **type**: Filter by customer type (COMPANY, REGION, BRANCH)
    - **pusat_id**: Filter by company ID
    - **region_id**: Filter by region ID
    - **province_id**: Filter by province ID
    - **district_id**: Filter by district ID
    - **include_deleted**: false = hide deleted (default), true = show all
    """
    conditions = [Customer.sales_id == current_user.id]
    _apply_deleted_filter(conditions, include_deleted)

    if search:
        _append_search_filter(conditions, search)

    if email:
        conditions.append(Customer.email == email)

    if type:
        conditions.append(Customer.type == type)

    if pusat_id:
        conditions.append(Customer.pusat_id == pusat_id)

    if region_id:
        conditions.append(Customer.region_id == region_id)

    if province_id:
        conditions.append(Customer.province_id == province_id)

    if district_id:
        conditions.append(Customer.district_id == district_id)

    return await _query_customer_list(db, conditions, skip, limit)


# Get customer by ID
@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    include_deleted: bool = Query(
        False,
        description="If true, return customer even when soft-deleted.",
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific customer by ID
    """
    conditions = [Customer.id == customer_id]
    _apply_deleted_filter(conditions, include_deleted)

    customer = await fetch_one(
        db,
        select(Customer).options(*_customer_load_options()).where(*conditions),
    )

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    username = await _fetch_linked_username(db, customer_id)
    response = CustomerResponse.model_validate(customer)
    return response.model_copy(update={"username": username})


# Create new customer
@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new customer
    
    - **name**: Full name of the customer (required)
    - **PIC**: Person in Charge (optional)
    - **type**: Customer type - COMPANY, REGION, or BRANCH (required)
    - **email**: Email address (optional)
    - **phone**: Phone number (optional)
    - **address**: Physical address (optional)
    - **province_id**: Province ID (optional)
    - **district_id**: District ID (optional, requires province_id)
    - **sales_id**: Sales user ID responsible for this customer (required)
    - **pusat_id**: Company ID (required for REGION and BRANCH)
    - **region_id**: Region ID (required for BRANCH)
    """
    await _validate_customer_create(db, customer_data)

    new_customer = Customer(
        type=customer_data.type,
        name=customer_data.name,
        PIC=customer_data.PIC,
        pic_phone=customer_data.pic_phone,
        email=customer_data.email,
        phone=customer_data.phone,
        address=customer_data.address,
        province_id=customer_data.province_id,
        district_id=customer_data.district_id,
        pusat_id=customer_data.pusat_id,
        region_id=customer_data.region_id,
        sales_id=customer_data.sales_id
    )

    db.add(new_customer)
    await db.commit()

    customer = await _fetch_customer_with_relations(db, new_customer.id)
    return CustomerResponse.model_validate(customer)


# Update customer
@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    customer_data: CustomerUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing customer
    
    - All fields are optional
    - Only provided fields will be updated
    """
    customer = await fetch_one(
        db,
        select(Customer).options(*_customer_load_options()).where(
            Customer.id == customer_id,
            Customer.deleted_at.is_(None),
        ),
    )

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    update_data = customer_data.model_dump(exclude_unset=True)

    if "sales" in update_data and update_data["sales"]:
        update_data["sales_id"] = update_data["sales"]["id"]
        del update_data["sales"]

    if "province" in update_data and update_data["province"]:
        update_data["province_id"] = update_data["province"]["id"]
        del update_data["province"]

    if "district" in update_data and update_data["district"]:
        update_data["district_id"] = update_data["district"]["id"]
        del update_data["district"]

    await _validate_customer_update(db, customer, update_data)

    for field, value in update_data.items():
        setattr(customer, field, value)

    await db.commit()

    customer = await _fetch_customer_with_relations(db, customer_id)
    return CustomerResponse.model_validate(customer)


# Soft delete customer
@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Soft delete a customer
    
    - Sets deleted_at timestamp
    - Deactivates linked user accounts (is_active = false)
    - Customer can still be recovered later
    """
    customer = await fetch_one(
        db,
        select(Customer).where(
            Customer.id == customer_id,
            Customer.deleted_at.is_(None),
        ),
    )

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    customer.deleted_at = datetime.utcnow()
    await _deactivate_linked_users(db, customer_id)
    await db.commit()

    return None


# Restore deleted customer
@router.patch("/{customer_id}/restore", response_model=CustomerResponse)
async def restore_customer(
    customer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Restore a soft-deleted customer
    
    - Clears deleted_at timestamp when set
    - Reactivates linked user accounts (is_active = true)
    """
    customer = await fetch_one(
        db,
        select(Customer).where(Customer.id == customer_id),
    )

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    customer.deleted_at = None
    await _activate_linked_users(db, customer_id)
    await db.commit()

    customer = await _fetch_customer_with_relations(db, customer_id)
    return CustomerResponse.model_validate(customer)


# Hard delete customer (permanent)
@router.delete("/{customer_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer_permanent(
    customer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Permanently delete a customer from the database
    
    - ⚠️ This action cannot be undone
    - Use with caution
    """
    customer = await fetch_one(
        db,
        select(Customer).where(Customer.id == customer_id),
    )

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    await db.delete(customer)
    await db.commit()

    return None


# Get all companies
@router.get("/companies/list", response_model=CustomerListResponse)
async def get_companies(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, description="Filter by company name (partial, case-insensitive)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all companies (COMPANY type customers) with pagination
    """
    base_where = [Customer.type == "COMPANY", Customer.deleted_at.is_(None)]
    if search:
        base_where.append(Customer.name.ilike(f"%{search}%"))

    return await _query_customer_list(db, base_where, skip, limit)


# Get regions by company
@router.get("/companies/{company_id}/regions", response_model=CustomerListResponse)
async def get_regions_by_company(
    company_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, description="Filter by region name (partial, case-insensitive)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all regions belonging to a specific company with pagination
    """
    company = await fetch_one(
        db,
        select(Customer).where(
            Customer.id == company_id,
            Customer.type == "COMPANY",
            Customer.deleted_at.is_(None),
        ),
    )

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )

    base_where = [
        Customer.type == "REGION",
        Customer.pusat_id == company_id,
        Customer.deleted_at.is_(None),
    ]
    if search:
        base_where.append(Customer.name.ilike(f"%{search}%"))

    return await _query_customer_list(db, base_where, skip, limit)


# Get branches by region
@router.get("/regions/{region_id}/branches", response_model=CustomerListResponse)
async def get_branches_by_region(
    region_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, description="Filter by branch name (partial, case-insensitive)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all branches belonging to a specific region with pagination
    """
    region = await fetch_one(
        db,
        select(Customer).where(
            Customer.id == region_id,
            Customer.type == "REGION",
            Customer.deleted_at.is_(None),
        ),
    )

    if not region:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Region not found"
        )

    base_where = [
        Customer.type == "BRANCH",
        Customer.region_id == region_id,
        Customer.deleted_at.is_(None),
    ]
    if search:
        base_where.append(Customer.name.ilike(f"%{search}%"))

    return await _query_customer_list(db, base_where, skip, limit)


# Get all branches by company (across all regions)
@router.get("/companies/{company_id}/branches", response_model=CustomerListResponse)
async def get_branches_by_company(
    company_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, description="Filter by branch name (partial, case-insensitive)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all branches belonging to a specific company (across all regions) with pagination
    """
    company = await fetch_one(
        db,
        select(Customer).where(
            Customer.id == company_id,
            Customer.type == "COMPANY",
            Customer.deleted_at.is_(None),
        ),
    )

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )

    base_where = [
        Customer.type == "BRANCH",
        Customer.pusat_id == company_id,
        Customer.deleted_at.is_(None),
    ]
    if search:
        base_where.append(Customer.name.ilike(f"%{search}%"))

    return await _query_customer_list(db, base_where, skip, limit)