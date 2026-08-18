from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class TaskCreate(BaseModel):
    text: str
    description: Optional[str] = None
    priority: Optional[int] = Field(default=3, ge=1, le=5)
    recurring: Optional[bool] = False


class TaskUpdate(BaseModel):
    text: Optional[str] = None
    description: Optional[str] = None
    done: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    tags: Optional[list[str]] = None
    recurring: Optional[bool] = None


class TaskParseIn(BaseModel):
    text: str


class TaskOut(BaseModel):
    id: int
    text: str
    description: Optional[str] = None
    done: bool
    priority: int
    tags: list[str]
    recurring: bool
    created_at: datetime

    model_config = {"from_attributes": True}

