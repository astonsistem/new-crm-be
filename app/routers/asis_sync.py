"""
ASIS Sync Router
----------------
Endpoint untuk preview dan sinkronisasi data Company, Branch, Warehouse dari ASIS ke CRM.

CRUD data yang sudah tersimpan di CRM ada di router terpisah:
  /asis-companies
  /asis-branches
  /asis-warehouses
"""

from typing import Any, List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.asis_sync import AsisBranch, AsisCompany, AsisWarehouse
from app.schemas.asis_sync import (
    AsisBranchPreview,
    AsisCompanyPreview,
    AsisWarehousePreview,
    SyncResult,
)
from app.services.asis_session import asis_session

logger = get_logger("app.asis_sync")

router = APIRouter(prefix="/asis-sync", tags=["ASIS Sync"])


async def _fetch_all_pages(path: str, params: dict | None = None) -> list[dict]:
    """Fetch semua halaman dari ASIS endpoint yang paginated."""
    params = dict(params or {})
    params.setdefault("size", 100)
    all_items: list[dict] = []
    page = 1

    while True:
        params["page"] = page
        data: dict = await asis_session.get(path, params=params)
        items = data.get("items", [])
        all_items.extend(items)
        if page >= data.get("pages", 1):
            break
        page += 1

    return all_items


