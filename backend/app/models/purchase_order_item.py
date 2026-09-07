from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    purchase_order_item_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.purchase_order_id"),
        nullable=False
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id"),
        nullable=False
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    unit_price: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )