from enum import Enum
from typing import List
from fastapi import Depends, HTTPException, status


# ============================================
#   Actor Level - resolved from role.scope
#   or customer.type
# ============================================

class ActorLevel(str, Enum):
    ADMIN = "ADMIN"
    SALES = "SALES"
    CUSTOMER = "CUSTOMER"
    TECHNICIAN = "TECHNICIAN"
    COMPANY = "COMPANY"
    REGION = "REGION"
    BRANCH = "BRANCH"


# ============================================
#   Granular Permissions
# ============================================

class Permission(str, Enum):
    # Customer
    CREATE_CUSTOMER = "customer.create"
    READ_CUSTOMER = "customer.read"
    UPDATE_CUSTOMER = "customer.update"
    DELETE_CUSTOMER = "customer.delete"

    # MOU
    CREATE_MOU = "mou.create"
    READ_MOU = "mou.read"
    UPDATE_MOU = "mou.update"
    DELETE_MOU = "mou.delete"

    # Order
    CREATE_ORDER = "order.create"
    READ_ORDER = "order.read"
    UPDATE_ORDER = "order.update"
    DELETE_ORDER = "order.delete"

    # Service
    CREATE_SERVICE = "service.create"
    READ_SERVICE = "service.read"
    UPDATE_SERVICE = "service.update"
    DELETE_SERVICE = "service.delete"

    # Transaction
    CREATE_TRANSACTION = "transaction.create"
    READ_TRANSACTION = "transaction.read"
    UPDATE_TRANSACTION = "transaction.update"
    DELETE_TRANSACTION = "transaction.delete"

    # Sales management
    CREATE_SALES = "sales.create"
    READ_SALES = "sales.read"
    UPDATE_SALES = "sales.update"
    DELETE_SALES = "sales.delete"

    # Asset
    CREATE_ASSET = "asset.create"
    READ_ASSET = "asset.read"
    UPDATE_ASSET = "asset.update"
    DELETE_ASSET = "asset.delete"

    # Product
    CREATE_PRODUCT = "product.create"
    READ_PRODUCT = "product.read"
    UPDATE_PRODUCT = "product.update"
    DELETE_PRODUCT = "product.delete"

    # Serial Number
    CREATE_SERIAL_NUMBER = "serial_number.create"
    READ_SERIAL_NUMBER = "serial_number.read"
    UPDATE_SERIAL_NUMBER = "serial_number.update"
    DELETE_SERIAL_NUMBER = "serial_number.delete"


# ============================================
#   Permission Matrix
#   Maps each ActorLevel to its permissions
# ============================================

