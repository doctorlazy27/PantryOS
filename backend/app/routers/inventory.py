from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.inventory import Inventory
from app.schemas.inventory import InventoryCreate
from app.auth.dependencies import require_permission
from datetime import date

from app.models.batch import Batch
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.models.inventory_addition_request import InventoryAdditionRequest
from app.schemas.inventory_addition_request import InventoryAdditionRequestCreate
from app.services.activity import log_activity
from app.services.notification import create_notification, notify_roles
from datetime import datetime


router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"]
)


@router.get("/addition-requests")
def list_addition_requests(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory")),
):
    query = db.query(InventoryAdditionRequest).filter(
        InventoryAdditionRequest.warehouse_id == current_user.get("warehouse_id")
    )
    if current_user["role"] == "warehouse_worker":
        query = query.filter(InventoryAdditionRequest.requested_by == current_user["user_id"])
    rows = query.order_by(InventoryAdditionRequest.created_at.desc()).all()
    return {
        "requests": [
            {
                "request_id": item.request_id,
                "product_id": item.product_id,
                "product_name": db.query(Product.name).filter(Product.product_id == item.product_id).scalar(),
                "quantity": item.quantity,
                "status": item.status,
                "requested_by": item.requested_by,
                "created_at": item.created_at,
            }
            for item in rows
        ]
    }


@router.post("/addition-requests")
def request_inventory_addition(
    request: InventoryAdditionRequestCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("submit_inventory_requests")),
):
    warehouse_id = current_user.get("warehouse_id")
    if request.expiry_date <= request.manufacturing_date:
        raise HTTPException(status_code=400, detail="Expiry date must be after manufacturing date")

    product = db.query(Product).filter(Product.name.ilike(request.product_name.strip())).first()
    if product is None:
        product = Product(name=request.product_name.strip(), category="General", quantity=0, unit="units", price=0, reorder_level=0)
        db.add(product)
        db.flush()

    batch = Batch(
        product_id=product.product_id,
        batch_number=request.batch_number.strip(),
        manufacturing_date=request.manufacturing_date,
        expiry_date=request.expiry_date,
    )
    db.add(batch)
    db.flush()

    item = InventoryAdditionRequest(
        product_id=product.product_id,
        batch_id=batch.batch_id,
        warehouse_id=warehouse_id,
        quantity=request.quantity,
        requested_by=current_user["user_id"],
    )
    db.add(item)
    db.flush()
    notify_roles(db, {"manager"}, "Inventory addition request", f"Request #{item.request_id} needs approval.", "inventory_request", warehouse_id)
    db.commit()
    return {"message": "Inventory addition request submitted", "request_id": item.request_id, "status": item.status}


