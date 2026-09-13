from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from app.models.product import Product
from app.schemas.order import SalesOrderCreate
from app.auth.dependencies import get_current_user, require_permission
from fastapi import APIRouter, Depends, HTTPException
from datetime import date, datetime
from app.services.order_status import OrderStatus
from app.models.inventory import Inventory
from app.models.batch import Batch
from app.models.customer import Customer
from app.services.activity import log_activity
from app.services.notification import create_notification, notify_roles
from app.models.warehouse_request import WarehouseRequest
from app.models.salesperson_inventory import SalespersonInventory
from app.models.inventory_movement import InventoryMovement
from app.schemas.warehouse_request import WarehouseRequestCreate


router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


def _fefo_plan(db: Session, product_id: int, warehouse_id: int, quantity: int, lock: bool = False) -> list[dict]:
    query = db.query(Inventory, Batch).join(
        Batch, Inventory.batch_id == Batch.batch_id
    ).filter(
        Inventory.product_id == product_id,
        Inventory.warehouse_id == warehouse_id,
        Inventory.quantity > 0,
        Batch.expiry_date >= date.today(),
    ).order_by(Batch.expiry_date.asc())
    if lock:
        query = query.with_for_update()
    rows = query.all()
    if sum(row.quantity for row, _batch in rows) < quantity:
        return []
    remaining = quantity
    plan = []
    for inventory, batch in rows:
        picked = min(inventory.quantity, remaining)
        plan.append({"inventory_id": inventory.inventory_id, "batch_id": batch.batch_id, "batch_number": batch.batch_number, "quantity": picked, "expiry_date": batch.expiry_date})
        remaining -= picked
        if remaining == 0:
            break
    return plan


@router.get("/warehouse-requests")
def list_warehouse_requests(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_orders")),
):
    query = db.query(WarehouseRequest).filter(WarehouseRequest.warehouse_id == current_user.get("warehouse_id"))
    if current_user["role"] == "salesperson":
        query = query.filter(WarehouseRequest.requested_by == current_user["user_id"])
    rows = query.order_by(WarehouseRequest.created_at.desc()).all()
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


@router.post("/warehouse-requests")
def request_warehouse_stock(
    request: WarehouseRequestCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("request_warehouse_stock")),
):
    if db.query(Product).filter(Product.product_id == request.product_id).first() is None:
        raise HTTPException(status_code=404, detail="Product not found")
    item = WarehouseRequest(product_id=request.product_id, quantity=request.quantity, warehouse_id=current_user.get("warehouse_id"), requested_by=current_user["user_id"])
    db.add(item)
    db.flush()
    notify_roles(db, {"warehouse_worker"}, "Stock request", f"Salesperson stock request #{item.request_id} needs action.", "warehouse_stock_request", current_user.get("warehouse_id"))
    db.commit()
    return {"message": "Stock request sent to warehouse", "request_id": item.request_id, "status": item.status}


@router.post("/sales")
def create_sale_from_salesperson_stock(
    order: SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("create_orders")),
):
    customer = db.query(Customer).filter(Customer.customer_id == order.customer_id).first() if order.customer_id else None
    if customer is None and order.customer_name:
        customer = Customer(name=order.customer_name.strip(), phone="Not provided")
        db.add(customer)
        db.flush()
    if customer is None:
        raise HTTPException(status_code=400, detail="Enter a customer name")
    for item in order.items:
        stock = db.query(SalespersonInventory).filter(
            SalespersonInventory.salesperson_id == current_user["user_id"],
            SalespersonInventory.product_id == item.product_id,
        ).with_for_update().first()
        if stock is None or stock.quantity < item.quantity:
            raise HTTPException(status_code=400, detail=f"You do not have enough received stock for product {item.product_id}")
    sale = SalesOrder(customer_id=customer.customer_id, created_by=current_user["user_id"], warehouse_id=current_user.get("warehouse_id"), status="confirmed")
    db.add(sale)
    db.flush()
    for item in order.items:
        stock = db.query(SalespersonInventory).filter(SalespersonInventory.salesperson_id == current_user["user_id"], SalespersonInventory.product_id == item.product_id).with_for_update().first()
        stock.quantity -= item.quantity
        product = db.query(Product).filter(Product.product_id == item.product_id).first()
        db.add(SalesOrderItem(order_id=sale.order_id, product_id=item.product_id, quantity=item.quantity, unit_price=product.price))
    db.commit()
    return {"message": "Sale recorded", "order_id": sale.order_id, "status": sale.status}


