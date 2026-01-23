from sqlalchemy import Column, Integer, String
from app.database import Base


class Status_MOU(Base):
    __tablename__ = "status_mou"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(100), nullable=True)


class Status_Service(Base):
    __tablename__ = "status_service"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(100), nullable=True)
