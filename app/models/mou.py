from sqlalchemy import Column, Integer, String, Boolean, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class MOU(Base):
    __tablename__ = "mou"

    id = Column(Integer, primary_key=True, index=True)
    no_mou = Column(String(100), nullable=False, unique=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    status_mou_id = Column(Integer, ForeignKey("status_mou.id"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    contract_file = Column(String(255), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    deleted_at = Column(DateTime, nullable=True)

    customer = relationship("Customer")
    created_user = relationship("User")
    status_mou = relationship("Status_MOU")


class MOU_Product(Base):
    __tablename__ = "mou_products"

    id = Column(Integer, primary_key=True, index=True)
    mou_id = Column(Integer, ForeignKey("mou.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    contract_price = Column(Numeric(15, 2), nullable=False)
    active = Column(Boolean, default=True)

    mou = relationship("MOU")
    product = relationship("Product")
