"""
Centralized SQLAlchemy eager-load options for async sessions.

Always use these helpers when a query result will access relationships
during response serialization — lazy loading raises MissingGreenlet in async.
"""

from sqlalchemy.orm import joinedload, selectinload

from app.models.user import User
from app.models.customer import Customer
from app.models.mou import MOU, MOU_Device, MOU_Product
from app.models.serial_number import Serial_Number


def user_joinedload_options():
    """Single User fetch (auth dependency, detail endpoints)."""
    return [
        joinedload(User.role),
        joinedload(User.customer).joinedload(Customer.province),
        joinedload(User.customer).joinedload(Customer.district),
        joinedload(User.asis_company),
        joinedload(User.asis_branch),
        joinedload(User.asis_warehouse),
    ]


def user_selectinload_options():
    """User list / batch fetch."""
    return [
        selectinload(User.role),
        selectinload(User.customer).options(
            selectinload(Customer.province),
            selectinload(Customer.district),
        ),
        selectinload(User.asis_company),
        selectinload(User.asis_branch),
        selectinload(User.asis_warehouse),
    ]


def mou_load_options():
    return [
        joinedload(MOU.customer),
        joinedload(MOU.status_mou),
        joinedload(MOU.created_user),
    ]


def mou_device_load_options():
    return [
        joinedload(MOU_Device.mou).joinedload(MOU.customer),
        joinedload(MOU_Device.serial_number).joinedload(Serial_Number.asset),
    ]


def mou_product_load_options():
    return [
        joinedload(MOU_Product.mou).joinedload(MOU.customer),
        joinedload(MOU_Product.product),
    ]
