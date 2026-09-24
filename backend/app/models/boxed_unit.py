from uuid import uuid4

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BoxedUnit(Base):
    __tablename__ = "boxed_units"

    boxed_unit_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.inventory_id"), nullable=False, index=True)
    box_code: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=lambda: str(uuid4()))
    scanned_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0)