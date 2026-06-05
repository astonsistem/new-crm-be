from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from datetime import datetime
import os
from pathlib import Path
from app.dependencies import get_current_active_user, get_db
from app.models import User
from app.models.order import Order_Service, Service_File
from app.schemas.orders.service_file import ServiceFileResponse, ServiceFileUpload

router = APIRouter(prefix="/service-files", tags=["Service Files"])


@router.get("/{service_id}", response_model=List[ServiceFileResponse])
async def get_service_files(
    service_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    service = (await db.execute(
        select(Order_Service).where(Order_Service.id == service_id)
    )).scalar_one_or_none()
    
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service order not found"
        )
    
    files = (await db.execute(
        select(Service_File).where(
            Service_File.service_id == service_id
        ).order_by(Service_File.uploaded_at.desc())
    )).scalars().all()
    
    return files


@router.post("/{service_id}/upload", response_model=List[ServiceFileResponse], status_code=status.HTTP_201_CREATED)
async def upload_service_files(
    service_id: UUID,
    files: List[UploadFile] = File(...),
    title: str = None,
    description: str = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    service = (await db.execute(
        select(Order_Service).where(Order_Service.id == service_id)
    )).scalar_one_or_none()
    
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service order not found"
        )
    
    allowed_extensions = [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".docx", ".doc"]
    max_size = 10 * 1024 * 1024  # 10MB in bytes
    
    uploaded_files = []
    
    upload_dir = Path("uploads/service_files")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    for file in files:
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not allowed for {file.filename}. Allowed types: {', '.join(allowed_extensions)}"
            )
        
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {file.filename} exceeds 10MB limit"
            )
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        safe_filename = f"{service_id}_{timestamp}{file_ext}"
        file_path = upload_dir / safe_filename
        
        try:
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file {file.filename}: {str(e)}"
            )
        
        service_file = Service_File(
            service_id=service_id,
            file_path=str(file_path),
            title=title,
            description=description
        )
        db.add(service_file)
        uploaded_files.append(service_file)
    
    await db.commit()
    
    for file_obj in uploaded_files:
        await db.refresh(file_obj)
    
    return uploaded_files


@router.get("/{service_id}/download/{file_id}")
async def download_service_file(
    service_id: UUID,
    file_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    service_file = (await db.execute(
        select(Service_File).where(
            Service_File.id == file_id,
            Service_File.service_id == service_id
        )
    )).scalar_one_or_none()
    
    if not service_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service file not found"
        )
    
    if not os.path.exists(service_file.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on server"
        )
    
    filename = os.path.basename(service_file.file_path)
    
    return FileResponse(
        path=service_file.file_path,
        filename=filename,
        media_type='application/octet-stream'
    )


@router.delete("/{service_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_file(
    service_id: UUID,
    file_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    service_file = (await db.execute(
        select(Service_File).where(
            Service_File.id == file_id,
            Service_File.service_id == service_id
        )
    )).scalar_one_or_none()
    
    if not service_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service file not found"
        )
    
    if os.path.exists(service_file.file_path):
        try:
            os.remove(service_file.file_path)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete file: {str(e)}"
            )
    
    await db.delete(service_file)
    await db.commit()
    
    return None