@router.patch("/warehouse-requests/{request_id}/approve")
def approve_warehouse_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("approve_orders")),
):
    item = db.query(WarehouseRequest).filter(WarehouseRequest.request_id == request_id, WarehouseRequest.warehouse_id == current_user.get("warehouse_id"), WarehouseRequest.status == "pending").first()
    if item is None:
        raise HTTPException(status_code=404, detail="Pending stock request not found")
    inventory_rows = db.query(Inventory).join(Batch, Inventory.batch_id == Batch.batch_id).filter(Inventory.product_id == item.product_id, Inventory.warehouse_id == item.warehouse_id, Inventory.quantity > 0, Batch.expiry_date >= date.today()).order_by(Batch.expiry_date.asc()).with_for_update().all()
    if sum(row.quantity for row in inventory_rows) < item.quantity:
        raise HTTPException(status_code=400, detail="Insufficient unexpired warehouse inventory")
    remaining = item.quantity
    for inventory in inventory_rows:
        deduction = min(inventory.quantity, remaining)
        inventory.quantity -= deduction
        db.add(InventoryMovement(
            inventory_id=inventory.inventory_id,
            product_id=inventory.product_id,
            batch_id=inventory.batch_id,
            warehouse_id=inventory.warehouse_id,
            movement_type="ISSUED",
            quantity=deduction,
            actor_id=current_user["user_id"],
            actor_name=current_user["username"],
            reason=f"Warehouse request #{item.request_id} approved using FEFO.",
        ))
        remaining -= deduction
        if remaining == 0:
            break
    personal = db.query(SalespersonInventory).filter(SalespersonInventory.salesperson_id == item.requested_by, SalespersonInventory.product_id == item.product_id).with_for_update().first()
    if personal is None:
        personal = SalespersonInventory(salesperson_id=item.requested_by, product_id=item.product_id, quantity=item.quantity)
        db.add(personal)
    else:
        personal.quantity += item.quantity
    item.status = "approved"
    item.approved_by = current_user["user_id"]
    item.approved_at = datetime.utcnow()
    create_notification(db, item.requested_by, "Stock request approved", f"Request #{item.request_id} was approved and added to your stock.", "warehouse_stock_approved")
    db.commit()
    return {"message": "Stock request approved", "request_id": request_id, "status": item.status}


@router.patch("/warehouse-requests/{request_id}/reject")
def reject_warehouse_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("approve_orders")),
):
    item = db.query(WarehouseRequest).filter(WarehouseRequest.request_id == request_id, WarehouseRequest.warehouse_id == current_user.get("warehouse_id"), WarehouseRequest.status == "pending").first()
    if item is None:
        raise HTTPException(status_code=404, detail="Pending stock request not found")
    item.status = "rejected"
    item.approved_by = current_user["user_id"]
    item.approved_at = datetime.utcnow()
    create_notification(db, item.requested_by, "Stock request rejected", f"Request #{item.request_id} was rejected.", "warehouse_stock_rejected")
    db.commit()
    return {"message": "Stock request rejected", "request_id": request_id, "status": item.status}


@router.get("/")
def list_orders(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_orders"))
):
    query = db.query(SalesOrder).order_by(SalesOrder.created_at.desc())
    query = query.filter(SalesOrder.warehouse_id == current_user.get("warehouse_id"))

    if current_user["role"] == "salesperson":
        query = query.filter(SalesOrder.created_by == current_user["user_id"])

    orders = query.all()

    items_by_order: dict[int, list[dict]] = {}
    order_ids = [order.order_id for order in orders]
    if order_ids:
        rows = db.query(SalesOrderItem.order_id, Product.name, SalesOrderItem.quantity).join(
            Product, SalesOrderItem.product_id == Product.product_id
        ).filter(SalesOrderItem.order_id.in_(order_ids)).all()
        for order_id, product_name, quantity in rows:
            items_by_order.setdefault(order_id, []).append({"product_name": product_name, "quantity": quantity})

    return {
        "orders": [
            {
                "order_id": order.order_id,
                "customer_id": order.customer_id,
                "created_by": order.created_by,
                "status": order.status,
                "created_at": order.created_at,
                "items": items_by_order.get(order.order_id, []),
            }
            for order in orders
        ]
    }


