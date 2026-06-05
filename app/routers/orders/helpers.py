"""Shared order query helpers."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.order import Order_Customer, Order_Customer_Detail, Order_Activity_Log
from app.models.mou import MOU_Product


def order_customer_load_options():
    return [
        joinedload(Order_Customer.mou),
        joinedload(Order_Customer.customer),
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
