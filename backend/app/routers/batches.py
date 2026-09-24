from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date
from fastapi import HTTPException

from app.database import get_db
from app.models.batch import Batch
from app.schemas.batch import BatchCreate
from app.auth.dependencies import require_permission


router = APIRouter(
    prefix="/batches",
    tags=["Batches"]
)


@router.post("/")
def create_batch(
    batch: BatchCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("receive_purchase_orders"))
):
    if batch.expiry_date <= batch.manufacturing_date:
        raise HTTPException(status_code=400, detail="Expiry date must be after manufacturing date")
    if batch.expiry_date <= date.today():
        raise HTTPException(status_code=400, detail="Cannot create an already expired batch")
    new_batch = Batch(
        product_id=batch.product_id,
        batch_number=batch.batch_number,
        manufacturing_date=batch.manufacturing_date,
        expiry_date=batch.expiry_date
    )

    db.add(new_batch)
    db.commit()
    db.refresh(new_batch)

    return new_batch


@router.get("/")
def get_batches(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    batches = db.query(Batch).all()

    return {
        "batches": batches
    }