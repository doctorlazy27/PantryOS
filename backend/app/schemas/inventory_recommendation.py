from pydantic import BaseModel


class RecommendationReview(BaseModel):
    supplier_id: int | None = None