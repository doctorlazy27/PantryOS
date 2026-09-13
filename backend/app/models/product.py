from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(50))
    price: Mapped[float] = mapped_column(Float)

    units_per_box: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    reorder_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )