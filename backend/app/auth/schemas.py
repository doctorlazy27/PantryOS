from pydantic import BaseModel
from enum import Enum


class UserRole(str, Enum):
    MANAGER = "manager"
    WAREHOUSE_WORKER = "warehouse_worker"
    SALESPERSON = "salesperson"


class User(BaseModel):
    username: str
    full_name: str
    role: UserRole