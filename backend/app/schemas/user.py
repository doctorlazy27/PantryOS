from pydantic import BaseModel, Field

from app.auth.roles import UserRole


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    full_name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    warehouse_id: int | None = Field(default=None, gt=0)
    warehouse_name: str | None = Field(default=None, min_length=1, max_length=100)


class UserLogin(BaseModel):
    username: str
    password: str


class UserDelete(BaseModel):
    password: str = Field(default="", max_length=128)