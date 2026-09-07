from pydantic import BaseModel, Field


class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class SalesOrderCreate(BaseModel):
    customer_id: int | None = None
    customer_name: str | None = Field(default=None, min_length=1, max_length=150)
    items: list[OrderItemCreate]