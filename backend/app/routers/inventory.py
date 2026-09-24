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
from app.models.boxed_unit import BoxedUnit
from app.models.inventory_movement import InventoryMovement
from app.schemas.inventory_addition_request import InventoryAdditionRequestCreate
from app.schemas.inventory_addition_approval import InventoryAdditionApproval
from app.schemas.inventory_scan import InventoryScan
from app.services.activity import log_activity
from app.services.notification import create_notification, notify_roles
from datetime import datetime
from app.services.boxed_units import create_boxed_units
from app.services.expiry import process_expiry
from app.services.inventory_guard import require_available_batch


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
                "boxed_units": item.boxed_units,
                "batch_number": db.query(Batch.batch_number).filter(Batch.batch_id == item.batch_id).scalar(),
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
    product = db.query(Product).filter(Product.name.ilike(request.product_name.strip())).first()
    quantity = request.boxed_units * request.units_per_box if request.boxed_units else request.quantity
    if product is None:
        product = Product(name=request.product_name.strip(), category=request.category, quantity=0, unit="units", price=request.unit_price, units_per_box=request.units_per_box, reorder_level=0)
        db.add(product)
        db.flush()

    item = InventoryAdditionRequest(
        product_id=product.product_id,
        warehouse_id=warehouse_id,
        quantity=quantity,
        category=request.category,
        boxed_units=request.boxed_units,
        units_per_box=request.units_per_box,
        unit_price=request.unit_price,
        box_unit_cost=request.box_unit_cost or request.unit_price * request.units_per_box,
        scanned_code=request.scanned_codes[0] if request.scanned_codes else None,
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
    approval: InventoryAdditionApproval,
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
    if approval.expiry_date <= approval.manufacturing_date:
        raise HTTPException(status_code=400, detail="Expiry date must be after manufacturing date")
    if approval.expiry_date <= date.today():
        raise HTTPException(status_code=400, detail="Cannot approve an already expired batch")
    product = db.query(Product).filter(Product.product_id == item.product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Requested product not found")
    product.aisle = approval.aisle
    product.shelf_number = approval.shelf_number
    if item.batch_id is None:
        batch = Batch(product_id=item.product_id, batch_number=approval.batch_number.strip(), manufacturing_date=approval.manufacturing_date, expiry_date=approval.expiry_date)
        db.add(batch)
        db.flush()
        item.batch_id = batch.batch_id
    else:
        batch = db.query(Batch).filter(Batch.batch_id == item.batch_id).with_for_update().first()
        if batch is None:
            raise HTTPException(status_code=404, detail="Requested batch not found")
        batch.batch_number = approval.batch_number.strip()
        batch.manufacturing_date = approval.manufacturing_date
        batch.expiry_date = approval.expiry_date
    existing = db.query(Inventory).filter(
        Inventory.product_id == item.product_id,
        Inventory.batch_id == item.batch_id,
        Inventory.warehouse_id == item.warehouse_id,
    ).with_for_update().first()
    if existing:
        existing.quantity += item.quantity
        existing.boxed_units += item.boxed_units
        existing.total_box_cost += item.boxed_units * (item.box_unit_cost or item.unit_price * item.units_per_box)
        create_boxed_units(db, existing.inventory_id, item.boxed_units, item.units_per_box, item.unit_price, [item.scanned_code] if item.scanned_code else None)
        db.add(InventoryMovement(
            inventory_id=existing.inventory_id,
            product_id=existing.product_id,
            batch_id=existing.batch_id,
            warehouse_id=existing.warehouse_id,
            movement_type="RECEIVED",
            quantity=item.quantity,
            actor_id=current_user["user_id"],
            actor_name=current_user["username"],
            reason=f"Inventory addition request #{item.request_id} approved and merged.",
        ))
    else:
        box_cost = item.box_unit_cost or item.unit_price * item.units_per_box
        inventory = Inventory(product_id=item.product_id, batch_id=item.batch_id, warehouse_id=item.warehouse_id,
            quantity=item.quantity, boxed_units=item.boxed_units, units_per_box=item.units_per_box,
            unit_price=item.unit_price, box_unit_cost=box_cost, total_box_cost=item.boxed_units * box_cost)
        db.add(inventory)
        db.flush()
        create_boxed_units(db, inventory.inventory_id, item.boxed_units, item.units_per_box, item.unit_price, [item.scanned_code] if item.scanned_code else None)
        db.add(InventoryMovement(
            inventory_id=inventory.inventory_id,
            product_id=inventory.product_id,
            batch_id=inventory.batch_id,
            warehouse_id=inventory.warehouse_id,
            movement_type="RECEIVED",
            quantity=inventory.quantity,
            actor_id=current_user["user_id"],
            actor_name=current_user["username"],
            reason=f"Inventory addition request #{item.request_id} approved.",
        ))
    log_activity(db, current_user["user_id"], current_user["username"], "INVENTORY_REQUEST_APPROVED", f"Approved inventory addition request #{item.request_id} for {item.quantity} units.")
    item.status = "approved"
    item.reviewed_by = current_user["user_id"]
    item.reviewed_at = datetime.utcnow()
    log_activity(db, current_user["user_id"], current_user["username"], "INVENTORY_REQUEST_REJECTED", f"Rejected inventory addition request #{item.request_id}.")
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


@router.post("/scan-reduction")
def reduce_inventory_by_scan(
    scan: InventoryScan,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("pick_stock")),
):
    event_key = f"barcode_scan:{scan.scan_event_id}"
    previous = db.query(InventoryMovement).filter(InventoryMovement.event_key == event_key).first()
    if previous:
        product = db.query(Product).filter(Product.product_id == previous.product_id).first()
        return {
            "message": "Scan already applied",
            "scan_event_id": scan.scan_event_id,
            "movement_id": previous.movement_id,
            "product_name": product.name if product else "Unknown product",
            "quantity_removed": previous.quantity,
            "remaining_quantity": db.query(Inventory.quantity).filter(Inventory.inventory_id == previous.inventory_id).scalar(),
            "duplicate": True,
        }

    match = db.query(BoxedUnit, Inventory, Product, Batch).join(
        Inventory, BoxedUnit.inventory_id == Inventory.inventory_id
    ).join(Product, Inventory.product_id == Product.product_id).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).filter(
        Inventory.warehouse_id == current_user.get("warehouse_id"),
        BoxedUnit.remaining_units >= scan.quantity,
        (BoxedUnit.scanned_code == scan.scanned_code) | (BoxedUnit.box_code == scan.scanned_code),
    ).with_for_update().first()
    if match is None:
        raise HTTPException(status_code=404, detail="Barcode is not registered in this warehouse")

    boxed_unit, inventory, product, batch = match
    require_available_batch(db, inventory.batch_id)
    if boxed_unit.remaining_units < scan.quantity:
        raise HTTPException(status_code=400, detail=f"Only {boxed_unit.remaining_units} units remain for this barcode")
    if inventory.quantity < scan.quantity:
        raise HTTPException(status_code=400, detail=f"Only {inventory.quantity} units remain in stock")

    boxed_unit.remaining_units -= scan.quantity
    inventory.quantity -= scan.quantity
    movement = InventoryMovement(
        inventory_id=inventory.inventory_id,
        product_id=inventory.product_id,
        batch_id=inventory.batch_id,
        warehouse_id=inventory.warehouse_id,
        movement_type="PICKED",
        event_key=event_key,
        quantity=scan.quantity,
        actor_id=current_user["user_id"],
        actor_name=current_user["username"],
        reason=f"Barcode scan {scan.scanned_code} reduced stock.",
    )
    db.add(movement)
    db.commit()
    return {
        "message": "Stock reduced",
        "scan_event_id": scan.scan_event_id,
        "movement_id": movement.movement_id,
        "product_name": product.name,
        "batch_number": batch.batch_number,
        "quantity_removed": scan.quantity,
        "remaining_quantity": inventory.quantity,
        "remaining_barcode_units": boxed_unit.remaining_units,
        "duplicate": False,
    }