@router.post("/")
def create_order(
    order: SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("create_orders")
    )
):
    customer = db.query(Customer).filter(Customer.customer_id == order.customer_id).first() if order.customer_id else None
    if customer is None and order.customer_name:
        customer = Customer(name=order.customer_name.strip(), phone="Not provided")
        db.add(customer)
        db.flush()
    if customer is None:
        raise HTTPException(status_code=400, detail="Enter a customer name or select a valid customer")

    new_order = SalesOrder(
        customer_id=customer.customer_id,
        created_by=current_user["user_id"],
        warehouse_id=current_user.get("warehouse_id"),
        status="pending"
    )

    db.add(new_order)
    db.flush()
    notify_roles(
        db=db,
        roles={"manager"},
        title="New sales order",
        message=f"Sales order #{new_order.order_id} is waiting for approval.",
        notification_type="order_pending",
        warehouse_id=current_user.get("warehouse_id"),
    )
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="create_order",
    description=f"Created sales order #{new_order.order_id}"
)

    for item in order.items:
        product = db.query(Product).filter(
            Product.product_id == item.product_id
        ).first()

        if product is None:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item.product_id} does not exist"
            )

        order_item = SalesOrderItem(
            order_id=new_order.order_id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=product.price
        )

        db.add(order_item)

    db.commit()
    db.refresh(new_order)

    return {
        "message": "Sales order created successfully",
        "order_id": new_order.order_id,
        "created_by": current_user["username"],
        "status": new_order.status
    }

@router.patch("/{order_id}/approve")
def approve_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("approve_orders")
    )
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail="Only pending orders can be approved"
        )

    if current_user["role"] == "warehouse_worker":
        for item in db.query(SalesOrderItem).filter(SalesOrderItem.order_id == order_id).all():
            available = db.query(Inventory).join(Batch, Inventory.batch_id == Batch.batch_id).filter(
                Inventory.product_id == item.product_id,
                Inventory.warehouse_id == current_user.get("warehouse_id"),
                Inventory.quantity > 0,
                Batch.expiry_date >= date.today(),
            ).with_for_update().all()
            if sum(row.quantity for row in available) < item.quantity:
                raise HTTPException(status_code=400, detail=f"Insufficient unexpired inventory for product {item.product_id}")

    order.status = OrderStatus.APPROVED.value
    create_notification(
        db=db,
        user_id=order.created_by,
        title="Order approved",
        message=f"Sales order #{order.order_id} was approved.",
        notification_type="order_approved",
    )
    notify_roles(
        db=db,
        roles={"warehouse_worker"},
        title="Order ready to dispatch",
        message=f"Sales order #{order.order_id} is approved and ready to dispatch.",
        notification_type="order_ready_to_dispatch",
        warehouse_id=order.warehouse_id,
    )
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="approve_order",
    description=f"Approved sales order #{order.order_id}"
)

    db.commit()
    db.refresh(order)

    return {
        "message": "Order approved successfully",
        "order_id": order.order_id,
        "status": order.status,
        "approved_by": current_user["username"]
    }

@router.patch("/{order_id}/reject")
def reject_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("approve_orders")
    )
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail="Only pending orders can be rejected"
        )

    order.status = OrderStatus.REJECTED.value
    create_notification(
        db=db,
        user_id=order.created_by,
        title="Order rejected",
        message=f"Sales order #{order.order_id} was rejected.",
        notification_type="order_rejected",
    )
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="reject_order",
    description=f"Rejected sales order #{order.order_id}"
)

    db.commit()
    db.refresh(order)

    return {
        "message": "Order rejected successfully",
        "order_id": order.order_id,
        "status": order.status,
        "rejected_by": current_user["username"]
    }


