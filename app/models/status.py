from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.database import Base


class Status_MOU(Base):
    __tablename__ = "status_mou"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(100), nullable=True)


class Status_Service(Base):
    __tablename__ = "status_service"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(100), nullable=True)
