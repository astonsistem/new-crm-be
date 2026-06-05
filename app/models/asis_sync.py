from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.database import Base


class AsisCompany(Base):
    __tablename__ = "asis_companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    asis_id = Column(String(255), unique=True, nullable=False, index=True)
    asis_code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    telp = Column(String(50), nullable=True)
    initial = Column(String(50), nullable=True)
    pic_name = Column(String(100), nullable=True)
    pic_phone = Column(String(50), nullable=True)
    pic_email = Column(String(100), nullable=True)
    pic_jabatan = Column(String(100), nullable=True)
    ppn = Column(String(50), nullable=True)
    logo = Column(String(500), nullable=True)
    status = Column(Boolean, nullable=False, default=True)
    synced_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    branches = relationship("AsisBranch", back_populates="company")
    warehouses = relationship("AsisWarehouse", back_populates="company")


class AsisBranch(Base):
    __tablename__ = "asis_branches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    asis_id = Column(String(255), unique=True, nullable=False, index=True)
    asis_code = Column(String(100), unique=True, nullable=False, index=True)
    asis_company_id = Column(
        UUID(as_uuid=True), ForeignKey("asis_companies.id"), nullable=True
    )
    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    telp = Column(String(50), nullable=True)
    initial = Column(String(50), nullable=True)
    pic_name = Column(String(100), nullable=True)
    pic_email = Column(String(100), nullable=True)
    status = Column(Boolean, nullable=False, default=True)
    synced_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("AsisCompany", back_populates="branches")
    warehouses = relationship("AsisWarehouse", back_populates="branch")


class AsisWarehouse(Base):
    __tablename__ = "asis_warehouses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    asis_id = Column(String(255), unique=True, nullable=False, index=True)
    asis_code = Column(String(100), unique=True, nullable=False, index=True)
    asis_company_id = Column(
        UUID(as_uuid=True), ForeignKey("asis_companies.id"), nullable=True
    )
    asis_branch_id = Column(
        UUID(as_uuid=True), ForeignKey("asis_branches.id"), nullable=True
    )
    name = Column(String(255), nullable=False)
    location = Column(Text, nullable=True)
    pic_name = Column(String(100), nullable=True)
    pic_email = Column(String(100), nullable=True)
    status = Column(Boolean, nullable=False, default=True)
    is_kongsi = Column(Boolean, nullable=False, default=False)
    is_kongsi_vendor = Column(Boolean, nullable=False, default=False)
    synced_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("AsisCompany", back_populates="warehouses")
    branch = relationship("AsisBranch", back_populates="warehouses")
