from datetime import date
from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    product_id: int | None = None
    name: str
    category: str
    quantity: int = Field(ge=0)
    unit: str
    price: float = Field(ge=0)
    units_per_box: int = Field(default=1, ge=1)
    boxed_units: int = Field(default=0, ge=0)
    unit_price: float | None = Field(default=None, ge=0)
    box_unit_cost: float | None = Field(default=None, ge=0)
    reorder_level: int = Field(default=0, ge=0)
    batch_number: str | None = Field(default=None, min_length=1, max_length=100)
    manufacturing_date: date | None = None
    expiry_date: date | None = None