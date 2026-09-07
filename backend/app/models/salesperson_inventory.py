from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SalespersonInventory(Base):
    __tablename__ = "salesperson_inventory"

    inventory_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    salesperson_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
