# models.py
from sqlalchemy import Column, Integer, String, JSON, DateTime
from sqlalchemy.sql import func
from database import Base


class DeviceRecord(Base):
    __tablename__ = "device_records"

    id = Column(Integer, primary_key=True, index=True)
    device = Column(String, index=True)
    name = Column(String)
    metadata_description = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
