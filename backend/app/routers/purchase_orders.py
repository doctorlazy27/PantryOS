from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_item import PurchaseOrderItem
from app.schemas.purchase_order import PurchaseOrderCreate
from app.auth.dependencies import require_permission
from app.models.batch import Batch
from app.models.inventory import Inventory
from app.models.warehouse import Warehouse
from app.models.supplier import Supplier
from app.schemas.receiving import ReceivePurchaseOrder


router = APIRouter(
    prefix="/purchase-orders",
    tags=["Purchase Orders"]
)

@router.patch("/{purchase_order_id}/receive")
def receive_purchase_order(
    purchase_order_id: int,
    receiving: ReceivePurchaseOrder,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("receive_purchase_orders")
    )
):
    purchase_order = db.query(PurchaseOrder).filter(
        PurchaseOrder.purchase_order_id == purchase_order_id,
        PurchaseOrder.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if purchase_order is None:
        raise HTTPException(
            status_code=404,
            detail="Purchase order not found"
        )

    if purchase_order.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only pending purchase orders can be received"
        )

    if db.query(Warehouse).filter(Warehouse.warehouse_id == receiving.warehouse_id).first() is None:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    if receiving.warehouse_id != current_user.get("warehouse_id"):
        raise HTTPException(status_code=403, detail="You can only receive stock into your assigned warehouse")

    resolved_items = []
    for item in receiving.items:
        product = db.query(Product).filter(Product.product_id == item.product_id).first() if item.product_id else None
        if product is None and item.product_name:
            product = db.query(Product).filter(Product.name.ilike(item.product_name.strip())).first()
        if product is None:
            raise HTTPException(status_code=404, detail=f"Product '{item.product_name or item.product_id}' does not exist")
        resolved_items.append((item, product))

    purchase_items = db.query(PurchaseOrderItem).filter(
        PurchaseOrderItem.purchase_order_id == purchase_order_id
    ).all()
    ordered = {item.product_id: item.quantity for item in purchase_items}
    received = {}
    for item, product in resolved_items:
        received[product.product_id] = received.get(product.product_id, 0) + item.quantity

    if set(received) != set(ordered):
        raise HTTPException(status_code=400, detail="Received products must match the purchase order")
    if received != ordered:
        raise HTTPException(status_code=400, detail="Received quantities must match the purchase order")

    for item, product in resolved_items:
        if item.expiry_date <= item.manufacturing_date:
            raise HTTPException(status_code=400, detail="Expiry date must be after manufacturing date")

        batch = Batch(
            product_id=product.product_id,
            batch_number=item.batch_number,
            manufacturing_date=item.manufacturing_date,
            expiry_date=item.expiry_date
        )

        db.add(batch)
        db.flush()

        inventory = Inventory(
            product_id=product.product_id,
            warehouse_id=receiving.warehouse_id,
            batch_id=batch.batch_id,
            quantity=item.quantity
        )

        db.add(inventory)

    purchase_order.status = "received"

    db.commit()
    db.refresh(purchase_order)

    return {
        "message": "Purchase order received successfully",
        "purchase_order_id": purchase_order.purchase_order_id,
        "warehouse_id": receiving.warehouse_id,
        "received_by": current_user["username"],
        "status": purchase_order.status
    }





@router.post("/")
def create_purchase_order(
    purchase_order: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("create_purchase_orders")
    )
):
    supplier = db.query(Supplier).filter(Supplier.supplier_id == purchase_order.supplier_id).first() if purchase_order.supplier_id else None
    if supplier is None and purchase_order.supplier_name:
        supplier = Supplier(name=purchase_order.supplier_name.strip(), phone="Not provided")
        db.add(supplier)
        db.flush()
    if supplier is None:
        raise HTTPException(status_code=400, detail="Enter a supplier name or select a valid supplier")

    new_order = PurchaseOrder(
        supplier_id=supplier.supplier_id,
        created_by=current_user["user_id"],
        warehouse_id=current_user.get("warehouse_id"),
        status="pending"
    )

    db.add(new_order)
    db.flush()

    for item in purchase_order.items:
        product = db.query(Product).filter(Product.product_id == item.product_id).first() if item.product_id else None
        if product is None and item.product_name:
            product = db.query(Product).filter(Product.name.ilike(item.product_name.strip())).first()
        if product is None and item.product_name:
            product = Product(name=item.product_name.strip(), category="General", quantity=0, unit="units", price=0, reorder_level=0)
            db.add(product)
            db.flush()

        if product is None:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item.product_id} does not exist"
            )

        order_item = PurchaseOrderItem(
            purchase_order_id=new_order.purchase_order_id,
            product_id=product.product_id,
            quantity=item.quantity,
            unit_price=product.price
        )

        db.add(order_item)

    db.commit()
    db.refresh(new_order)

    return {
        "message": "Purchase order created successfully",
        "purchase_order_id": new_order.purchase_order_id,
        "created_by": current_user["username"],
        "status": new_order.status
    }