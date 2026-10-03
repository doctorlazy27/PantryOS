from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class InventoryAdditionApproval(BaseModel):
    batch_number: str = Field(min_length=1, max_length=100)
    manufacturing_date: date
    expiry_date: date
    storage_zone: Literal["AMBIENT", "CHILLED", "FROZEN"]
    temperature_c: float = Field(ge=-80, le=100)
    aisle: str = Field(default="Unassigned", min_length=1, max_length=50)
    shelf_number: str = Field(default="Unassigned", min_length=1, max_length=50)