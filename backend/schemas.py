from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class TaskCreate(BaseModel):
    text: str
    priority: Optional[int] = Field(default=3, ge=1, le=5)


class TaskUpdate(BaseModel):
    text: Optional[str] = None
    done: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)


class TaskOut(BaseModel):
    id: int
    text: str
    done: bool
    priority: int
    created_at: datetime

    model_config = {"from_attributes": True}

