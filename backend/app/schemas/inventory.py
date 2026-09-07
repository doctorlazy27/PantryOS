from pydantic import BaseModel, Field


class InventoryCreate(BaseModel):
    product_id: int
    warehouse_id: int
    batch_id: int
    quantity: int = Field(ge=0)