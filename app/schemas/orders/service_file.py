from pydantic import BaseModel, Field, computed_field
from typing import Optional
from uuid import UUID
from datetime import datetime


# Service File Response
class ServiceFileResponse(BaseModel):
    id: UUID
    service_id: UUID
    file_path: str = Field(exclude=True)
    title: Optional[str] = None
    description: Optional[str] = None
    uploaded_at: datetime
    
    @computed_field
    @property
    def file_url(self) -> str:
        return "/" + self.file_path.replace("\\", "/").replace("uploads/", "files/", 1)
    
    class Config:
        from_attributes = True


# Upload Service File
class ServiceFileUpload(BaseModel):
    description: Optional[str] = Field(None, max_length=255)