@router.patch("/addition-requests/{request_id}/approve")
def approve_inventory_addition(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("approve_inventory_requests")),
):
    item = db.query(InventoryAdditionRequest).filter(
        InventoryAdditionRequest.request_id == request_id,
        InventoryAdditionRequest.warehouse_id == current_user.get("warehouse_id"),
        InventoryAdditionRequest.status == "pending",
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Pending inventory request not found")
    existing = db.query(Inventory).filter(
        Inventory.product_id == item.product_id,
        Inventory.batch_id == item.batch_id,
        Inventory.warehouse_id == item.warehouse_id,
    ).with_for_update().first()
    if existing:
        existing.quantity += item.quantity
    else:
        db.add(Inventory(product_id=item.product_id, batch_id=item.batch_id, warehouse_id=item.warehouse_id, quantity=item.quantity))
    item.status = "approved"
    item.reviewed_by = current_user["user_id"]
    item.reviewed_at = datetime.utcnow()
    create_notification(db, item.requested_by, "Inventory request approved", f"Inventory request #{item.request_id} was approved.", "inventory_request_approved")
    db.commit()
    return {"message": "Inventory addition approved", "request_id": request_id, "status": item.status}


@router.patch("/addition-requests/{request_id}/reject")
def reject_inventory_addition(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("approve_inventory_requests")),
):
    item = db.query(InventoryAdditionRequest).filter(
        InventoryAdditionRequest.request_id == request_id,
        InventoryAdditionRequest.warehouse_id == current_user.get("warehouse_id"),
        InventoryAdditionRequest.status == "pending",
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Pending inventory request not found")
    item.status = "rejected"
    item.reviewed_by = current_user["user_id"]
    item.reviewed_at = datetime.utcnow()
    create_notification(db, item.requested_by, "Inventory request rejected", f"Inventory request #{item.request_id} was rejected.", "inventory_request_rejected")
    db.commit()
    return {"message": "Inventory addition rejected", "request_id": request_id, "status": item.status}


@router.get("/expiring")
def get_expiring_inventory(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory"))
):
    days = max(1, min(days, 365))
    warehouse_id = current_user.get("warehouse_id")
    today = date.today()

    inventory = (
        db.query(Inventory, Batch)
        .join(Batch, Inventory.batch_id == Batch.batch_id)
        .filter(
            Batch.expiry_date >= today,
            Batch.expiry_date <= today.fromordinal(
                today.toordinal() + days
            ),
            Inventory.warehouse_id == warehouse_id,
        )
        .order_by(Batch.expiry_date.asc())
        .all()
    )

    results = []

    for inventory_record, batch in inventory:
        results.append({
            "inventory_id": inventory_record.inventory_id,
            "product_id": inventory_record.product_id,
            "warehouse_id": inventory_record.warehouse_id,
            "batch_id": batch.batch_id,
            "batch_number": batch.batch_number,
            "quantity": inventory_record.quantity,
            "expiry_date": batch.expiry_date
        })

    return {
        "days": days,
        "items": results
    }

@router.post("/")
def create_inventory(
    inventory: InventoryCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("update_inventory")
    )
):
    if current_user["role"] == "warehouse_worker":
        raise HTTPException(
            status_code=403,
            detail="Workers must submit an inventory addition request for manager approval",
        )

    new_inventory = Inventory(
        product_id=inventory.product_id,
        warehouse_id=inventory.warehouse_id,
        batch_id=inventory.batch_id,
        quantity=inventory.quantity
    )

    if current_user["role"] == "warehouse_worker" and inventory.warehouse_id != current_user.get("warehouse_id"):
        raise HTTPException(status_code=403, detail="You can only add inventory to your assigned warehouse")

    db.add(new_inventory)
    db.commit()
    db.refresh(new_inventory)

    return {
        "message": "Inventory created successfully",
        "created_by": current_user["username"],
        "inventory": new_inventory
    }


@router.get("/")
def get_inventory(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    inventory = db.query(Inventory).filter(
        Inventory.warehouse_id == current_user.get("warehouse_id")
    ).all()

    return {
        "inventory": inventory
    }

@router.get("/warehouse/{warehouse_id}")
def get_warehouse_inventory(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory"))
):
    inventory = db.query(Inventory).filter(
        Inventory.warehouse_id == warehouse_id
    ).filter(Inventory.warehouse_id == current_user.get("warehouse_id")).all()

    return {
        "warehouse_id": warehouse_id,
        "inventory": inventory
    }

@router.get("/product/{product_id}")
def get_product_inventory(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory"))
):
    inventory = db.query(Inventory).filter(
        Inventory.product_id == product_id
    ).filter(Inventory.warehouse_id == current_user.get("warehouse_id")).all()

    return {
        "product_id": product_id,
        "inventory": inventory
    }

@router.get("/fefo/{product_id}")
def get_fefo_stock(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory"))
):
    inventory = (
        db.query(Inventory, Batch)
        .join(Batch, Inventory.batch_id == Batch.batch_id)
        .filter(
            Inventory.product_id == product_id,
            Inventory.warehouse_id == current_user.get("warehouse_id"),
            Inventory.quantity > 0,
            Batch.expiry_date >= date.today()
        )
        .order_by(Batch.expiry_date.asc())
        .all()
    )

    return {
        "product_id": product_id,
        "batches": [
            {
                "inventory_id": inventory_record.inventory_id,
                "warehouse_id": inventory_record.warehouse_id,
                "batch_id": batch.batch_id,
                "batch_number": batch.batch_number,
                "quantity": inventory_record.quantity,
                "expiry_date": batch.expiry_date
            }
            for inventory_record, batch in inventory
        ]
    }