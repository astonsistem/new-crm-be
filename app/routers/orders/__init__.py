from app.routers.orders.cart import router as cart_router
from app.routers.orders.service import router as order_service_router
from app.routers.orders.service_file import router as service_file_router
from app.routers.orders.customer_order import router as customer_order_router
from app.routers.orders.sales_order import router as sales_order_router
from app.routers.orders.bast import router as bast_router

__all__ = [
    "cart_router",
    "order_service_router",
    "service_file_router",
    "bast_router",
    "customer_order_router",
    "sales_order_router",
]
