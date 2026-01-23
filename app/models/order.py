from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class Order_Customer(Base):
    __tablename__ = "order_customers"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), nullable=False, unique=True)
    mou_id = Column(Integer, ForeignKey("mou.id"), nullable=False)
    order_date = Column(DateTime, nullable=False)
    total = Column(Numeric(15, 2), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    mou = relationship("MOU")


class Order_Customer_Detail(Base):
    __tablename__ = "order_customer_details"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("order_customers.id", ondelete="CASCADE"), nullable=False)
    mou_product_id = Column(Integer, ForeignKey("mou_products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(15, 2), nullable=False)
    subtotal = Column(Numeric(15, 2), nullable=False)

    order_customer = relationship("Order_Customer")
    mou_product = relationship("MOU_Product")


class Order_Service(Base):
    __tablename__ = "order_services"
    
    id = Column(Integer, primary_key=True, index=True)
    service_number = Column(String(50), nullable=False, unique=True)
    mou_id = Column(Integer, ForeignKey("mou.id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    status_service_id = Column(Integer, ForeignKey("status_service.id"), nullable=False)
    description = Column(String(512), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    mou = relationship("MOU")
    status_service = relationship("Status_Service")
    asset = relationship("Asset")
    created_user = relationship("User")


class Service_File(Base):
    __tablename__ = "service_files"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("order_services.id", ondelete="SET NULL"), nullable=False)
    file_path = Column(String(255), nullable=False)
    description = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now())

    order_service = relationship("Order_Service")
