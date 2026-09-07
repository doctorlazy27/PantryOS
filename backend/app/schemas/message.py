from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    recipient_ids: list[int] = Field(default_factory=list, max_length=100)
    subject: str = Field(min_length=1, max_length=150)
    body: str = Field(min_length=1, max_length=5000)
    broadcast: bool = False
    reply_to_id: int | None = None
