from sqlalchemy import Column, Integer, Numeric, Enum, String, Boolean, ARRAY, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(String(255))
    permissions = Column(ARRAY(String), default=[])

    # Relationships
    users = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"))
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

    # Relationships
    role = relationship("Role", back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(500), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    is_revoked = Column(Boolean, default=False)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(512), nullable=True)

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    address = Column(String(512), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String(100), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    default_price = Column(Numeric(15, 2), nullable=False)
    unit = Column(String(50), nullable=False)
    
    category = relationship("Category")
   
class Status_MOU(Base):
    __tablename__ = "status_mou"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(100), nullable=True)

class Status_Service(Base):
    __tablename__ = "status_service"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(100), nullable=True)

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
    action = Column(Enum("PINJAM", "KEMBALI", "MUTASI","UPDATE",  name="action_enum"), nullable=False)
    description = Column(String(512), nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime, server_default=func.now())

    asset = relationship("Asset")
    mou = relationship("MOU")
    changed_user = relationship("User")

class MOU_Product(Base):
    __tablename__ = "mou_products"

    id = Column(Integer, primary_key=True, index=True)
    mou_id = Column(Integer, ForeignKey("mou.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    contract_price = Column(Numeric(15, 2), nullable=False)
    active = Column(Boolean, default=True)

    mou = relationship("MOU")
    product = relationship("Product")

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