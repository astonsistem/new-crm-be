from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.database import Base


class Serial_Number(Base):
    __tablename__ = "serial_numbers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    serial_code = Column(String(100), nullable=False, unique=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    status = Column(
        Enum("ACTIVE", "INACTIVE", "SERVICE", "BROKEN", name="serial_number_status_enum"),
        nullable=False,
    )

    asset = relationship("Asset")