def _safe(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


# ══════════════════════════════════════════════════════════════════════════════
# COMPANY SYNC
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/company/preview", response_model=AsisCompanyPreview)
async def preview_company(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Ambil data company dari ASIS tanpa menyimpan ke CRM."""
    raw: dict = await asis_session.get("/asis/company/company")
    data = raw.get("data", raw)

    asis_id = str(data.get("id", ""))
    existing = (await db.execute(
        select(AsisCompany).where(AsisCompany.asis_id == asis_id)
    )).scalar_one_or_none()

    return AsisCompanyPreview(
        asis_id=asis_id,
        asis_code=str(data.get("companyCode", "")),
        name=str(data.get("name", "")),
        address=data.get("address"),
        telp=data.get("telp"),
        initial=data.get("initial"),
        pic_name=data.get("picName"),
        pic_phone=data.get("picPhone"),
        pic_email=data.get("picEmail"),
        status=bool(data.get("status", True)),
        already_synced=existing is not None,
    )


@router.post("/company/sync", response_model=SyncResult)
async def sync_company(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Sinkronisasi company dari ASIS ke CRM."""
    raw: dict = await asis_session.get("/asis/company/company")
    data = raw.get("data", raw)

    asis_id = str(data.get("id", ""))
    asis_code = str(data.get("companyCode", ""))
    result = SyncResult(synced_count=0, updated_count=0, skipped_count=0)

    conflict = (await db.execute(
        select(AsisCompany).where(
            AsisCompany.asis_code == asis_code,
            AsisCompany.asis_id != asis_id,
        )
    )).scalar_one_or_none()
    if conflict:
        result.skipped_count = 1
        result.errors.append(
            f"Company code '{asis_code}' sudah digunakan oleh asis_id={conflict.asis_id}. Sync dibatalkan."
        )
        return result

    existing = (await db.execute(
        select(AsisCompany).where(AsisCompany.asis_id == asis_id)
    )).scalar_one_or_none()

    payload = dict(
        asis_id=asis_id,
        asis_code=asis_code,
        name=str(data.get("name", "")),
        address=data.get("address"),
        telp=data.get("telp"),
        initial=data.get("initial"),
        pic_name=data.get("picName"),
        pic_phone=data.get("picPhone"),
        pic_email=data.get("picEmail"),
        pic_jabatan=data.get("picJabatan"),
        ppn=data.get("ppn"),
        logo=data.get("logo"),
        status=bool(data.get("status", True)),
    )

    if existing:
        for k, v in payload.items():
            setattr(existing, k, v)
        result.updated_count = 1
        logger.info("Company diperbarui via sync: asis_id=%s", asis_id)
    else:
        db.add(AsisCompany(**payload))
        result.synced_count = 1
        logger.info("Company baru via sync: asis_id=%s", asis_id)

    await db.commit()
    return result


# ══════════════════════════════════════════════════════════════════════════════
# BRANCH SYNC
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/branch/preview", response_model=List[AsisBranchPreview])
async def preview_branches(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Ambil semua branch dari ASIS tanpa menyimpan ke CRM."""
    raw_items = await _fetch_all_pages("/asis/company/branch/all")
    existing_ids = set((await db.execute(select(AsisBranch.asis_id))).scalars().all())

    return [
        AsisBranchPreview(
            asis_id=str(item.get("id", "")),
            asis_code=str(item.get("branchCode", "")),
            name=str(item.get("name", "")),
            address=item.get("address"),
            telp=item.get("telp"),
            initial=item.get("initial"),
            pic_name=item.get("picName"),
            pic_email=item.get("picEmail"),
            status=bool(item.get("status", True)),
            already_synced=str(item.get("id", "")) in existing_ids,
        )
        for item in raw_items
    ]


@router.post("/branch/sync", response_model=SyncResult)
async def sync_branches(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Sinkronisasi semua branch dari ASIS ke CRM."""
    raw_items = await _fetch_all_pages("/asis/company/branch/all")

    existing_by_id: dict[str, AsisBranch] = {
        r.asis_id: r for r in (await db.execute(select(AsisBranch))).scalars().all()
    }
    existing_codes: dict[str, str] = {
        r.asis_code: r.asis_id for r in existing_by_id.values()
    }

    result = SyncResult(synced_count=0, updated_count=0, skipped_count=0)

    for item in raw_items:
        asis_id = str(item.get("id", ""))
        asis_code = str(item.get("branchCode", ""))

        if asis_code in existing_codes and existing_codes[asis_code] != asis_id:
            result.skipped_count += 1
            result.errors.append(
                f"Branch code '{asis_code}' sudah dipakai asis_id={existing_codes[asis_code]}. Dilewati."
            )
            continue

        raw_company_id = str(_safe(item, "company_id") or "")
        asis_company = None
        if raw_company_id:
            asis_company = (await db.execute(
                select(AsisCompany).where(AsisCompany.asis_id == raw_company_id)
            )).scalar_one_or_none()

        payload = dict(
            asis_id=asis_id,
            asis_code=asis_code,
            asis_company_id=asis_company.id if asis_company else None,
            name=str(item.get("name", "")),
            address=item.get("address"),
            telp=item.get("telp"),
            initial=item.get("initial"),
            pic_name=item.get("picName"),
            pic_email=item.get("picEmail"),
            status=bool(item.get("status", True)),
        )

        if asis_id in existing_by_id:
            branch = existing_by_id[asis_id]
            for k, v in payload.items():
                setattr(branch, k, v)
            result.updated_count += 1
        else:
            db.add(AsisBranch(**payload))
            existing_codes[asis_code] = asis_id
            result.synced_count += 1

    await db.commit()
    logger.info(
        "Branch sync selesai: +%d baru, %d diperbarui, %d dilewati",
        result.synced_count, result.updated_count, result.skipped_count,
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
# WAREHOUSE SYNC
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/warehouse/preview", response_model=List[AsisWarehousePreview])
async def preview_warehouses(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Ambil semua warehouse dari ASIS tanpa menyimpan ke CRM."""
    raw_items = await _fetch_all_pages("/asis/company/warehouse")
    existing_ids = set((await db.execute(select(AsisWarehouse.asis_id))).scalars().all())

    return [
        AsisWarehousePreview(
            asis_id=str(item.get("id", "")),
            asis_code=str(item.get("warehouse_code", "") or item.get("warehouseCode", "")),
            name=str(item.get("name", "")),
            location=item.get("location"),
            pic_name=item.get("picName"),
            pic_email=item.get("picEmail"),
            status=bool(item.get("status", True)),
            is_kongsi=bool(item.get("is_kongsi", False)),
            is_kongsi_vendor=bool(item.get("is_kongsi_vendor", False)),
            already_synced=str(item.get("id", "")) in existing_ids,
        )
        for item in raw_items
    ]


@router.post("/warehouse/sync", response_model=SyncResult)
async def sync_warehouses(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Sinkronisasi semua warehouse dari ASIS ke CRM."""
    raw_items = await _fetch_all_pages("/asis/company/warehouse")

    existing_by_id: dict[str, AsisWarehouse] = {
        r.asis_id: r for r in (await db.execute(select(AsisWarehouse))).scalars().all()
    }
    existing_codes: dict[str, str] = {
        r.asis_code: r.asis_id for r in existing_by_id.values()
    }

    result = SyncResult(synced_count=0, updated_count=0, skipped_count=0)

    for item in raw_items:
        asis_id = str(item.get("id", ""))
        asis_code = str(item.get("warehouse_code", "") or item.get("warehouseCode", ""))

        if asis_code in existing_codes and existing_codes[asis_code] != asis_id:
            result.skipped_count += 1
            result.errors.append(
                f"Warehouse code '{asis_code}' sudah dipakai asis_id={existing_codes[asis_code]}. Dilewati."
            )
            continue

        raw_branch_id = str(_safe(item, "branch_id") or "")
        raw_company_id = str(_safe(item, "company_id") or "")

        asis_branch = None
        if raw_branch_id:
            asis_branch = (await db.execute(
                select(AsisBranch).where(AsisBranch.asis_id == raw_branch_id)
            )).scalar_one_or_none()

        asis_company = None
        if raw_company_id:
            asis_company = (await db.execute(
                select(AsisCompany).where(AsisCompany.asis_id == raw_company_id)
            )).scalar_one_or_none()

        payload = dict(
            asis_id=asis_id,
            asis_code=asis_code,
            asis_branch_id=asis_branch.id if asis_branch else None,
            asis_company_id=asis_company.id if asis_company else None,
            name=str(item.get("name", "")),
            location=item.get("location"),
            pic_name=item.get("picName"),
            pic_email=item.get("picEmail"),
            status=bool(item.get("status", True)),
            is_kongsi=bool(item.get("is_kongsi", False)),
            is_kongsi_vendor=bool(item.get("is_kongsi_vendor", False)),
        )

        if asis_id in existing_by_id:
            wh = existing_by_id[asis_id]
            for k, v in payload.items():
                setattr(wh, k, v)
            result.updated_count += 1
        else:
            db.add(AsisWarehouse(**payload))
            existing_codes[asis_code] = asis_id
            result.synced_count += 1

    await db.commit()
    logger.info(
        "Warehouse sync selesai: +%d baru, %d diperbarui, %d dilewati",
        result.synced_count, result.updated_count, result.skipped_count,
    )
    return result
