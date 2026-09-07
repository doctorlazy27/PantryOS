from datetime import date
from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    product_id: int | None = None
    name: str
    category: str
    quantity: int = Field(ge=0)
    unit: str
    price: float = Field(ge=0)
    reorder_level: int = Field(default=0, ge=0)
    batch_number: str | None = Field(default=None, min_length=1, max_length=100)
    manufacturing_date: date | None = None
    expiry_date: date | None = None