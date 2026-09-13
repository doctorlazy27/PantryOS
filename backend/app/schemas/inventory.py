from pydantic import BaseModel, Field


class InventoryCreate(BaseModel):
    product_id: int
    warehouse_id: int
    batch_id: int
    quantity: int = Field(ge=0)
    boxed_units: int = Field(default=0, ge=0)
    units_per_box: int = Field(default=1, ge=1)
    unit_price: float = Field(default=0, ge=0)
    box_unit_cost: float = Field(default=0, ge=0)
    scanned_codes: list[str] = Field(default_factory=list)