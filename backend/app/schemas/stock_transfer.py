from pydantic import BaseModel, Field


class StockTransferCreate(BaseModel):
    product_id: int
    batch_id: int
    source_warehouse_id: int
    destination_warehouse_id: int
    quantity: int = Field(gt=0)