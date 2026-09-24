from pydantic import BaseModel, Field


class InventoryScan(BaseModel):
    scanned_code: str = Field(min_length=1, max_length=120)
    quantity: int = Field(default=1, ge=1)
    scan_event_id: str = Field(min_length=1, max_length=120)