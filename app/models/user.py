from sqlalchemy import Column, Integer, String, Boolean, ARRAY, DateTime, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.database import Base
# NOTE: AsisCompany, AsisBranch, AsisWarehouse diimport via string di relationship
# untuk menghindari circular import


class Role(Base):
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(String(255))
    permissions = Column(ARRAY(String), default=[])
    scope = Column(Enum("ADMIN", "SALES", "CUSTOMER", name="role_scope_enum"), nullable=False)

    # Relationships
    users = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    asis_company_id = Column(UUID(as_uuid=True), ForeignKey("asis_companies.id"), nullable=True)
    asis_branch_id = Column(UUID(as_uuid=True), ForeignKey("asis_branches.id"), nullable=True)
    asis_warehouse_id = Column(UUID(as_uuid=True), ForeignKey("asis_warehouses.id"), nullable=True)

    # Relationships
    customer = relationship("Customer", foreign_keys=[customer_id])
    role = relationship("Role", back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    asis_company = relationship("AsisCompany", foreign_keys=[asis_company_id])
    asis_branch = relationship("AsisBranch", foreign_keys=[asis_branch_id])
    asis_warehouse = relationship("AsisWarehouse", foreign_keys=[asis_warehouse_id])


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(500), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    is_revoked = Column(Boolean, default=False)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")
