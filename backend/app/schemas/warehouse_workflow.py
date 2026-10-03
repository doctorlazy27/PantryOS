from typing import Literal

from pydantic import BaseModel, Field


class PutawayConfirm(BaseModel):
    storage_zone: Literal["AMBIENT", "CHILLED", "FROZEN"]
    location_code: str = Field(min_length=1, max_length=100)


class TemperatureCheckCreate(BaseModel):
    temperature_c: float = Field(ge=-80, le=100)


class BatchStatusUpdate(BaseModel):
    status: Literal["active", "quarantined", "disposed", "donated"]
    reason: str = Field(min_length=3, max_length=300)


class OrderPickScanCreate(BaseModel):
    scanned_code: str = Field(min_length=1, max_length=120)
    quantity: int = Field(default=1, ge=1)
    event_key: str = Field(min_length=1, max_length=120)