@router.get("/expiring")
def get_expiring_inventory(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory"))
):
    process_expiry(db)
    days = max(1, min(days, 365))
    warehouse_id = current_user.get("warehouse_id")
    today = date.today()

    inventory = (
        db.query(Inventory, Batch, Product)
        .join(Batch, Inventory.batch_id == Batch.batch_id)
        .join(Product, Inventory.product_id == Product.product_id)
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

    for inventory_record, batch, product in inventory:
        days_remaining = (batch.expiry_date - today).days
        results.append({
            "inventory_id": inventory_record.inventory_id,
            "product_id": inventory_record.product_id,
            "product_name": product.name,
            "warehouse_id": inventory_record.warehouse_id,
            "batch_id": batch.batch_id,
            "batch_number": batch.batch_number,
            "quantity": inventory_record.quantity,
            "expiry_date": batch.expiry_date,
            "status": "URGENT" if days_remaining <= 1 else "EXPIRING SOON",
            "days_remaining": days_remaining,
            "estimated_value": inventory_record.quantity * product.price,
        })

    return {
        "days": days,
        "items": results
    }


@router.get("/expired")
def get_expired_inventory(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory")),
):
    process_expiry(db)
    rows = db.query(Inventory, Batch, Product).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).join(Product, Inventory.product_id == Product.product_id).filter(
        Inventory.warehouse_id == current_user.get("warehouse_id"),
        Batch.expiry_date <= date.today(),
        Inventory.expired_quantity > 0,
    ).order_by(Batch.expiry_date.desc()).all()
    return {"items": [
        {
            "inventory_id": inventory.inventory_id,
            "product_id": product.product_id,
            "product_name": product.name,
            "batch_id": batch.batch_id,
            "batch_number": batch.batch_number,
            "quantity": inventory.expired_quantity,
            "expiry_date": batch.expiry_date,
            "status": "EXPIRED",
            "estimated_value": inventory.expired_quantity * product.price,
        }
        for inventory, batch, product in rows
    ]}


