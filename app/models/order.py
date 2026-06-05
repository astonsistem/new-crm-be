from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.database import Base


class Order_Status(Base):
    __tablename__ = "order_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    orders = relationship("Order_Customer", back_populates="status")


class Order_Customer(Base):
    __tablename__ = "order_customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_number = Column(String(50), nullable=False, unique=True)
    mou_id = Column(UUID(as_uuid=True), ForeignKey("mou.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    order_date = Column(DateTime, nullable=False)
    serial_number = Column(String(50), nullable=True)
    total = Column(Numeric(15, 2), nullable=False)
    status_id = Column(UUID(as_uuid=True), ForeignKey("order_status.id"), nullable=False)
    payment_confirmed_at = Column(DateTime, nullable=True)
    payment_confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    shipping_confirmed_at = Column(DateTime, nullable=True)
    shipping_confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expedition_id = Column(UUID(as_uuid=True), ForeignKey("expeditions.id"), nullable=True)
    no_resi = Column(String(100), nullable=True)
    shipping_date = Column(DateTime, nullable=True)
    estimated_arrived = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    completed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    mou = relationship("MOU")
    customer = relationship("Customer")
    status = relationship("Order_Status", back_populates="orders")
    payment_confirmer = relationship("User", foreign_keys=[payment_confirmed_by])
    shipping_confirmer = relationship("User", foreign_keys=[shipping_confirmed_by])
    expedition = relationship("Expedition")
    completer = relationship("User", foreign_keys=[completed_by])
    order_details = relationship("Order_Customer_Detail", back_populates="order_customer", cascade="all, delete-orphan")
    payment_files = relationship("Order_Payment_File", back_populates="order_customer", cascade="all, delete-orphan")
    activity_logs = relationship("Order_Activity_Log", back_populates="order", cascade="all, delete-orphan", order_by="Order_Activity_Log.created_at")


class Order_Activity_Log(Base):
    __tablename__ = "order_activity_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("order_customers.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Relationships
    order = relationship("Order_Customer", back_populates="activity_logs")
    user = relationship("User")


class Order_Customer_Detail(Base):
    __tablename__ = "order_customer_details"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("order_customers.id", ondelete="CASCADE"), nullable=False)
    mou_product_id = Column(UUID(as_uuid=True), ForeignKey("mou_products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(15, 2), nullable=False)
    subtotal = Column(Numeric(15, 2), nullable=False)
    device_name = Column(String(100), nullable=True)
    serial_number = Column(String(100), nullable=True)

    order_customer = relationship("Order_Customer", back_populates="order_details")
    mou_product = relationship("MOU_Product")


class Order_Cart(Base):
    __tablename__ = "order_carts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    mou_product_id = Column(UUID(as_uuid=True), ForeignKey("mou_products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    added_at = Column(DateTime, server_default=func.now())

    customer = relationship("Customer")
    mou_product = relationship("MOU_Product")


class Order_Service(Base):
    __tablename__ = "order_services"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    service_number = Column(String(50), nullable=False, unique=True)
    mou_id = Column(UUID(as_uuid=True), ForeignKey("mou.id"), nullable=False)
    mou_device_id = Column(UUID(as_uuid=True), ForeignKey("mou_devices.id"), nullable=False)
    status_service_id = Column(UUID(as_uuid=True), ForeignKey("status_service.id"), nullable=False)
    description = Column(Text, nullable=True)
    service_date = Column(DateTime, nullable=True)
    service_date_description = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    mou = relationship("MOU")
    status_service = relationship("Status_Service")
    mou_device = relationship("MOU_Device", back_populates="service_orders")
    created_user = relationship("User")
    service_files = relationship("Service_File", back_populates="order_service", cascade="all, delete-orphan")
    activity_logs = relationship("Service_Activity_Log", back_populates="service", cascade="all, delete-orphan", order_by="Service_Activity_Log.created_at")

    @property
    def service_days(self):
        if self.completed_at and self.created_at:
            return (self.completed_at - self.created_at).days + 1
        return None


class Service_Activity_Log(Base):
    __tablename__ = "service_activity_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    service_id = Column(UUID(as_uuid=True), ForeignKey("order_services.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Relationships
    service = relationship("Order_Service", back_populates="activity_logs")
    user = relationship("User")


class Service_File(Base):
    __tablename__ = "service_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    service_id = Column(UUID(as_uuid=True), ForeignKey("order_services.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(255), nullable=False)
    title = Column(String(255), nullable=True)
    description = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now())

    order_service = relationship("Order_Service", back_populates="service_files")


class Order_Payment_File(Base):
    __tablename__ = "order_payment_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("order_customers.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    title = Column(String(255), nullable=True)
    description = Column(String(255), nullable=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, server_default=func.now())

    # Relationships
    order_customer = relationship("Order_Customer", back_populates="payment_files")
    uploader = relationship("User")
