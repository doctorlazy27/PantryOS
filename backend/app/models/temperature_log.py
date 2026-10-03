from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TemperatureLog(Base):
    __tablename__ = "temperature_logs"

    temperature_log_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.batch_id"), nullable=False, index=True)
    inventory_id: Mapped[int | None] = mapped_column(ForeignKey("inventory.inventory_id"), nullable=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.warehouse_id"), nullable=False, index=True)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    storage_zone: Mapped[str] = mapped_column(String(30), nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    minimum_c: Mapped[float] = mapped_column(Float, nullable=False)
    maximum_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    within_range: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)