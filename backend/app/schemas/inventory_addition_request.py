from datetime import date

from pydantic import BaseModel, Field


class InventoryAdditionRequestCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0)
    batch_number: str = Field(min_length=1, max_length=100)
    manufacturing_date: date
    expiry_date: date
