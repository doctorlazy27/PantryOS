from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    purchase_order_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.supplier_id"),
        nullable=False
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=False
    )

    warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.warehouse_id"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )