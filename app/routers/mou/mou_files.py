from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from typing import List, Optional
import base64
import os
import shutil
from pathlib import Path

from pydantic import BaseModel

from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.mou import MOU
from app.schemas.mou import MOUFileUploadResponse

router = APIRouter(prefix="/mou-files", tags=["MOU Files"])

ALLOWED_EXTENSIONS = [".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
CONTRACT_FILE_ID = "contract"


class MOUFileInfo(BaseModel):
    id: str
    filename: str
    file_path: str


class MOUFileListResponse(BaseModel):
    data: List[MOUFileInfo]
    total: int


async def _get_mou_or_404(db: AsyncSession, mou_id: UUID) -> MOU:
    mou = (await db.execute(
        select(MOU).where(MOU.id == mou_id, MOU.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not mou:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MOU not found",
        )
    return mou


def _validate_upload_file(file: UploadFile) -> str:
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 10MB limit",
        )
    return file_ext


async def _save_contract_file(mou: MOU, mou_id: UUID, file: UploadFile, db: AsyncSession) -> MOUFileUploadResponse:
    file_ext = _validate_upload_file(file)

    upload_dir = Path("uploads/mou_contracts")
    upload_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{mou_id}_{timestamp}{file_ext}"
    file_path = upload_dir / safe_filename

    if mou.contract_file and os.path.exists(mou.contract_file):
        try:
            os.remove(mou.contract_file)
        except OSError:
            pass

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {exc}",
        ) from exc

    mou.contract_file = str(file_path)
    await db.commit()
    await db.refresh(mou)

    return MOUFileUploadResponse(
        message="File uploaded successfully",
        filename=safe_filename,
        file_path=str(file_path),
        mou_id=str(mou_id),
    )


def read_contract_file_base64(contract_file_path: Optional[str]) -> Optional[str]:
    if not contract_file_path or not os.path.exists(contract_file_path):
        return None
    try:
        with open(contract_file_path, "rb") as file:
            return base64.b64encode(file.read()).decode("utf-8")
    except OSError:
        return None


def _contract_file_info(mou: MOU) -> MOUFileInfo | None:
    if not mou.contract_file:
        return None
    return MOUFileInfo(
        id=CONTRACT_FILE_ID,
        filename=os.path.basename(mou.contract_file),
        file_path=mou.contract_file,
    )


@router.get("/{mou_id}", response_model=MOUFileListResponse)
async def list_mou_files(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Daftar file kontrak MOU (saat ini maksimal 1 file kontrak per MOU)."""
    mou = await _get_mou_or_404(db, mou_id)
    info = _contract_file_info(mou)
    data = [info] if info else []
    return MOUFileListResponse(data=data, total=len(data))


@router.post("/{mou_id}/upload", response_model=MOUFileUploadResponse)
async def upload_mou_contract(
    mou_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload file kontrak MOU.

    Format: .pdf, .docx, .doc, .txt, .png, .jpg, .jpeg, .gif, .bmp, .webp
    Max size: 10MB
    """
    mou = await _get_mou_or_404(db, mou_id)
    return await _save_contract_file(mou, mou_id, file, db)


@router.post("/{mou_id}/upload-contract", response_model=MOUFileUploadResponse, include_in_schema=False)
async def upload_mou_contract_legacy(
    mou_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy alias — gunakan POST /mou-files/{mou_id}/upload"""
    mou = await _get_mou_or_404(db, mou_id)
    return await _save_contract_file(mou, mou_id, file, db)


@router.get("/{mou_id}/download")
async def download_mou_contract(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Download file kontrak MOU."""
    mou = await _get_mou_or_404(db, mou_id)
    return _file_response(mou)


@router.get("/{mou_id}/download/{file_id}")
async def download_mou_contract_by_id(
    mou_id: UUID,
    file_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Download file kontrak MOU (file_id = 'contract' karena hanya 1 file per MOU)."""
    mou = await _get_mou_or_404(db, mou_id)
    if file_id not in (CONTRACT_FILE_ID, str(mou_id)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return _file_response(mou)


@router.get("/{mou_id}/contract", include_in_schema=False)
async def download_mou_contract_legacy(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy alias — gunakan GET /mou-files/{mou_id}/download"""
    mou = await _get_mou_or_404(db, mou_id)
    return _file_response(mou)


def _file_response(mou: MOU) -> FileResponse:
    if not mou.contract_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No contract file uploaded for this MOU",
        )
    if not os.path.exists(mou.contract_file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract file not found on server",
        )
    return FileResponse(
        path=mou.contract_file,
        filename=os.path.basename(mou.contract_file),
        media_type="application/octet-stream",
    )


@router.delete("/{mou_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mou_contract(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Hapus file kontrak MOU."""
    mou = await _get_mou_or_404(db, mou_id)
    await _remove_contract_file(mou, db)
    return None


@router.delete("/{mou_id}/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mou_contract_by_id(
    mou_id: UUID,
    file_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Hapus file kontrak MOU (file_id = 'contract')."""
    mou = await _get_mou_or_404(db, mou_id)
    if file_id not in (CONTRACT_FILE_ID, str(mou_id)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    await _remove_contract_file(mou, db)
    return None


@router.delete("/{mou_id}/contract", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def delete_mou_contract_legacy(
    mou_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy alias — gunakan DELETE /mou-files/{mou_id}"""
    mou = await _get_mou_or_404(db, mou_id)
    await _remove_contract_file(mou, db)
    return None


async def _remove_contract_file(mou: MOU, db: AsyncSession) -> None:
    if not mou.contract_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No contract file to delete",
        )
    if os.path.exists(mou.contract_file):
        try:
            os.remove(mou.contract_file)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete file: {exc}",
            ) from exc
    mou.contract_file = None
    await db.commit()
