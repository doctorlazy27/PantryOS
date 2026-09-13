from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.inventory_recommendation import InventoryRecommendation
from app.models.product import Product

router = APIRouter(prefix="/inventory/recommendations", tags=["Inventory recommendations"])


@router.get("/")
def list_recommendations(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory_recommendations")),
):
    rows = db.query(InventoryRecommendation, Product.name).join(
        Product, Product.product_id == InventoryRecommendation.product_id
    ).filter(
        InventoryRecommendation.warehouse_id == current_user.get("warehouse_id"),
    ).order_by(InventoryRecommendation.created_at.desc()).all()
    return {"recommendations": [
        {
            "recommendation_id": item.recommendation_id,
            "recommendation_key": item.recommendation_key,
            "product_id": item.product_id,
            "product_name": name,
            "warehouse_id": item.warehouse_id,
            "recommendation_type": item.recommendation_type,
            "current_stock": item.current_stock,
            "average_daily_demand": item.average_daily_demand,
            "recommended_quantity": item.recommended_quantity,
            "reason": item.reason,
            "status": item.status,
            "created_at": item.created_at,
            "reviewed_by": item.reviewed_by,
            "reviewed_at": item.reviewed_at,
        }
        for item, name in rows
    ]}


@router.patch("/{recommendation_id}/{decision}")
def review_recommendation(
    recommendation_id: int,
    decision: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("review_inventory_recommendations")),
):
    if decision not in {"approve", "reject", "complete"}:
        raise HTTPException(status_code=400, detail="Decision must be approve, reject, or complete")
    item = db.query(InventoryRecommendation).filter(
        InventoryRecommendation.recommendation_id == recommendation_id,
        InventoryRecommendation.warehouse_id == current_user.get("warehouse_id"),
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    item.status = {"approve": "APPROVED", "reject": "REJECTED", "complete": "COMPLETED"}[decision]
    item.reviewed_by = current_user["user_id"]
    item.reviewed_at = datetime.utcnow()
    db.commit()
    return {"recommendation_id": item.recommendation_id, "status": item.status}