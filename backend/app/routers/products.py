from fastapi import APIRouter, Depends, HTTPException
from datetime import date
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate
from app.models.inventory import Inventory
from app.models.batch import Batch
from app.auth.dependencies import get_current_user, require_permission

router = APIRouter(
    prefix="/products",
    tags=["Products"]
)

@router.get("/")
def get_products(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    products = db.query(Product).all()

    return {
        "products": products
    }

@router.get("/low-stock")
def get_low_stock_products(db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    products = db.query(Product).all()
    low_stock = []

    for product in products:
        total_quantity = sum(
            quantity for (quantity,) in db.query(Inventory.quantity).filter(
                    Inventory.product_id == product.product_id,
                    Inventory.warehouse_id == current_user.get("warehouse_id"),
            ).all()
        )
        if total_quantity <= product.reorder_level:
            low_stock.append({
                "product_id": product.product_id,
                "name": product.name,
                "reorder_level": product.reorder_level,
                "current_quantity": total_quantity,
                "unit": product.unit,
            })

    return {"low_stock": low_stock}


@router.get("/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_permission("view_inventory"))):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if product is None:
        return {"message": "Product not found"}
    return product

@router.post("/")
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission("update_inventory"))
    
):
    if current_user["role"] == "warehouse_worker":
        raise HTTPException(status_code=403, detail="Workers must submit a manager inventory request")

    new_product = Product(
        product_id=product.product_id,
        name=product.name,
        category=product.category,
        storage_section=product.storage_section,
        shelf_number=product.shelf_number,
        aisle=product.aisle,
        quantity=product.quantity,
        unit=product.unit,
        price=product.price,
        units_per_box=product.units_per_box,
        reorder_level=product.reorder_level
    )

    db.add(new_product)
    db.flush()
    if current_user["role"] == "warehouse_worker":
        if not product.batch_number or not product.manufacturing_date or not product.expiry_date:
            raise HTTPException(status_code=400, detail="Batch number, manufacturing date, and expiry date are required")
        if product.expiry_date <= product.manufacturing_date:
            raise HTTPException(status_code=400, detail="Expiry date must be after manufacturing date")
        if product.expiry_date <= date.today():
            raise HTTPException(status_code=400, detail="Cannot create an already expired batch")
        batch = Batch(
            product_id=new_product.product_id,
            batch_number=product.batch_number,
            manufacturing_date=product.manufacturing_date,
            expiry_date=product.expiry_date,
        )
        db.add(batch)
        db.flush()
        db.add(Inventory(
            product_id=new_product.product_id,
            warehouse_id=current_user.get("warehouse_id"),
            batch_id=batch.batch_id,
            quantity=product.quantity,
        ))
    db.commit()
    db.refresh(new_product)

    return new_product
