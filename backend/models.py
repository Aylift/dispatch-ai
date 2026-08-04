from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String, nullable=False)
    done = Column(Boolean, default=False, nullable=False)
    priority = Column(Integer, default=3, nullable=False)  # 1=Critical ... 5=Optional
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

