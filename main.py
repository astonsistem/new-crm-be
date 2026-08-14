import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.utils.scheduler import start_scheduler, stop_scheduler, run_mou_expiry_check
from app.database import AsyncSessionLocal
from app.services.asis_session import asis_session

from app.routers import (
    auth_router,
    user_router,
    customer_router,
    mou_router,
    mou_files_router,
    mou_products_router,
    mou_devices_router,
    status_router,
    status_service_router,
    role_router,
    category_router,
    product_router,
    asset_router,
    serial_number_router,
    region_router,
    expedition_router,
    service_point_router,
    bank_account_router,
    asis_config_router,
    asis_sync_router,
    asis_company_router,
    asis_branch_router,
    asis_warehouse_router,
)
from app.routers.orders import (
    cart_router,
    order_service_router,
    service_file_router,
    bast_router,
    customer_order_router,
    sales_order_router,
)

# ─── Bootstrap logging before anything else ───────────────────────────────────
settings = get_settings()
setup_logging(debug=settings.debug)
logger = get_logger("app.main")


# ─── Lifespan ────────────────────────────────────────────────────────────────

async def _load_asis_config() -> None:
    """Baca konfigurasi ASIS aktif dari DB dan inisialisasi session singleton."""
    from sqlalchemy import select
    from app.models.asis_config import AsisConfig

    try:
        async with AsyncSessionLocal() as db:
            config = (await db.execute(
                select(AsisConfig).where(AsisConfig.is_active.is_(True))
            )).scalar_one_or_none()
        if config:
            asis_session.configure(config.base_url, config.username, config.password)
            logger.info(
                "ASIS session diinisialisasi dari DB: %s (user: %s)",
                config.base_url, config.username,
            )
        else:
            logger.warning(
                "Tidak ada konfigurasi ASIS aktif di DB. "
                "Tambahkan via POST /asis-config lalu aktifkan."
            )
    except Exception:
        logger.exception("Gagal memuat konfigurasi ASIS saat startup — ASIS tidak akan tersedia.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up %s v%s (debug=%s) …", settings.app_name, settings.api_version, settings.debug)
    start_scheduler()
    await run_mou_expiry_check()
    await _load_asis_config()
    yield
    stop_scheduler()
    logger.info("Application shutdown complete.")


# ─── App factory ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="CRM Backend API",
    description="Backend API for CRM System",
    version=settings.api_version,
    lifespan=lifespan,
    # Hide /docs & /redoc in production
    docs_url="/docs",
    redoc_url="/redoc" if settings.debug else None,
    root_path="/api",
    servers=[{"url": "/api", "description": "API Server"}],
)

# ─── TAMBAHKAN INI (OVERRIDE OPENAPI VERSION) ───────────────────────────────
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    openapi_schema["openapi"] = "3.0.3"  # Force ke 3.0.x
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# ─── Middleware (order matters: outermost executes first) ─────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)


# ─── Global exception handlers ───────────────────────────────────────────────

_HTTP_ERROR_NAMES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    410: "Gone",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Catch all HTTPExceptions; return a consistent JSON error envelope."""
    request_id = getattr(request.state, "request_id", "-")

    if exc.status_code >= 500:
        logger.error(
            "[%s] HTTP %s  %s %s — %s",
            request_id, exc.status_code, request.method, request.url.path, exc.detail,
        )
    else:
        logger.warning(
            "[%s] HTTP %s  %s %s — %s",
            request_id, exc.status_code, request.method, request.url.path, exc.detail,
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": _HTTP_ERROR_NAMES.get(exc.status_code, "Error"),
            "status_code": exc.status_code,
            "detail": exc.detail,
            "request_id": request_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Catch Pydantic 422 validation errors; return per-field details for FE."""
    request_id = getattr(request.state, "request_id", "-")

    errors = []
    for err in exc.errors():
        loc = err.get("loc", [])
        # Skip the first element if it is "body" / "query" / "path" (not useful for FE)
        field_parts = [str(l) for l in loc if l not in ("body", "query", "path", "header")]
        errors.append({
            "field": ".".join(field_parts) if field_parts else ".".join(str(l) for l in loc),
            "message": err["msg"],
            "type": err["type"],
            "input": err.get("input"),
        })

    logger.warning(
        "[%s] 422 VALIDATION  %s %s — %d field error(s)",
        request_id, request.method, request.url.path, len(errors),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "status_code": 422,
            "detail": "Request validation failed. Check the 'errors' field for details.",
            "errors": errors,
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all — hide internal details, log full traceback server-side."""
    request_id = getattr(request.state, "request_id", "-")
    logger.exception(
        "[%s] 500 UNHANDLED  %s %s",
        request_id, request.method, request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "status_code": 500,
            "detail": "An unexpected error occurred. Please contact support.",
            "request_id": request_id,
        },
    )


# ─── Routers ─────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(customer_router)
app.include_router(mou_router)
app.include_router(mou_files_router)
app.include_router(mou_devices_router)
app.include_router(mou_products_router)
app.include_router(status_router)
app.include_router(status_service_router)
app.include_router(role_router)
app.include_router(category_router)
app.include_router(product_router)
app.include_router(asset_router)
app.include_router(serial_number_router)
app.include_router(cart_router)
app.include_router(customer_order_router)
app.include_router(sales_order_router)
app.include_router(order_service_router)
app.include_router(bast_router)
app.include_router(service_file_router)
app.include_router(region_router)
app.include_router(expedition_router)
app.include_router(service_point_router)
app.include_router(bank_account_router)
app.include_router(asis_config_router)
app.include_router(asis_sync_router)
app.include_router(asis_company_router)
app.include_router(asis_branch_router)
app.include_router(asis_warehouse_router)

# ─── Static files ────────────────────────────────────────────────────────────

os.makedirs("uploads", exist_ok=True)
app.mount("/files", StaticFiles(directory="uploads"), name="files")

# ─── Health endpoints ─────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {"message": f"Welcome to {settings.app_name} API"}


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "version": settings.api_version}
