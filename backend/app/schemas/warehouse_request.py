from pydantic import BaseModel, Field


class WarehouseRequestCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
