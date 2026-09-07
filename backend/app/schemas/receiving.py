from datetime import date

from pydantic import BaseModel, Field


class ReceiveItem(BaseModel):
    product_id: int | None = None
    product_name: str | None = Field(default=None, min_length=1, max_length=100)
    quantity: int = Field(gt=0)
    batch_number: str
    manufacturing_date: date
    expiry_date: date


class ReceivePurchaseOrder(BaseModel):
    warehouse_id: int
    items: list[ReceiveItem]