from pydantic import BaseModel, Field, computed_field
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

# Import service schema for unified response
from app.schemas.orders.service import OrderServiceResponse


# Order Status Response Schema
class OrderStatusResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    
    class Config:
        from_attributes = True


# MOU Basic Response Schema
class MOUBasicResponse(BaseModel):
    id: UUID
    no_mou: str
    
    class Config:
        from_attributes = True


# Customer Basic Response Schema
class CustomerBasicResponse(BaseModel):
    id: UUID
    name: str
    type: str
    
    class Config:
        from_attributes = True


# Product Detail Response Schema
class ProductDetailResponse(BaseModel):
    id: UUID
    product_name: str
    default_price: Decimal
    
    class Config:
        from_attributes = True


# MOU Product Response Schema
class MOUProductDetailResponse(BaseModel):
    id: UUID
    contract_price: Decimal
    product: ProductDetailResponse
    
    class Config:
        from_attributes = True


# Order Detail Response Schema
class OrderCustomerDetailResponse(BaseModel):
    id: UUID
    quantity: int
    price: Decimal
    subtotal: Decimal
    mou_product: MOUProductDetailResponse
    device_name: Optional[str] = None
    serial_number: Optional[str] = None
    
    class Config:
        from_attributes = True


# Payment File Response Schema
class OrderPaymentFileResponse(BaseModel):
    id: UUID
    file_path: str = Field(exclude=True)
    original_filename: str
    description: Optional[str] = None
    uploaded_at: datetime
    
    @computed_field
    @property
    def file_url(self) -> str:
        return "/" + self.file_path.replace("\\", "/").replace("uploads/", "files/", 1)
    
    class Config:
        from_attributes = True


# User Basic Response Schema
class UserBasicResponse(BaseModel):
    id: UUID
    name: str
    username: str
    
    class Config:
        from_attributes = True


# Expedition Basic Response Schema
class ExpeditionBasicResponse(BaseModel):
    id: UUID
    name: str
    url: Optional[str] = None

    class Config:
        from_attributes = True


# Order Activity Log Response
class OrderActivityLogResponse(BaseModel):
    id: UUID
    order_id: UUID
    status: str
    description: Optional[str] = None
    created_at: datetime
    user: Optional[UserBasicResponse] = None

    class Config:
        from_attributes = True


# Order Customer Response
class OrderCustomerResponse(BaseModel):
    id: UUID
    order_number: str
    order_date: datetime
    total: Decimal
    payment_confirmed_at: Optional[datetime] = None
    shipping_confirmed_at: Optional[datetime] = None
    expedition: Optional[ExpeditionBasicResponse] = None
    no_resi: Optional[str] = None
    shipping_date: Optional[datetime] = None
    estimated_arrived: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    
    # Relationships
    mou: MOUBasicResponse
    customer: CustomerBasicResponse
    status: OrderStatusResponse
    payment_confirmer: Optional[UserBasicResponse] = None
    shipping_confirmer: Optional[UserBasicResponse] = None
    completer: Optional[UserBasicResponse] = None
    order_details: List[OrderCustomerDetailResponse] = []
    payment_files: List[OrderPaymentFileResponse] = []
    activity_logs: List[OrderActivityLogResponse] = []
    
    class Config:
        from_attributes = True


# Checkout Item (per-item device info)
class OrderCheckoutItem(BaseModel):
    mou_product_id: UUID
    device_name: Optional[str] = None
    serial_number: Optional[str] = None


# Checkout Request
class OrderCheckoutRequest(BaseModel):
    mou_id: UUID
    items: Optional[List[OrderCheckoutItem]] = None


# Payment Proof Upload
class PaymentProofUpload(BaseModel):
    description: Optional[str] = Field(None, max_length=255)


# Confirm Payment Request
class ConfirmPaymentRequest(BaseModel):
    confirmed: bool = True


# Sales Order Log Response Schema
class SalesOrderLogItem(BaseModel):
    id: UUID
    order_number: str
    order_date: datetime
    completed_at: datetime
    total: Decimal
    customer_name: str
    customer_type: str
    order_details: List[OrderCustomerDetailResponse] = []
    
    class Config:
        from_attributes = True


# Sales Order Log Summary Response
class SalesOrderLogResponse(BaseModel):
    data: List[SalesOrderLogItem]
    total_orders: int
    total_revenue: Decimal


# Sales Performance Summary (for admin view)
class SalesPerformanceItem(BaseModel):
    sales_id: UUID  
    sales_name: str
    sales_username: str
    completed_orders: int
    total_revenue: Decimal
    
    class Config:
        from_attributes = True


# Admin Sales Order Log Response
class AdminSalesOrderLogResponse(BaseModel):
    sales_performance: List[SalesPerformanceItem]
    total_sales_users: int
    overall_orders: int
    overall_revenue: Decimal


# Unified Customer Log Response
class CustomerLogResponse(BaseModel):
    orders: List[OrderCustomerResponse] = []
    services: List[OrderServiceResponse] = []
    payment: List[OrderPaymentFileResponse] = []
    total_orders: int = 0
    total_services: int = 0