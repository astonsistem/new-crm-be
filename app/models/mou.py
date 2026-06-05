from sqlalchemy import Column, Integer, String, Boolean, Numeric, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.database import Base


class MOU(Base):
    __tablename__ = "mou"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    no_mou = Column(String(100), nullable=False, unique=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    status_mou_id = Column(UUID(as_uuid=True), ForeignKey("status_mou.id"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    description = Column(Text, nullable=True)
    end_date = Column(DateTime, nullable=False)
    contract_file = Column(String(255), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    deleted_at = Column(DateTime, nullable=True)

    customer = relationship("Customer")
    created_user = relationship("User")
    status_mou = relationship("Status_MOU")

    @property
    def customer_name(self):
        """Get customer name from the relationship"""
        return self.customer.name if self.customer else None

    @property
    def created_by_name(self):
        """Get creator user name from the relationship"""
        return self.created_user.name if self.created_user else None


class MOU_Product(Base):
    __tablename__ = "mou_products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    mou_id = Column(UUID(as_uuid=True), ForeignKey("mou.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    contract_price = Column(Numeric(15, 2), nullable=False)
    active = Column(Boolean, default=True)
    deleted_at = Column(DateTime, nullable=True)

    mou = relationship("MOU")
    product = relationship("Product")

class MOU_Device(Base):
    __tablename__ = "mou_devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    mou_id = Column(UUID(as_uuid=True), ForeignKey("mou.id"), nullable=False)
    location = Column(String(255), nullable=True)
    serial_number_id = Column(UUID(as_uuid=True), ForeignKey("serial_numbers.id"), nullable=False)
    status = Column(String(50), nullable=False, default="INACTIVE")
    # Possible values: "ACTIVE", "INACTIVE", "SERVICE"

    serial_number = relationship("Serial_Number")
    mou = relationship("MOU")
    service_orders = relationship("Order_Service", back_populates="mou_device")
