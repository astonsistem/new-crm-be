from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.asis_sync import AsisBranch, AsisCompany, AsisWarehouse
from app.models.bank_account import Bank_Account
from app.schemas.bank_account import (
    BankAccountCreate,
    BankAccountListResponse,
    BankAccountResponse,
    BankAccountUpdate,
)
from app.utils.db_queries import fetch_one, row_exists

router = APIRouter(prefix="/bank-accounts", tags=["Bank Accounts"])


def _bank_account_load_options():
    return [
        joinedload(Bank_Account.asis_company),
        joinedload(Bank_Account.asis_branch),
        joinedload(Bank_Account.asis_warehouse),
    ]


async def _fetch_bank_account(db: AsyncSession, bank_account_id: UUID) -> Bank_Account | None:
    return await fetch_one(
        db,
        select(Bank_Account)
        .options(*_bank_account_load_options())
        .where(
            Bank_Account.id == bank_account_id,
            Bank_Account.deleted_at.is_(None),
        ),
    )


async def _ensure_asis_refs(
    db: AsyncSession,
    *,
    asis_company_id: Optional[UUID],
    asis_branch_id: Optional[UUID],
    asis_warehouse_id: Optional[UUID],
) -> None:
    if asis_company_id is not None:
        if not await row_exists(
            db, select(AsisCompany.id).where(AsisCompany.id == asis_company_id)
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ASIS company tidak ditemukan",
            )

    if asis_branch_id is not None:
        branch = await fetch_one(
            db, select(AsisBranch).where(AsisBranch.id == asis_branch_id)
        )
        if not branch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ASIS branch tidak ditemukan",
            )
        if asis_company_id is not None and branch.asis_company_id not in (None, asis_company_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ASIS branch tidak termasuk company yang dipilih",
            )

    if asis_warehouse_id is not None:
        warehouse = await fetch_one(
            db, select(AsisWarehouse).where(AsisWarehouse.id == asis_warehouse_id)
        )
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ASIS warehouse tidak ditemukan",
            )
        if asis_company_id is not None and warehouse.asis_company_id not in (None, asis_company_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ASIS warehouse tidak termasuk company yang dipilih",
            )
        if asis_branch_id is not None and warehouse.asis_branch_id not in (None, asis_branch_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ASIS warehouse tidak termasuk branch yang dipilih",
            )


async def _ensure_unique_account_number(
    db: AsyncSession,
    account_number: str,
    *,
    exclude_id: Optional[UUID] = None,
) -> None:
    stmt = select(Bank_Account.id).where(
        Bank_Account.account_number == account_number,
        Bank_Account.deleted_at.is_(None),
    )
    if exclude_id is not None:
        stmt = stmt.where(Bank_Account.id != exclude_id)
    if await row_exists(db, stmt):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nomor rekening '{account_number}' sudah terdaftar",
        )


@router.get("/", response_model=BankAccountListResponse)
async def list_bank_accounts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    search: Optional[str] = Query(None, description="Cari bank, nomor rekening, atau atas nama"),
    is_active: Optional[bool] = Query(None),
    is_default: Optional[bool] = Query(None),
    asis_company_id: Optional[UUID] = Query(None),
    asis_branch_id: Optional[UUID] = Query(None),
    asis_warehouse_id: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Daftar rekening bank (master)."""
    conditions = [Bank_Account.deleted_at.is_(None)]

    if search:
        pattern = f"%{search}%"
        conditions.append(
            Bank_Account.bank_name.ilike(pattern)
            | Bank_Account.account_number.ilike(pattern)
            | Bank_Account.account_holder.ilike(pattern)
        )
    if is_active is not None:
        conditions.append(Bank_Account.is_active.is_(is_active))
    if is_default is not None:
        conditions.append(Bank_Account.is_default.is_(is_default))
    if asis_company_id is not None:
        conditions.append(Bank_Account.asis_company_id == asis_company_id)
    if asis_branch_id is not None:
        conditions.append(Bank_Account.asis_branch_id == asis_branch_id)
    if asis_warehouse_id is not None:
        conditions.append(Bank_Account.asis_warehouse_id == asis_warehouse_id)

    total = (await db.execute(
        select(func.count()).select_from(Bank_Account).where(*conditions)
    )).scalar_one()

    rows = (await db.execute(
        select(Bank_Account)
        .options(*_bank_account_load_options())
        .where(*conditions)
        .order_by(Bank_Account.is_default.desc(), Bank_Account.bank_name.asc())
        .offset(skip)
        .limit(limit)
    )).unique().scalars().all()

    return BankAccountListResponse(data=rows, total=total)


@router.get("/dropdown", response_model=List[BankAccountResponse])
async def dropdown_bank_accounts(
    search: Optional[str] = Query(None),
    asis_company_id: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Rekening aktif untuk dropdown."""
    conditions = [
        Bank_Account.deleted_at.is_(None),
        Bank_Account.is_active.is_(True),
    ]
    if search:
        pattern = f"%{search}%"
        conditions.append(
            Bank_Account.bank_name.ilike(pattern)
            | Bank_Account.account_number.ilike(pattern)
            | Bank_Account.account_holder.ilike(pattern)
        )
    if asis_company_id is not None:
        conditions.append(Bank_Account.asis_company_id == asis_company_id)

    return (await db.execute(
        select(Bank_Account)
        .options(*_bank_account_load_options())
        .where(*conditions)
        .order_by(Bank_Account.is_default.desc(), Bank_Account.bank_name.asc())
    )).unique().scalars().all()


@router.get("/{bank_account_id}", response_model=BankAccountResponse)
async def get_bank_account(
    bank_account_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _fetch_bank_account(db, bank_account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rekening bank tidak ditemukan",
        )
    return account


@router.post("/", response_model=BankAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_bank_account(
    data: BankAccountCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_asis_refs(
        db,
        asis_company_id=data.asis_company_id,
        asis_branch_id=data.asis_branch_id,
        asis_warehouse_id=data.asis_warehouse_id,
    )
    await _ensure_unique_account_number(db, data.account_number)

    account = Bank_Account(**data.model_dump())
    db.add(account)
    await db.commit()

    created = await _fetch_bank_account(db, account.id)
    return created


@router.put("/{bank_account_id}", response_model=BankAccountResponse)
async def update_bank_account(
    bank_account_id: UUID,
    data: BankAccountUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _fetch_bank_account(db, bank_account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rekening bank tidak ditemukan",
        )

    update_data = data.model_dump(exclude_unset=True)

    company_id = update_data.get("asis_company_id", account.asis_company_id)
    branch_id = update_data.get("asis_branch_id", account.asis_branch_id)
    warehouse_id = update_data.get("asis_warehouse_id", account.asis_warehouse_id)

    if any(k in update_data for k in ("asis_company_id", "asis_branch_id", "asis_warehouse_id")):
        await _ensure_asis_refs(
            db,
            asis_company_id=company_id,
            asis_branch_id=branch_id,
            asis_warehouse_id=warehouse_id,
        )

    if "account_number" in update_data and update_data["account_number"]:
        await _ensure_unique_account_number(
            db,
            update_data["account_number"],
            exclude_id=bank_account_id,
        )

    for field, value in update_data.items():
        setattr(account, field, value)

    await db.commit()
    return await _fetch_bank_account(db, bank_account_id)


@router.delete("/{bank_account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank_account(
    bank_account_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _fetch_bank_account(db, bank_account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rekening bank tidak ditemukan",
        )

    account.deleted_at = datetime.utcnow()
    account.is_active = False
    account.is_default = False
    await db.commit()
    return None
