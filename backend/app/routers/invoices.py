from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.models.invoice import Invoice
from app.models.order import SalesOrder
from app.models.order_item import SalesOrderItem
from datetime import datetime
from app.auth.dependencies import get_current_user, require_permission
from app.auth.dependencies import require_permission
from app.services.activity import log_activity

router = APIRouter(
    prefix="/invoices",
    tags=["Invoices"]
)


@router.get("/{invoice_id}")
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    invoice = db.query(Invoice).join(
        SalesOrder, Invoice.order_id == SalesOrder.order_id
    ).filter(
        Invoice.invoice_id == invoice_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if invoice is None:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found"
        )

    return {
        "invoice_id": invoice.invoice_id,
        "order_id": invoice.order_id,
        "customer_id": invoice.customer_id,
        "generated_by": invoice.generated_by,
        "total_amount": invoice.total_amount,
        "status": invoice.status,
        "sent_by": invoice.sent_by,
        "confirmed_by": invoice.confirmed_by,
        "created_at": invoice.created_at,
        "sent_at": invoice.sent_at,
        "confirmed_at": invoice.confirmed_at
    }

@router.patch("/{invoice_id}/send")
def send_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("send_invoices")
    )
):
    invoice = db.query(Invoice).join(
        SalesOrder, Invoice.order_id == SalesOrder.order_id
    ).filter(
        Invoice.invoice_id == invoice_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if invoice is None:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found"
        )

    if invoice.status != "generated":
        raise HTTPException(
            status_code=400,
            detail="Only generated invoices can be sent"
        )

    invoice.status = "sent"
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="send_invoice",
    description=f"Sent invoice #{invoice.invoice_id}"
)
    invoice.sent_by = current_user["user_id"]
    invoice.sent_at = datetime.utcnow()

    db.commit()
    db.refresh(invoice)

    return {
        "message": "Invoice sent successfully",
        "invoice_id": invoice.invoice_id,
        "status": invoice.status,
        "sent_by": current_user["username"]
    }


@router.get("/")
def get_invoices(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    invoices = (
        db.query(Invoice).join(
            SalesOrder, Invoice.order_id == SalesOrder.order_id
        ).filter(
            SalesOrder.warehouse_id == current_user.get("warehouse_id")
        )
        .order_by(Invoice.created_at.desc())
        .all()
    )

    return {
        "invoices": invoices
    }

@router.patch("/{invoice_id}/confirm")
def confirm_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_permission("confirm_invoices")
    )
):
    invoice = db.query(Invoice).join(
        SalesOrder, Invoice.order_id == SalesOrder.order_id
    ).filter(
        Invoice.invoice_id == invoice_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id"),
    ).first()

    if invoice is None:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found"
        )

    if invoice.status != "sent":
        raise HTTPException(
            status_code=400,
            detail="Only sent invoices can be confirmed"
        )

    invoice.status = "confirmed"
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="confirm_invoice",
    description=f"Confirmed invoice #{invoice.invoice_id}"
)
    invoice.confirmed_by = current_user["user_id"]
    invoice.confirmed_at = datetime.utcnow()

    db.commit()
    db.refresh(invoice)

    return {
        "message": "Invoice confirmed successfully",
        "invoice_id": invoice.invoice_id,
        "status": invoice.status,
        "confirmed_by": current_user["username"]
    }

@router.post("/generate/{order_id}")
def generate_invoice(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("send_invoices"))
):
    order = db.query(SalesOrder).filter(
        SalesOrder.order_id == order_id,
        SalesOrder.warehouse_id == current_user.get("warehouse_id")
    ).first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Sales order not found"
        )

    if order.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Sales invoice can only be generated after the salesperson confirms receipt"
        )

    existing_invoice = db.query(Invoice).filter(
        Invoice.order_id == order_id
    ).first()

    if existing_invoice:
        raise HTTPException(
            status_code=400,
            detail="Invoice already exists for this order"
        )

    items = db.query(SalesOrderItem).filter(
        SalesOrderItem.order_id == order_id
    ).all()

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Order contains no items"
        )

    total_amount = sum(
        item.quantity * item.unit_price
        for item in items
    )

    invoice = Invoice(
        order_id=order.order_id,
        customer_id=order.customer_id,
        generated_by=current_user["username"],
        total_amount=total_amount,
        status="generated"
    )

    db.add(invoice)
    log_activity(
    db=db,
    user_id=current_user["user_id"],
    username=current_user["username"],
    action="generate_invoice",
    description=f"Generated invoice for sales order #{order.order_id}"
)
    db.commit()
    db.refresh(invoice)

    return {
        "invoice_id": invoice.invoice_id,
        "order_id": invoice.order_id,
        "customer_id": invoice.customer_id,
        "generated_by": invoice.generated_by,
        "total_amount": invoice.total_amount,
        "status": invoice.status
    }