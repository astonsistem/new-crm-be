from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class Bank_Account(Base):
    __tablename__ = "bank_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    bank_name = Column(String(100), nullable=False)
    account_number = Column(String(50), nullable=False)
    account_holder = Column(String(150), nullable=False)
    bank_branch = Column(String(150), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)

    # Optional ASIS scope — null for now, usable later for company/branch/warehouse filtering
    asis_company_id = Column(UUID(as_uuid=True), ForeignKey("asis_companies.id"), nullable=True)
    asis_branch_id = Column(UUID(as_uuid=True), ForeignKey("asis_branches.id"), nullable=True)
    asis_warehouse_id = Column(UUID(as_uuid=True), ForeignKey("asis_warehouses.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    asis_company = relationship("AsisCompany", foreign_keys=[asis_company_id])
    asis_branch = relationship("AsisBranch", foreign_keys=[asis_branch_id])
    asis_warehouse = relationship("AsisWarehouse", foreign_keys=[asis_warehouse_id])
