from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    asset_name = Column(String(150), nullable=False)
    asset_type = Column(String(50), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    category = relationship("Category")




class Asset_Log(Base):
    __tablename__ = "asset_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    mou_id = Column(UUID(as_uuid=True), ForeignKey("mou.id"), nullable=False)
    action = Column(Enum("PINJAM", "KEMBALI", "MUTASI", "UPDATE", name="action_enum"), nullable=False)
    description = Column(String(512), nullable=True)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime, server_default=func.now())

    asset = relationship("Asset")
    mou = relationship("MOU")
    changed_user = relationship("User")
