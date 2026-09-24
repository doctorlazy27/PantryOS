from datetime import date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.batch import Batch
from app.models.boxed_unit import BoxedUnit
from app.models.counter_allocation import CounterAllocation
from app.models.counter_inventory import CounterInventory
from app.models.counter_sale import CounterSale, CounterSaleItem
from app.models.inventory import Inventory
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.schemas.counter import CheckoutCreate, CounterAllocationCreate
from app.services.activity import log_activity
from app.services.expiry import process_expiry
from app.services.inventory_guard import require_available_batch
from app.services.notification import create_notification, notify_roles

router = APIRouter(prefix="/counter", tags=["Counter"])


def _counter_row(db: Session, row: CounterInventory):
    product = db.query(Product).filter(Product.product_id == row.product_id).first()
    batch = db.query(Batch).filter(Batch.batch_id == row.batch_id).first()
    status = "OUT OF STOCK" if row.quantity <= 0 else "CRITICAL" if row.quantity <= max(1, row.minimum_level // 2) else "LOW" if row.quantity < row.minimum_level else "GOOD"
    return {
        "counter_inventory_id": row.counter_inventory_id,
        "product_id": row.product_id,
        "product_name": product.name if product else "Unknown",
        "category": product.category if product else "General",
        "batch_id": row.batch_id,
        "batch_number": batch.batch_number if batch else "Unknown",
        "quantity": row.quantity,
        "minimum_level": row.minimum_level,
        "unit_price": row.unit_price,
        "expiry_date": batch.expiry_date if batch else None,
        "status": status,
        "last_replenished_at": row.last_replenished_at,
    }


@router.get("/inventory")
def get_counter_inventory(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_counter_inventory"))):
    process_expiry(db)
    rows = db.query(CounterInventory).filter(CounterInventory.warehouse_id == current_user.get("warehouse_id")).all()
    return {"inventory": [_counter_row(db, row) for row in rows]}


@router.get("/allocations")
def get_counter_allocations(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_counter_inventory"))):
    rows = db.query(CounterAllocation).filter(CounterAllocation.warehouse_id == current_user.get("warehouse_id")).order_by(CounterAllocation.created_at.desc()).limit(100).all()
    return {"allocations": [{
        "allocation_id": row.allocation_id,
        "product_id": row.product_id,
        "product_name": db.query(Product.name).filter(Product.product_id == row.product_id).scalar(),
        "quantity": row.quantity,
        "status": row.status,
        "created_at": row.created_at,
    } for row in rows]}


@router.post("/allocations")
def request_counter_allocation(request: CounterAllocationCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("request_counter_allocation"))):
    if db.query(Product).filter(Product.product_id == request.product_id).first() is None:
        raise HTTPException(status_code=404, detail="Product not found")
    item = CounterAllocation(product_id=request.product_id, quantity=request.quantity, warehouse_id=current_user.get("warehouse_id"), requested_by=current_user["user_id"])
    db.add(item)
    db.flush()
    if current_user["role"] == "manager":
        return approve_counter_allocation(item.allocation_id, db, current_user)
    notify_roles(db, {"manager"}, "Counter replenishment required", f"Counter allocation request #{item.allocation_id} needs approval.", "counter_replenishment", current_user.get("warehouse_id"))
    db.commit()
    return {"allocation_id": item.allocation_id, "status": item.status}


@router.patch("/allocations/{allocation_id}/approve")
def approve_counter_allocation(allocation_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("approve_counter_allocation"))):
    allocation = db.query(CounterAllocation).filter(CounterAllocation.allocation_id == allocation_id, CounterAllocation.warehouse_id == current_user.get("warehouse_id"), CounterAllocation.status == "pending").first()
    if allocation is None:
        raise HTTPException(status_code=404, detail="Pending counter allocation not found")
    remaining = allocation.quantity
    warehouse_rows = db.query(Inventory, Batch).join(Batch, Inventory.batch_id == Batch.batch_id).filter(Inventory.warehouse_id == allocation.warehouse_id, Inventory.product_id == allocation.product_id, Inventory.quantity > 0, Batch.expiry_date > date.today()).order_by(Batch.expiry_date.asc()).with_for_update().all()
    if sum(row.quantity for row, _ in warehouse_rows) < remaining:
        raise HTTPException(status_code=400, detail="Not enough valid warehouse stock for this allocation")
    for warehouse_row, batch in warehouse_rows:
        if remaining <= 0:
            break
        require_available_batch(db, batch.batch_id)
        moved = min(remaining, warehouse_row.quantity)
        warehouse_row.quantity -= moved
        counter = db.query(CounterInventory).filter(CounterInventory.warehouse_id == allocation.warehouse_id, CounterInventory.product_id == allocation.product_id, CounterInventory.batch_id == batch.batch_id).with_for_update().first()
        if counter is None:
            product = db.query(Product).filter(Product.product_id == allocation.product_id).first()
            counter = CounterInventory(warehouse_id=allocation.warehouse_id, product_id=allocation.product_id, batch_id=batch.batch_id, quantity=moved, minimum_level=product.reorder_level if product else 0, unit_price=product.price if product else 0, last_replenished_at=datetime.utcnow())
            db.add(counter)
        else:
            counter.quantity += moved
            counter.last_replenished_at = datetime.utcnow()
        db.add(InventoryMovement(inventory_id=warehouse_row.inventory_id, product_id=allocation.product_id, batch_id=batch.batch_id, warehouse_id=allocation.warehouse_id, movement_type="TRANSFER_TO_COUNTER", event_key=f"counter_allocation:{allocation_id}:{batch.batch_id}", quantity=moved, actor_id=current_user["user_id"], actor_name=current_user["username"], reason=f"Counter allocation #{allocation_id} approved."))
        remaining -= moved
    allocation.status = "approved"
    allocation.reviewed_by = current_user["user_id"]
    allocation.reviewed_at = datetime.utcnow()
    log_activity(db, current_user["user_id"], current_user["username"], "COUNTER_ALLOCATION_APPROVED", f"Approved counter allocation #{allocation_id}.")
    db.commit()
    return {"allocation_id": allocation_id, "status": allocation.status, "message": "Stock transferred to counter using FEFO"}


@router.post("/checkout")
def checkout(checkout: CheckoutCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("checkout_counter"))):
    process_expiry(db)
    warehouse_id = current_user.get("warehouse_id")
    prepared = []
    total = 0.0
    for requested in checkout.items:
        match = db.query(CounterInventory, Product, Batch, BoxedUnit, Inventory).join(Product, CounterInventory.product_id == Product.product_id).join(Batch, CounterInventory.batch_id == Batch.batch_id).join(Inventory, (Inventory.product_id == CounterInventory.product_id) & (Inventory.batch_id == CounterInventory.batch_id) & (Inventory.warehouse_id == CounterInventory.warehouse_id)).join(BoxedUnit, BoxedUnit.inventory_id == Inventory.inventory_id).filter(CounterInventory.warehouse_id == warehouse_id, CounterInventory.quantity >= requested.quantity, Batch.expiry_date > date.today(), (BoxedUnit.scanned_code == requested.scanned_code) | (BoxedUnit.box_code == requested.scanned_code)).order_by(Batch.expiry_date.asc()).with_for_update().first()
        if match is None:
            known = db.query(CounterInventory.quantity).join(Batch, CounterInventory.batch_id == Batch.batch_id).join(Inventory, (Inventory.product_id == CounterInventory.product_id) & (Inventory.batch_id == CounterInventory.batch_id) & (Inventory.warehouse_id == CounterInventory.warehouse_id)).join(BoxedUnit, BoxedUnit.inventory_id == Inventory.inventory_id).filter(CounterInventory.warehouse_id == warehouse_id, (BoxedUnit.scanned_code == requested.scanned_code) | (BoxedUnit.box_code == requested.scanned_code)).order_by(Batch.expiry_date.asc()).first()
            if known is not None and known[0] <= 0:
                raise HTTPException(status_code=400, detail="Out of counter stock")
            raise HTTPException(status_code=404, detail="Product not found at counter")
        counter, product, batch, _, warehouse_inventory = match
        prepared.append((counter, product, batch, warehouse_inventory, requested.quantity))
        total += requested.quantity * product.price
    sale = CounterSale(warehouse_id=warehouse_id, bill_number=f"INV-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid4().hex[:4].upper()}", total_amount=total, worker_id=current_user["user_id"])
    db.add(sale)
    db.flush()
    for counter, product, batch, warehouse_inventory, quantity in prepared:
        counter.quantity -= quantity
        db.add(CounterSaleItem(sale_id=sale.sale_id, product_id=product.product_id, batch_id=batch.batch_id, quantity=quantity, unit_price=product.price, line_total=quantity * product.price))
        db.add(InventoryMovement(inventory_id=warehouse_inventory.inventory_id, product_id=product.product_id, batch_id=batch.batch_id, warehouse_id=warehouse_id, movement_type="SOLD_COUNTER", event_key=f"counter_sale:{sale.sale_id}:{product.product_id}:{batch.batch_id}", quantity=quantity, actor_id=current_user["user_id"], actor_name=current_user["username"], reason=f"Counter checkout {sale.bill_number}."))
        if counter.quantity < counter.minimum_level:
            notify_roles(db, {"manager"}, "Counter stock low", f"Counter stock for {product.name} is {counter.quantity}; minimum is {counter.minimum_level}.", "counter_low_stock", warehouse_id)
    log_activity(db, current_user["user_id"], current_user["username"], "COUNTER_CHECKOUT", f"Generated bill {sale.bill_number} for {total:.2f}.")
    db.commit()
    return {"sale_id": sale.sale_id, "bill_number": sale.bill_number, "total_amount": total, "created_at": sale.created_at}


