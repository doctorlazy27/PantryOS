from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.inventory import Inventory
from app.models.warehouse import Warehouse
from app.models.stock_transfer import StockTransfer
from app.schemas.stock_transfer import StockTransferCreate
from app.auth.dependencies import require_permission
from app.models.inventory import Inventory
from app.services.activity import log_activity


router = APIRouter(
    prefix="/stock-transfers",
    tags=["Stock Transfers"]
)


@router.patch("/{transfer_id}/approve")
def approve_stock_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("approve_stock_transfers")
    )
):
    transfer = db.query(StockTransfer).filter(
        StockTransfer.transfer_id == transfer_id
    ).first()

    if transfer is None:
        raise HTTPException(
            status_code=404,
            detail="Stock transfer not found"
        )

    if current_user["role"] == "manager" and current_user.get("warehouse_id") not in {
        transfer.source_warehouse_id,
        transfer.destination_warehouse_id,
    }:
        raise HTTPException(status_code=403, detail="This transfer does not involve your warehouse")

    if transfer.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only pending transfers can be approved"
        )

    source_inventory = db.query(Inventory).filter(
        Inventory.product_id == transfer.product_id,
        Inventory.batch_id == transfer.batch_id,
        Inventory.warehouse_id == transfer.source_warehouse_id
    ).with_for_update().first()

    if source_inventory is None:
        raise HTTPException(
            status_code=404,
            detail="Source inventory not found"
        )

    if source_inventory.quantity < transfer.quantity:
        raise HTTPException(
            status_code=400,
            detail="Insufficient stock for transfer"
        )

    destination_inventory = db.query(Inventory).filter(
        Inventory.product_id == transfer.product_id,
        Inventory.batch_id == transfer.batch_id,
        Inventory.warehouse_id == transfer.destination_warehouse_id
    ).first()

    source_inventory.quantity -= transfer.quantity

    if destination_inventory:
        destination_inventory.quantity += transfer.quantity
    else:
        destination_inventory = Inventory(
            product_id=transfer.product_id,
            warehouse_id=transfer.destination_warehouse_id,
            batch_id=transfer.batch_id,
            quantity=transfer.quantity
        )

        db.add(destination_inventory)

    transfer.status = "completed"
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="complete_stock_transfer",
    description=f"Completed stock transfer #{transfer.transfer_id}"
)
    

    db.commit()
    db.refresh(transfer)

    return {
        "message": "Stock transfer completed successfully",
        "transfer_id": transfer.transfer_id,
        "status": transfer.status,
        "approved_by": current_user["username"]
    }

@router.post("/")
def create_stock_transfer(
    transfer: StockTransferCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("request_stock_transfer")
    )
):
    if transfer.source_warehouse_id == transfer.destination_warehouse_id:
        raise HTTPException(
            status_code=400,
            detail="Source and destination warehouses must be different"
        )

    if current_user["role"] == "salesperson" and transfer.source_warehouse_id != current_user.get("warehouse_id"):
        raise HTTPException(status_code=403, detail="You can only initiate transfers from your assigned warehouse")

    if db.query(Warehouse).filter(Warehouse.warehouse_id.in_([
        transfer.source_warehouse_id,
        transfer.destination_warehouse_id,
    ])).count() != 2:
        raise HTTPException(status_code=404, detail="Source or destination warehouse not found")

    inventory = db.query(Inventory).filter(
        Inventory.product_id == transfer.product_id,
        Inventory.batch_id == transfer.batch_id,
        Inventory.warehouse_id == transfer.source_warehouse_id
    ).first()

    if inventory is None:
        raise HTTPException(
            status_code=404,
            detail="Source inventory not found"
        )

    if inventory.quantity < transfer.quantity:
        raise HTTPException(
            status_code=400,
            detail="Insufficient stock for transfer"
        )

    new_transfer = StockTransfer(
        product_id=transfer.product_id,
        batch_id=transfer.batch_id,
        source_warehouse_id=transfer.source_warehouse_id,
        destination_warehouse_id=transfer.destination_warehouse_id,
        quantity=transfer.quantity,
        created_by=current_user["user_id"],
        status="pending"
    )

    db.add(new_transfer)
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="request_stock_transfer",
    description=f"Requested stock transfer #{new_transfer.transfer_id}"
)
    db.commit()
    db.refresh(new_transfer)

    return {
        "message": "Stock transfer request created",
        "transfer_id": new_transfer.transfer_id,
        "status": new_transfer.status,
        "created_by": current_user["username"]
    }



@router.patch("/{transfer_id}/reject")
def reject_stock_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("approve_stock_transfers")
    )
):
    transfer = db.query(StockTransfer).filter(
        StockTransfer.transfer_id == transfer_id
    ).first()

    if transfer is None:
        raise HTTPException(
            status_code=404,
            detail="Stock transfer not found"
        )

    if current_user["role"] == "manager" and current_user.get("warehouse_id") not in {
        transfer.source_warehouse_id,
        transfer.destination_warehouse_id,
    }:
        raise HTTPException(status_code=403, detail="This transfer does not involve your warehouse")

    if transfer.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only pending transfers can be rejected"
        )

    transfer.status = "rejected"
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="reject_stock_transfer",
    description=f"Rejected stock transfer #{transfer.transfer_id}"
)
    
    db.commit()
    db.refresh(transfer)

    return {
        "message": "Stock transfer rejected",
        "transfer_id": transfer.transfer_id,
        "status": transfer.status,
        "rejected_by": current_user["username"]
    }