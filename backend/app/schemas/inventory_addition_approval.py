from datetime import date

from pydantic import BaseModel, Field


class InventoryAdditionApproval(BaseModel):
    batch_number: str = Field(min_length=1, max_length=100)
    manufacturing_date: date
    expiry_date: date
    aisle: str = Field(default="Unassigned", min_length=1, max_length=50)
    shelf_number: str = Field(default="Unassigned", min_length=1, max_length=50)