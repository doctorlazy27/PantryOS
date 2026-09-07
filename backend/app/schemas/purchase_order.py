from pydantic import BaseModel, Field


class PurchaseOrderItemCreate(BaseModel):
    product_id: int | None = None
    product_name: str | None = Field(default=None, min_length=1, max_length=100)
    quantity: int = Field(gt=0)


class PurchaseOrderCreate(BaseModel):
    supplier_id: int | None = None
    supplier_name: str | None = Field(default=None, min_length=1, max_length=150)
    items: list[PurchaseOrderItemCreate]