@router.get("/{order_id}")
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("view_orders"))
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if current_user["role"] == "salesperson" and order.created_by != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You can only view your own orders")

    items = db.query(SalesOrderItem, Product.name).join(
        Product, SalesOrderItem.product_id == Product.product_id
    ).filter(
        SalesOrderItem.order_id == order_id
    ).all()

    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "created_by": order.created_by,
        "warehouse_id": order.warehouse_id,
        "status": order.status,
        "created_at": order.created_at,
        "items": [
            {
                "product_id": item.product_id,
                "product_name": product_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price
            }
            for item, product_name in items
        ],
        "fefo_allocations": [
            {
                "product_id": item.product_id,
                "product_name": product_name,
                "allocations": _fefo_plan(db, item.product_id, order.warehouse_id, item.quantity),
            }
            for item, product_name in items
        ] if order.status == OrderStatus.APPROVED.value else [],
    }

@router.patch("/{order_id}/fulfill")
def fulfill_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("fulfill_orders")
    )
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    if order.status != OrderStatus.APPROVED.value:
        raise HTTPException(
            status_code=400,
            detail="Only approved orders can be fulfilled"
        )

    items = db.query(SalesOrderItem).filter(
        SalesOrderItem.order_id == order_id
    ).all()

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Order contains no items"
        )

    requested_quantities = {}
    for item in items:
        requested_quantities[item.product_id] = requested_quantities.get(item.product_id, 0) + item.quantity

    allocations = []
    for product_id, requested_quantity in requested_quantities.items():
        plan = _fefo_plan(db, product_id, current_user.get("warehouse_id"), requested_quantity, lock=True)
        if not plan:
            raise HTTPException(status_code=400, detail=f"Insufficient unexpired stock for product {product_id}")
        inventory_by_id = {row.inventory_id: row for row in db.query(Inventory).filter(Inventory.inventory_id.in_([entry["inventory_id"] for entry in plan])).with_for_update().all()}
        allocations.extend((inventory_by_id[entry["inventory_id"]], entry["quantity"], entry) for entry in plan)

    for inventory, deduction, plan_entry in allocations:
        inventory.quantity -= deduction
        db.add(InventoryMovement(
            inventory_id=inventory.inventory_id,
            product_id=inventory.product_id,
            batch_id=inventory.batch_id,
            warehouse_id=inventory.warehouse_id,
            movement_type="SOLD",
            quantity=deduction,
            actor_id=current_user["user_id"],
            actor_name=current_user["username"],
            reason=f"Sales order #{order.order_id} fulfilled using FEFO batch {plan_entry['batch_number']}.",
        ))

    order.status = OrderStatus.FULFILLED.value
    create_notification(
        db=db,
        user_id=order.created_by,
        title="Order fulfilled",
        message=f"Sales order #{order.order_id} was fulfilled.",
        notification_type="order_fulfilled",
    )
    log_activity(db, current_user["user_id"], current_user["username"], "fulfill_order", f"Fulfilled sales order #{order.order_id} using FEFO allocation.")

    db.commit()
    db.refresh(order)

    return {
        "message": "Order fulfilled successfully",
        "order_id": order.order_id,
        "status": order.status,
        "fulfilled_by": current_user["username"],
        "fefo_allocations": [
            {"inventory_id": inventory.inventory_id, "batch_id": inventory.batch_id, "quantity": deduction, "batch_number": plan_entry["batch_number"], "expiry_date": plan_entry["expiry_date"]}
            for inventory, deduction, plan_entry in allocations
        ]
    }


@router.patch("/{order_id}/confirm-receipt")
def confirm_order_receipt(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("confirm_order_receipt")),
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
        SalesOrder.created_by == current_user["user_id"],
    ).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Your order was not found")
    if order.status != OrderStatus.FULFILLED.value:
        raise HTTPException(status_code=400, detail="Only fulfilled orders can be confirmed as received")
    order.status = "confirmed"
    order.confirmed_by = current_user["user_id"]
    order.confirmed_at = datetime.utcnow()
    create_notification(db, current_user["user_id"], "Order receipt confirmed", f"Sales order #{order.order_id} was marked received.", "order_received")
    db.commit()
    return {"message": "Order receipt confirmed", "order_id": order_id, "status": order.status}