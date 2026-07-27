from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class TaskCreate(BaseModel):
    text: str


class TaskUpdate(BaseModel):
    text: Optional[str] = None
    done: Optional[bool] = None


class TaskOut(BaseModel):
    id: int
    text: str
    done: bool
    created_at: datetime

    model_config = {"from_attributes": True}
