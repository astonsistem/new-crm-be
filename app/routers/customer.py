from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.dependencies import get_current_active_user, get_db
from app.models import User, Customer
from app.models.region import Province, District
from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse
from pydantic import BaseModel

# Wrapper response models for pagination with total count
class CustomerListResponse(BaseModel):
    data: List[CustomerResponse]
    total: int
    
router = APIRouter(prefix="/customers", tags=["Customers"])


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
    """
    conditions = [Customer.deleted_at.is_(None)]

    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            (Customer.name.ilike(search_pattern)) |
            (Customer.email.ilike(search_pattern)) |
            (Customer.phone.ilike(search_pattern)) |
            (Customer.address.ilike(search_pattern)) |
            (Customer.PIC.ilike(search_pattern)) |
            (Customer.pic_phone.ilike(search_pattern))
        )

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

    total = (await db.execute(
        select(func.count()).select_from(Customer).where(*conditions)
    )).scalar()

    customers = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district)
        ).where(*conditions).offset(skip).limit(limit)
    )).scalars().all()

    customer_responses = [CustomerResponse.model_validate(customer) for customer in customers]

    return CustomerListResponse(data=customer_responses, total=total)




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
    """
    conditions = [
        Customer.sales_id == current_user.id,
        Customer.deleted_at.is_(None)
    ]

    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            (Customer.name.ilike(search_pattern)) |
            (Customer.email.ilike(search_pattern)) |
            (Customer.phone.ilike(search_pattern)) |
            (Customer.address.ilike(search_pattern)) |
            (Customer.PIC.ilike(search_pattern)) |
            (Customer.pic_phone.ilike(search_pattern))
        )

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

    total = (await db.execute(
        select(func.count()).select_from(Customer).where(*conditions)
    )).scalar()

    customers = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district)
        ).where(*conditions).offset(skip).limit(limit)
    )).scalars().all()

    customer_responses = [CustomerResponse.model_validate(customer) for customer in customers]

    return CustomerListResponse(data=customer_responses, total=total)


