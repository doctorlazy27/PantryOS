from pydantic import BaseModel


class InvoiceResponse(BaseModel):
    invoice_id: int
    order_id: int
    customer_id: int
    generated_by: str
    total_amount: float
    status: str