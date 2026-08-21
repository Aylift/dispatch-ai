from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, Literal


class TaskCreate(BaseModel):
    text: str
    description: Optional[str] = None
    priority: Optional[int] = Field(default=3, ge=1, le=5)
    recurring: Optional[bool] = False
    timebox_minutes: Optional[int] = Field(default=None, ge=1)
    due_date: Optional[date] = None


class TaskUpdate(BaseModel):
    text: Optional[str] = None
    description: Optional[str] = None
    done: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    tags: Optional[list[str]] = None
    recurring: Optional[bool] = None
    timebox_minutes: Optional[int] = Field(default=None, ge=1)
    status: Optional[Literal["todo", "active", "paused"]] = None
    due_date: Optional[date] = None
    reset_elapsed: Optional[bool] = None


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
    timebox_minutes: Optional[int] = None
    status: str
    started_at: Optional[datetime] = None
    elapsed_seconds: int
    due_date: Optional[date] = None
    created_at: datetime

    model_config = {"from_attributes": True}