# Get customer by ID
@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific customer by ID
    """
    customer = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district)
        ).where(
            Customer.id == customer_id,
            Customer.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    username = (await db.execute(
        select(User.username).where(
            User.customer_id == customer_id,
            User.deleted_at.is_(None),
        )
    )).scalar_one_or_none()

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
    if customer_data.email:
        existing_customer = (await db.execute(
            select(Customer).where(
                Customer.email == customer_data.email,
                Customer.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if existing_customer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer with this email already exists"
            )

    from app.models.user import User
    sales_user = (await db.execute(
        select(User).where(User.id == customer_data.sales_id)
    )).scalar_one_or_none()
    if not sales_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales user not found"
        )

    if customer_data.pusat_id:
        pusat = (await db.execute(
            select(Customer).where(
                Customer.id == customer_data.pusat_id,
                Customer.type == "COMPANY",
                Customer.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if not pusat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company (pusat) not found"
            )

    if customer_data.region_id:
        region = (await db.execute(
            select(Customer).where(
                Customer.id == customer_data.region_id,
                Customer.type == "REGION",
                Customer.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if not region:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Region not found"
            )
        if customer_data.pusat_id and region.pusat_id != customer_data.pusat_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Region does not belong to the specified company"
            )

    if customer_data.province_id:
        province = (await db.execute(
            select(Province).where(
                Province.id == customer_data.province_id,
                Province.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if not province:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Province not found"
            )

    if customer_data.district_id:
        if not customer_data.province_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="district_id requires province_id to be set"
            )

        district = (await db.execute(
            select(District).where(
                District.id == customer_data.district_id,
                District.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if not district:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="District not found"
            )
        if district.province_id != customer_data.province_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="District does not belong to the specified province"
            )

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
    await db.refresh(new_customer)

    customer = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district)
        ).where(Customer.id == new_customer.id)
    )).scalar_one_or_none()

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
    customer = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district)
        ).where(
            Customer.id == customer_id,
            Customer.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

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

    if "sales_id" in update_data and update_data["sales_id"]:
        from app.models.user import User
        sales_user = (await db.execute(
            select(User).where(User.id == update_data["sales_id"])
        )).scalar_one_or_none()
        if not sales_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sales user not found"
            )

    if "email" in update_data and update_data["email"] and update_data["email"] != customer.email:
        existing_customer = (await db.execute(
            select(Customer).where(
                Customer.email == update_data["email"],
                Customer.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if existing_customer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer with this email already exists"
            )

    new_type = update_data.get("type", customer.type)
    new_pusat_id = update_data.get("pusat_id", customer.pusat_id)
    new_region_id = update_data.get("region_id", customer.region_id)

    if new_type == "COMPANY":
        if new_pusat_id is not None or new_region_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="COMPANY type cannot have pusat_id or region_id"
            )
    elif new_type == "REGION":
        if new_pusat_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="REGION type must have pusat_id"
            )
        if new_region_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="REGION type cannot have region_id"
            )
    elif new_type == "BRANCH":
        if new_pusat_id is None or new_region_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="BRANCH type must have both pusat_id and region_id"
            )

    if "pusat_id" in update_data and update_data["pusat_id"]:
        pusat = (await db.execute(
            select(Customer).where(
                Customer.id == update_data["pusat_id"],
                Customer.type == "COMPANY",
                Customer.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if not pusat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company (pusat) not found"
            )

    if "region_id" in update_data and update_data["region_id"]:
        region = (await db.execute(
            select(Customer).where(
                Customer.id == update_data["region_id"],
                Customer.type == "REGION",
                Customer.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if not region:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Region not found"
            )
        if new_pusat_id and region.pusat_id != new_pusat_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Region does not belong to the specified company"
            )

    if "province_id" in update_data and update_data["province_id"]:
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

    if "district_id" in update_data and update_data["district_id"]:
        new_province_id = update_data.get("province_id", customer.province_id)
        if not new_province_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="district_id requires province_id to be set"
            )

        district = (await db.execute(
            select(District).where(
                District.id == update_data["district_id"],
                District.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if not district:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="District not found"
            )
        if district.province_id != new_province_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="District does not belong to the specified province"
            )

    for field, value in update_data.items():
        setattr(customer, field, value)

    await db.commit()

    # Re-query with eager loading — db.refresh() strips loaded relationships
    customer = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district),
        ).where(Customer.id == customer_id)
    )).scalar_one()

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
    - Customer can still be recovered later
    """
    customer = (await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    customer.deleted_at = datetime.utcnow()
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
    
    - Clears deleted_at timestamp
    """
    customer = (await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.deleted_at.isnot(None)
        )
    )).scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deleted customer not found"
        )

    customer.deleted_at = None
    await db.commit()

    # Re-query with eager loading — db.refresh() strips loaded relationships
    customer = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district),
        ).where(Customer.id == customer_id)
    )).scalar_one()

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
    customer = (await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )).scalar_one_or_none()

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

    total = (await db.execute(
        select(func.count(Customer.id)).where(*base_where)
    )).scalar()

    companies = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district),
        ).where(*base_where).offset(skip).limit(limit)
    )).scalars().unique().all()

    return CustomerListResponse(
        data=[CustomerResponse.model_validate(c) for c in companies],
        total=total,
    )


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
    company = (await db.execute(
        select(Customer).where(
            Customer.id == company_id,
            Customer.type == "COMPANY",
            Customer.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

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

    total = (await db.execute(
        select(func.count(Customer.id)).where(*base_where)
    )).scalar()

    regions = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district),
        ).where(*base_where).offset(skip).limit(limit)
    )).scalars().unique().all()

    return CustomerListResponse(
        data=[CustomerResponse.model_validate(r) for r in regions],
        total=total,
    )


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
    region = (await db.execute(
        select(Customer).where(
            Customer.id == region_id,
            Customer.type == "REGION",
            Customer.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

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

    total = (await db.execute(
        select(func.count(Customer.id)).where(*base_where)
    )).scalar()

    branches = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district),
        ).where(*base_where).offset(skip).limit(limit)
    )).scalars().unique().all()

    return CustomerListResponse(
        data=[CustomerResponse.model_validate(b) for b in branches],
        total=total,
    )


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
    company = (await db.execute(
        select(Customer).where(
            Customer.id == company_id,
            Customer.type == "COMPANY",
            Customer.deleted_at.is_(None)
        )
    )).scalar_one_or_none()

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

    total = (await db.execute(
        select(func.count(Customer.id)).where(*base_where)
    )).scalar()

    branches = (await db.execute(
        select(Customer).options(
            joinedload(Customer.sales_user),
            joinedload(Customer.province),
            joinedload(Customer.district),
        ).where(*base_where).offset(skip).limit(limit)
    )).scalars().unique().all()

    return CustomerListResponse(
        data=[CustomerResponse.model_validate(b) for b in branches],
        total=total,
    )
