from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StockTransfer(Base):
    __tablename__ = "stock_transfers"

    transfer_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id"),
        nullable=False
    )

    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.batch_id"),
        nullable=False
    )

    source_warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.warehouse_id"),
        nullable=False
    )

    destination_warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.warehouse_id"),
        nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=False
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