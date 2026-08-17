from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text, func
from database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String, nullable=False)
    description = Column(Text, nullable=True)  # long-form notes for the task
    done = Column(Boolean, default=False, nullable=False)
    priority = Column(Integer, default=3, nullable=False)  # 1=Critical ... 5=Optional
    tags = Column(JSON, default=list, nullable=False)  # e.g. ["TODAY"]
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

