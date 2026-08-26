from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text, Date, func
from database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String, nullable=False)
    description = Column(Text, nullable=True)  # long-form notes for the task
    done = Column(Boolean, default=False, nullable=False)
    priority = Column(Integer, default=3, nullable=False)  # 1=Critical ... 5=Optional
    tags = Column(JSON, default=list, nullable=False)  # e.g. ["TODAY"]
    recurring = Column(Boolean, default=False, nullable=False)  # resets daily
    last_completed_date = Column(Date, nullable=True)  # day it was last done
    # Timeboxing / focus tracking
    timebox_minutes = Column(Integer, nullable=True)  # optional estimated duration
    status = Column(String, default="todo", nullable=False)  # 'todo' | 'active' | 'paused'
    started_at = Column(DateTime, nullable=True)  # when the task was last started
    elapsed_seconds = Column(Integer, default=0, nullable=False)  # accumulated active time
    # Calendar future-proofing: scheduled date for the task (calendar widget later)
    due_date = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    page_size = Column(Integer, default=10, nullable=False)  # number of tasks per page
