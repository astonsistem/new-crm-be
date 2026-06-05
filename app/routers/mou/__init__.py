from app.routers.mou.mou import router as mou_router
from app.routers.mou.mou_files import router as mou_files_router
from app.routers.mou.mou_products import router as mou_products_router
from app.routers.mou.mou_devices import router as mou_devices_router

__all__ = ["mou_router", "mou_files_router", "mou_products_router", "mou_devices_router"]
