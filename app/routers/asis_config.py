from typing import List
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.asis_config import AsisConfig
from app.schemas.asis_config import (
    AsisConfigCreate,
    AsisConfigResponse,
    AsisConfigUpdate,
)
from app.services.asis_session import asis_session

logger = get_logger("app.asis_config")

router = APIRouter(prefix="/asis-config", tags=["ASIS Config"])


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[AsisConfigResponse])
async def get_all_configs(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Daftar semua konfigurasi koneksi ASIS (password tidak dikembalikan)."""
    configs = (
        await db.execute(select(AsisConfig).order_by(AsisConfig.created_at))
    ).scalars().all()
    return configs


@router.get("/active", response_model=AsisConfigResponse)
async def get_active_config(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Ambil konfigurasi ASIS yang sedang aktif."""
    config = (await db.execute(
        select(AsisConfig).where(AsisConfig.is_active.is_(True))
    )).scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Belum ada konfigurasi ASIS yang aktif.",
        )
    return config


@router.get("/session-status")
async def get_session_status(
    current_user: User = Depends(get_current_active_user),
):
    """Status sesi ASIS: apakah token valid, base_url, berapa detik tersisa, dsb."""
    return asis_session.status()


@router.post("/", response_model=AsisConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_config(
    data: AsisConfigCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Tambah konfigurasi koneksi ASIS baru.

    - `base_url`: URL lengkap ASIS, contoh `https://api-ast.infoku.asia` atau `http://192.168.1.1:3002`
    - Jika `is_active=true`, semua konfigurasi lain otomatis dinonaktifkan
      dan sesi ASIS langsung diinisialisasi dengan konfigurasi ini.
    """
    if data.is_active:
        await db.execute(update(AsisConfig).values(is_active=False))

    config = AsisConfig(**data.model_dump())
    db.add(config)
    await db.commit()
    await db.refresh(config)

    if config.is_active:
        asis_session.configure(config.base_url, config.username, config.password)
        logger.info("AsisSession diinisialisasi dari config baru id=%s", config.id)

    return config


@router.put("/{config_id}", response_model=AsisConfigResponse)
async def update_config(
    config_id: UUID,
    data: AsisConfigUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update konfigurasi ASIS.

    Jika `is_active=true`, konfigurasi lain otomatis dinonaktifkan
    dan sesi ASIS di-reset dengan kredensial terbaru.
    """
    config = (await db.execute(
        select(AsisConfig).where(AsisConfig.id == config_id)
    )).scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config tidak ditemukan.",
        )

    update_data = data.model_dump(exclude_unset=True)

    if update_data.get("is_active"):
        await db.execute(
            update(AsisConfig).where(AsisConfig.id != config_id).values(is_active=False)
        )

    for field, value in update_data.items():
        setattr(config, field, value)

    await db.commit()
    await db.refresh(config)

    if config.is_active:
        asis_session.configure(config.base_url, config.username, config.password)
        logger.info("AsisSession di-reset dari config id=%s setelah update", config.id)

    return config


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(
    config_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Hapus konfigurasi ASIS. Konfigurasi yang sedang aktif tidak bisa dihapus."""
    config = (await db.execute(
        select(AsisConfig).where(AsisConfig.id == config_id)
    )).scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config tidak ditemukan.",
        )
    if config.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak bisa menghapus konfigurasi yang sedang aktif. Aktifkan config lain terlebih dahulu.",
        )

    await db.delete(config)
    await db.commit()
    return None


# ── Activate ──────────────────────────────────────────────────────────────────

@router.post("/{config_id}/activate", response_model=AsisConfigResponse)
async def activate_config(
    config_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Aktifkan konfigurasi tertentu dan nonaktifkan semua yang lain.
    Sesi ASIS langsung di-reset — token lama dibuang,
    login baru dilakukan pada request berikutnya ke ASIS.
    """
    config = (await db.execute(
        select(AsisConfig).where(AsisConfig.id == config_id)
    )).scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config tidak ditemukan.",
        )

    await db.execute(
        update(AsisConfig).where(AsisConfig.id != config_id).values(is_active=False)
    )
    config.is_active = True
    await db.commit()
    await db.refresh(config)

    asis_session.configure(config.base_url, config.username, config.password)
    logger.info(
        "AsisSession diaktifkan dengan config id=%s (%s)",
        config.id, config.base_url,
    )

    return config


# ── Test connection ───────────────────────────────────────────────────────────

class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    base_url: str


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Tes koneksi ke konfigurasi ASIS yang aktif.
    Melakukan login ke ASIS dan memperbarui token di sesi jika berhasil.
    """
    config = (await db.execute(
        select(AsisConfig).where(AsisConfig.is_active.is_(True))
    )).scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Belum ada konfigurasi ASIS yang aktif.",
        )

    base = config.base_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{base}/asis/auth/login",
                data={"username": config.username, "password": config.password},
            )

        if resp.status_code == 200:
            asis_session.configure(config.base_url, config.username, config.password)
            logger.info("Test koneksi ASIS berhasil — config id=%s", config.id)
            return TestConnectionResponse(
                success=True,
                message="Koneksi berhasil. Token ASIS telah diperbarui.",
                base_url=base,
            )

        return TestConnectionResponse(
            success=False,
            message=f"Login ke ASIS gagal: HTTP {resp.status_code} — {resp.text[:200]}",
            base_url=base,
        )

    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Tidak dapat terhubung ke ASIS ({base}): {exc}",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Timeout saat mencoba terhubung ke ASIS ({base}).",
        )
