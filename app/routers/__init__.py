from app.routers.auth import router as auth_router
from app.routers.user import router as user_router
from app.routers.customer import router as customer_router
from app.routers.mou import mou_router, mou_files_router, mou_products_router, mou_devices_router
from app.routers.status import router as status_router
from app.routers.status_service import router as status_service_router
from app.routers.role import router as role_router
from app.routers.category import router as category_router
from app.routers.product import router as product_router
from app.routers.asset import router as asset_router
from app.routers.serial_number import router as serial_number_router
from app.routers.orders.service import router as order_service_router
from app.routers.region import router as region_router
from app.routers.expedition import router as expedition_router
from app.routers.service_point import router as service_point_router
from app.routers.asis_config import router as asis_config_router
from app.routers.asis_sync import router as asis_sync_router
from app.routers.asis import (
    asis_company_router,
    asis_branch_router,
    asis_warehouse_router,
)

__all__ = [
    "auth_router",
    "user_router",
    "customer_router",
    "mou_router",
    "mou_files_router",
    "mou_products_router",
    "mou_devices_router",
    "status_router",
    "status_service_router",
    "role_router",
    "category_router",
    "product_router",
    "asset_router",
    "serial_number_router",
    "order_service_router",
    "region_router",
    "expedition_router",
    "service_point_router",
    "asis_config_router",
    "asis_sync_router",
    "asis_company_router",
    "asis_branch_router",
    "asis_warehouse_router",
]
