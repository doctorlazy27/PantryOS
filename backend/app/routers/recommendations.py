from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.inventory_recommendation import InventoryRecommendation
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.supplier import Supplier
from app.schemas.inventory_recommendation import RecommendationReview

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
    review: RecommendationReview | None = None,
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
    if item.status != "PENDING":
        raise HTTPException(status_code=409, detail="Recommendation has already been reviewed")
    purchase_order_id = None
    if decision == "approve":
        if review is None or review.supplier_id is None:
            raise HTTPException(status_code=400, detail="Choose a supplier to approve this reorder")
        supplier = db.query(Supplier).filter(Supplier.supplier_id == review.supplier_id).first()
        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found")
        product = db.query(Product).filter(Product.product_id == item.product_id).first()
        if product is None:
            raise HTTPException(status_code=404, detail="Recommended product not found")
        purchase_order = PurchaseOrder(
            supplier_id=supplier.supplier_id,
            created_by=current_user["user_id"],
            warehouse_id=item.warehouse_id,
            status="pending",
        )
        db.add(purchase_order)
        db.flush()
        db.add(PurchaseOrderItem(
            purchase_order_id=purchase_order.purchase_order_id,
            product_id=item.product_id,
            quantity=item.recommended_quantity,
            unit_price=product.price,
        ))
        purchase_order_id = purchase_order.purchase_order_id
    item.status = {"approve": "APPROVED", "reject": "REJECTED", "complete": "COMPLETED"}[decision]
    item.reviewed_by = current_user["user_id"]
    item.reviewed_at = datetime.utcnow()
    db.commit()
    return {"recommendation_id": item.recommendation_id, "status": item.status, "purchase_order_id": purchase_order_id}