LEVEL_PERMISSIONS: dict[ActorLevel, List[Permission]] = {
    ActorLevel.ADMIN: [
        # Customer - full access
        Permission.CREATE_CUSTOMER,
        Permission.READ_CUSTOMER,
        Permission.UPDATE_CUSTOMER,
        Permission.DELETE_CUSTOMER,
        # MOU - full access
        Permission.CREATE_MOU,
        Permission.READ_MOU,
        Permission.UPDATE_MOU,
        Permission.DELETE_MOU,
        # Order - full access
        Permission.CREATE_ORDER,
        Permission.READ_ORDER,
        Permission.UPDATE_ORDER,
        Permission.DELETE_ORDER,
        # Service - full access
        Permission.CREATE_SERVICE,
        Permission.READ_SERVICE,
        Permission.UPDATE_SERVICE,
        Permission.DELETE_SERVICE,
        # Transaction - full access
        Permission.CREATE_TRANSACTION,
        Permission.READ_TRANSACTION,
        Permission.UPDATE_TRANSACTION,
        Permission.DELETE_TRANSACTION,
        # Sales - full access
        Permission.CREATE_SALES,
        Permission.READ_SALES,
        Permission.UPDATE_SALES,
        Permission.DELETE_SALES,
        # Asset - full access
        Permission.CREATE_ASSET,
        Permission.READ_ASSET,
        Permission.UPDATE_ASSET,
        Permission.DELETE_ASSET,
        # Product - full access
        Permission.CREATE_PRODUCT,
        Permission.READ_PRODUCT,
        Permission.UPDATE_PRODUCT,
        Permission.DELETE_PRODUCT,
        # Serial Number - full access
        Permission.CREATE_SERIAL_NUMBER,
        Permission.READ_SERIAL_NUMBER,
        Permission.UPDATE_SERIAL_NUMBER,
        Permission.DELETE_SERIAL_NUMBER,
    ],
    ActorLevel.SALES: [
        # Customer - create, read, update
        Permission.CREATE_CUSTOMER,
        Permission.READ_CUSTOMER,
        Permission.UPDATE_CUSTOMER,
        # MOU - create, read, update
        Permission.CREATE_MOU,
        Permission.READ_MOU,
        Permission.UPDATE_MOU,
        # Order - create, read, update
        Permission.CREATE_ORDER,
        Permission.READ_ORDER,
        Permission.UPDATE_ORDER,
        # Sales - read (own sales dashboard)
        Permission.READ_SALES,
        # Service - create, read, update
        Permission.CREATE_SERVICE,
        Permission.READ_SERVICE,
        Permission.UPDATE_SERVICE,
        # Transaction - create, read, update
        Permission.CREATE_TRANSACTION,
        Permission.READ_TRANSACTION,
        Permission.UPDATE_TRANSACTION,
        # Asset - full access
        Permission.CREATE_ASSET,
        Permission.READ_ASSET,
        Permission.UPDATE_ASSET,
        Permission.DELETE_ASSET,
        # Product - full access
        Permission.CREATE_PRODUCT,
        Permission.READ_PRODUCT,
        Permission.UPDATE_PRODUCT,
        Permission.DELETE_PRODUCT,
        # Serial Number - full access
        Permission.CREATE_SERIAL_NUMBER,
        Permission.READ_SERIAL_NUMBER,
        Permission.UPDATE_SERIAL_NUMBER,
        Permission.DELETE_SERIAL_NUMBER,
    ],
    ActorLevel.CUSTOMER: [
        Permission.READ_CUSTOMER,
        Permission.READ_MOU,
        Permission.CREATE_ORDER,
        Permission.READ_ORDER,
        Permission.CREATE_SERVICE,
        Permission.READ_SERVICE,
        Permission.CREATE_TRANSACTION,
        Permission.READ_TRANSACTION,
        Permission.READ_PRODUCT,
    ],
    ActorLevel.TECHNICIAN: [
        # Service - read & update (handle service dari awal sampai selesai)
        Permission.READ_SERVICE,
        Permission.UPDATE_SERVICE,
        # Customer - read (untuk koordinasi dengan customer)
        Permission.READ_CUSTOMER,
        # MOU - read (untuk lihat device & warranty info)
        Permission.READ_MOU,
        # Product - read (untuk lihat spec produk)
        Permission.READ_PRODUCT,
        # Asset - read (untuk lihat detail asset yang di-service)
        Permission.READ_ASSET,
    ],
    ActorLevel.COMPANY: [
        # Customer - read (can see own regions & branches)
        Permission.READ_CUSTOMER,
        # MOU - read
        Permission.READ_MOU,
        # Order - create, read
        Permission.CREATE_ORDER,
        Permission.READ_ORDER,
        # Service - create, read
        Permission.CREATE_SERVICE,
        Permission.READ_SERVICE,
        # Transaction - create, read
        Permission.CREATE_TRANSACTION,
        Permission.READ_TRANSACTION,
        Permission.READ_PRODUCT,
    ],
    ActorLevel.REGION: [
        # Customer - read (can see own branches)
        Permission.READ_CUSTOMER,
        # MOU - read
        Permission.READ_MOU,
        # Order - create, read
        Permission.CREATE_ORDER,
        Permission.READ_ORDER,
        # Service - create, read
        Permission.CREATE_SERVICE,
        Permission.READ_SERVICE,
        # Transaction - create, read
        Permission.CREATE_TRANSACTION,
        Permission.READ_TRANSACTION,
        Permission.READ_PRODUCT,
    ],
    ActorLevel.BRANCH: [
        # Customer - read (own data only)
        Permission.READ_CUSTOMER,
        # MOU - read
        Permission.READ_MOU,
        # Order - create, read
        Permission.CREATE_ORDER,
        Permission.READ_ORDER,
        # Service - create, read
        Permission.CREATE_SERVICE,
        Permission.READ_SERVICE,
        # Transaction - create, read
        Permission.CREATE_TRANSACTION,
        Permission.READ_TRANSACTION,
        Permission.READ_PRODUCT,
    ],
}


# ============================================
#   Helper Functions
# ============================================

def get_user_level(user) -> ActorLevel:
    """
    Resolve the effective ActorLevel from a User object.

    - If user has a role → use role.scope (ADMIN, SALES, or CUSTOMER)
    - If user has a customer → use customer.type (COMPANY, REGION, or BRANCH)
    """
    if user.role is not None:
        try:
            return ActorLevel(user.role.scope)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unknown role scope: {user.role.scope}"
            )

    if user.customer is not None:
        try:
            return ActorLevel(user.customer.type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unknown customer type: {user.customer.type}"
            )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User has no role or customer assigned"
    )


def has_permission(user, permission: Permission) -> bool:
    """Check if a user has a specific permission based on their level."""
    level = get_user_level(user)
    allowed = LEVEL_PERMISSIONS.get(level, [])
    return permission in allowed


def require_permission(*permissions: Permission):
    """
    FastAPI dependency that checks if the current user has ALL of the
    required permissions.

    Usage:
        @router.get("/", dependencies=[Depends(require_permission(Permission.READ_CUSTOMER))])
        async def get_customers(...):
            ...
    """
    from app.dependencies import get_current_active_user

    async def permission_checker(
        current_user=Depends(get_current_active_user),
    ):
        level = get_user_level(current_user)
        allowed = LEVEL_PERMISSIONS.get(level, [])

        for perm in permissions:
            if perm not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied. Required: {perm.value}. Your level: {level.value}"
                )

        return current_user

    return permission_checker