@router.get("/history")
def get_inventory_history(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_inventory")),
):
    movements = db.query(InventoryMovement).filter(
        InventoryMovement.warehouse_id == current_user.get("warehouse_id"),
    ).order_by(InventoryMovement.created_at.desc()).limit(200).all()
    return {"movements": movements}

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

    require_available_batch(db, inventory.batch_id)

    new_inventory = Inventory(
        product_id=inventory.product_id,
        warehouse_id=inventory.warehouse_id,
        batch_id=inventory.batch_id,
        quantity=inventory.quantity,
        boxed_units=inventory.boxed_units,
        units_per_box=inventory.units_per_box,
        unit_price=inventory.unit_price,
        box_unit_cost=inventory.box_unit_cost or inventory.unit_price * inventory.units_per_box,
        total_box_cost=inventory.boxed_units * (inventory.box_unit_cost or inventory.unit_price * inventory.units_per_box),
    )

    if current_user["role"] == "warehouse_worker" and inventory.warehouse_id != current_user.get("warehouse_id"):
        raise HTTPException(status_code=403, detail="You can only add inventory to your assigned warehouse")

    db.add(new_inventory)
    db.flush()
    create_boxed_units(db, new_inventory.inventory_id, inventory.boxed_units, inventory.units_per_box, inventory.unit_price, inventory.scanned_codes)
    db.commit()
    db.refresh(new_inventory)

    return {
        "message": "Inventory created successfully",
        "created_by": current_user["username"],
        "inventory": new_inventory
    }


@router.get("/")
def get_inventory(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    process_expiry(db)
    inventory = db.query(Inventory).filter(
        Inventory.warehouse_id == current_user.get("warehouse_id")
    ).all()

    return {"inventory": [
        {"inventory_id": row.inventory_id, "product_id": row.product_id, "warehouse_id": row.warehouse_id,
         "batch_id": row.batch_id, "quantity": row.quantity, "boxed_units": row.boxed_units,
         "units_per_box": row.units_per_box, "unit_price": row.unit_price,
         "box_unit_cost": row.box_unit_cost, "total_box_cost": row.total_box_cost,
         "expired_quantity": row.expired_quantity,
         "boxed_unit_ids": [box.box_code for box in db.query(BoxedUnit).filter(BoxedUnit.inventory_id == row.inventory_id).all()]}
        for row in inventory
    ]}

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