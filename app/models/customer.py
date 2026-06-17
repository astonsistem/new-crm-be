from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    type = Column(Enum("COMPANY", "REGION", "BRANCH", name="customer_type_enum"), nullable=False)
    name = Column(String(100), nullable=False)
    PIC = Column(String(100), nullable=True)
    pic_phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    address = Column(String(512), nullable=True)
    province_id = Column(UUID(as_uuid=True), ForeignKey("master_provinces.id"), nullable=True)
    district_id = Column(UUID(as_uuid=True), ForeignKey("master_districts.id"), nullable=True)
    pusat_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    region_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    sales_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    pusat = relationship("Customer", remote_side=[id], foreign_keys=[pusat_id])
    region = relationship("Customer", remote_side=[id], foreign_keys=[region_id])
    sales_user = relationship("User", foreign_keys=[sales_id])
    province = relationship("Province", foreign_keys=[province_id])
    district = relationship("District", foreign_keys=[district_id])