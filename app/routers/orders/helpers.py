"""Shared order query helpers."""

from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import User
from app.models.order import (
    Order_Customer,
    Order_Customer_Detail,
    Order_Activity_Log,
    Order_Payment_File,
)
from app.models.mou import MOU_Product
from app.models.customer import Customer
from app.utils.permissions import Permission, has_permission

DELETABLE_ORDER_STATUSES = frozenset({"pending_payment", "waiting_approval"})
DELETABLE_ORDER_STATUS_LABELS = "menunggu pembayaran atau menunggu persetujuan"


def order_customer_load_options():
    return [
        joinedload(Order_Customer.mou),
        joinedload(Order_Customer.customer).joinedload(Customer.province),
        joinedload(Order_Customer.customer).joinedload(Customer.district),
        joinedload(Order_Customer.customer).joinedload(Customer.region),
        joinedload(Order_Customer.customer).joinedload(Customer.sales_user),
        joinedload(Order_Customer.status),
        joinedload(Order_Customer.payment_confirmer),
        joinedload(Order_Customer.shipping_confirmer),
        joinedload(Order_Customer.expedition),
        joinedload(Order_Customer.completer),
        joinedload(Order_Customer.order_details).joinedload(Order_Customer_Detail.mou_product).joinedload(MOU_Product.product),
        joinedload(Order_Customer.payment_files),
        joinedload(Order_Customer.activity_logs).joinedload(Order_Activity_Log.user),
    ]


async def fetch_order_customer(db: AsyncSession, order_id: UUID) -> Order_Customer | None:
    return (await db.execute(
        select(Order_Customer).options(*order_customer_load_options()).where(Order_Customer.id == order_id)
    )).unique().scalar_one_or_none()


async def fetch_order_for_deletion(db: AsyncSession, order_id: UUID) -> Order_Customer | None:
    return (await db.execute(
        select(Order_Customer).options(
            joinedload(Order_Customer.status),
            joinedload(Order_Customer.customer),
            joinedload(Order_Customer.payment_files),
        ).where(Order_Customer.id == order_id)
    )).unique().scalar_one_or_none()


def assert_can_delete_order(order: Order_Customer, current_user: User) -> None:
    """Customer/Sales: hanya order awal. Admin (order.delete): semua status."""
    if current_user.customer_id:
        if order.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak",
            )
        if order.status.name not in DELETABLE_ORDER_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Hanya bisa menghapus order dengan status {DELETABLE_ORDER_STATUS_LABELS}",
            )
        return

    if has_permission(current_user, Permission.DELETE_ORDER):
        return

    if current_user.role and current_user.role.scope == "SALES":
        if not order.customer or order.customer.sales_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akses ditolak",
            )
        if order.status.name not in DELETABLE_ORDER_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Hanya bisa menghapus order dengan status {DELETABLE_ORDER_STATUS_LABELS}",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Izin ditolak",
    )


def delete_order_files_from_disk(payment_files: list[Order_Payment_File]) -> None:
    for payment_file in payment_files:
        file_path = Path(payment_file.file_path)
        if file_path.exists():
            file_path.unlink()
