from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    inventory_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id"),
        nullable=False
    )

    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.warehouse_id"),
        nullable=False
    )

    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.batch_id"),
        nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    expired_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    boxed_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_per_box: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    box_unit_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_box_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0)