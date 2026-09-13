from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InventoryRecommendation(Base):
    __tablename__ = "inventory_recommendations"
    __table_args__ = (
        UniqueConstraint("recommendation_key", name="uq_inventory_recommendation_key"),
    )

    recommendation_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    recommendation_key: Mapped[str] = mapped_column(String(180), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.warehouse_id"), nullable=False, index=True)
    recommendation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    current_stock: Mapped[int] = mapped_column(Integer, nullable=False)
    average_daily_demand: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    recommended_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
