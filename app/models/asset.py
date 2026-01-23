from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    mou_id = Column(Integer, ForeignKey("mou.id"), nullable=False)
    asset_code = Column(String(50), nullable=False, unique=True)
    asset_name = Column(String(150), nullable=False)
    condition = Column(String(50), nullable=True)
    location = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    mou = relationship("MOU")


class Asset_Log(Base):
    __tablename__ = "asset_logs"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    mou_id = Column(Integer, ForeignKey("mou.id"), nullable=False)
    action = Column(Enum("PINJAM", "KEMBALI", "MUTASI", "UPDATE", name="action_enum"), nullable=False)
    description = Column(String(512), nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime, server_default=func.now())

    asset = relationship("Asset")
    mou = relationship("MOU")
    changed_user = relationship("User")