@router.get("/sales")
def get_counter_sales(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_counter_sales"))):
    rows = db.query(CounterSale).filter(CounterSale.warehouse_id == current_user.get("warehouse_id")).order_by(CounterSale.created_at.desc()).limit(100).all()
    return {"sales": [{"sale_id": row.sale_id, "bill_number": row.bill_number, "total_amount": row.total_amount, "worker_id": row.worker_id, "created_at": row.created_at} for row in rows]}


@router.get("/lookup")
def lookup_counter_barcode(barcode: str, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("checkout_counter"))):
    row = db.query(CounterInventory, Product, Batch, BoxedUnit).join(Product, CounterInventory.product_id == Product.product_id).join(Batch, CounterInventory.batch_id == Batch.batch_id).join(Inventory, (Inventory.product_id == CounterInventory.product_id) & (Inventory.batch_id == CounterInventory.batch_id) & (Inventory.warehouse_id == CounterInventory.warehouse_id)).join(BoxedUnit, BoxedUnit.inventory_id == Inventory.inventory_id).filter(CounterInventory.warehouse_id == current_user.get("warehouse_id"), (BoxedUnit.scanned_code == barcode) | (BoxedUnit.box_code == barcode)).order_by(Batch.expiry_date.asc()).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found at counter")
    counter, product, batch, _ = row
    if batch.expiry_date <= date.today():
        raise HTTPException(status_code=400, detail="This product batch has expired")
    if counter.quantity <= 0:
        raise HTTPException(status_code=400, detail="Out of counter stock")
    return {"product_name": product.name, "unit_price": product.price, "available_quantity": counter.quantity, "expiry_date": batch.expiry_date, "batch_number": batch.batch_number}


@router.get("/copilot")
def warehouse_copilot(question: str = "What needs attention today?", db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_counter_inventory"))):
    process_expiry(db)
    counter = db.query(CounterInventory).filter(CounterInventory.warehouse_id == current_user.get("warehouse_id")).all()
    low = [_counter_row(db, row) for row in counter if row.quantity < row.minimum_level]
    priorities = [f"Counter {item['product_name']} is {item['quantity']} units below its minimum." for item in low]
    expiring = db.query(Product.name, Batch.batch_number, Batch.expiry_date).join(Batch, Product.product_id == Batch.product_id).join(Inventory, Inventory.batch_id == Batch.batch_id).filter(Inventory.warehouse_id == current_user.get("warehouse_id"), Batch.expiry_date > date.today()).order_by(Batch.expiry_date.asc()).limit(5).all()
    priorities.extend([f"{name} batch {batch} expires on {expiry.isoformat()}." for name, batch, expiry in expiring])
    if not priorities:
        priorities.append("No urgent counter or expiry risks are currently reported.")
    return {"answer": f"For '{question}', I found {len(low)} counter replenishment item(s) and {len(expiring)} upcoming expiry item(s) in live warehouse data.", "priorities": priorities[:6]}