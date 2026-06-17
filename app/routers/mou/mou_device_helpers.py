"""MOU device list filters and Excel export helpers."""

import io
import os
from datetime import datetime
from typing import Optional
from uuid import UUID

import pandas as pd
from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.customer import Customer
from app.models.mou import MOU, MOU_Device
from app.models.serial_number import Serial_Number
from app.schemas.mou_device import MOUDeviceResponse
from app.schemas.serial_number import SerialNumberStatus
from app.utils.eager_loads import mou_device_load_options
from app.utils.excel_export import format_worksheet

def ensure_serial_assignable_to_mou(serial_number: Serial_Number) -> None:
    if serial_number.status == SerialNumberStatus.BROKEN.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Serial number '{serial_number.serial_code}' is marked as BROKEN "
                "and cannot be assigned to MOU"
            ),
        )


MOU_DEVICE_EXPORT_COLUMNS = [
    "MOU Number",
    "Customer Name",
    "Customer PIC",
    "Customer PIC Phone",
    "Customer Phone",
    "Asset Name",
    "Asset Type",
    "Serial Code",
    "Serial Status",
    "Location",
    "Device Status",
]


def build_mou_device_id_query(
    *,
    search: Optional[str] = None,
    mou_id: Optional[UUID] = None,
    customer_id: Optional[UUID] = None,
    status_filter: Optional[str] = None,
):
    conditions = []
    join_serial = False
    join_asset = False
    join_mou = False
    join_customer = False

    if search:
        join_serial = True
        join_asset = True
        join_mou = True
        join_customer = True
        search_term = search.lower()
        conditions.append(
            func.lower(Serial_Number.serial_code).contains(search_term)
            | func.lower(Asset.asset_name).contains(search_term)
            | func.lower(Customer.name).contains(search_term)
            | func.lower(MOU.no_mou).contains(search_term)
        )

    if mou_id:
        conditions.append(MOU_Device.mou_id == mou_id)

    if customer_id:
        join_mou = True
        conditions.append(MOU.customer_id == customer_id)

    if status_filter:
        conditions.append(MOU_Device.status == status_filter)

    id_stmt = select(MOU_Device.id)
    if join_serial:
        id_stmt = id_stmt.outerjoin(Serial_Number, MOU_Device.serial_number_id == Serial_Number.id)
    if join_asset:
        id_stmt = id_stmt.outerjoin(Asset, Serial_Number.asset_id == Asset.id)
    if join_mou:
        id_stmt = id_stmt.outerjoin(MOU, MOU_Device.mou_id == MOU.id)
    if join_customer:
        id_stmt = id_stmt.outerjoin(Customer, MOU.customer_id == Customer.id)
    if conditions:
        id_stmt = id_stmt.where(*conditions)

    return id_stmt


def enrich_mou_device_response(device: MOU_Device) -> MOUDeviceResponse:
    item = MOUDeviceResponse.model_validate(device)
    if device.mou and device.mou.customer:
        item.mou.customer_id = device.mou.customer_id
        item.mou.customer_name = device.mou.customer.name
        item.mou.customer_pic = device.mou.customer.PIC
        item.mou.customer_pic_phone = device.mou.customer.pic_phone
        item.mou.customer_phone = device.mou.customer.phone
    return item


def mou_device_to_export_row(item: MOUDeviceResponse) -> dict:
    mou = item.mou
    serial_number = item.serial_number
    asset = serial_number.asset if serial_number else None

    return {
        "MOU Number": mou.no_mou if mou else "N/A",
        "Customer Name": mou.customer_name if mou else "N/A",
        "Customer PIC": mou.customer_pic if mou else "",
        "Customer PIC Phone": mou.customer_pic_phone if mou else "",
        "Customer Phone": mou.customer_phone if mou else "",
        "Asset Name": asset.asset_name if asset else "N/A",
        "Asset Type": asset.asset_type if asset else "N/A",
        "Serial Code": serial_number.serial_code if serial_number else "N/A",
        "Serial Status": serial_number.status if serial_number else "N/A",
        "Location": item.location or "",
        "Device Status": item.status,
    }


async def fetch_mou_devices_by_ids(db: AsyncSession, id_stmt) -> list[MOU_Device]:
    return (await db.execute(
        select(MOU_Device)
        .options(*mou_device_load_options())
        .where(MOU_Device.id.in_(id_stmt))
    )).scalars().all()


def build_mou_devices_excel_response(rows: list[dict]) -> FileResponse:
    rows.sort(key=lambda row: (row["Customer Name"], row["MOU Number"], row["Serial Code"]))

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=MOU_DEVICE_EXPORT_COLUMNS)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="MOU Devices", index=False)
        format_worksheet(writer.sheets["MOU Devices"])

    output.seek(0)

    date_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"mou_devices_export_{date_suffix}.xlsx"
    temp_file_path = f"uploads/temp_{filename}"
    os.makedirs("uploads", exist_ok=True)

    with open(temp_file_path, "wb") as f:
        f.write(output.getvalue())

    return FileResponse(
        path=temp_file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
