from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class Service_Point(Base):
    __tablename__ = "service_points"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False, unique=True)
    address = Column(Text, nullable=True)
    pic_name = Column(String(100), nullable=True)
    pic_phone = Column(String(20), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    user = relationship("User")
    service_orders = relationship("Order_Service", back_populates="service_point")

    @property
    def user_name(self) -> str | None:
        return self.user.name if self.user else None

    @property
    def user_phone(self) -> str | None:
        return self.user.phone if self.user else None
