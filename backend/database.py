import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./dispatch.db",
)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db(max_retries: int = 10, delay: float = 0.5):
    """Create tables, retrying transient SQLite lock errors.

    On a cold boot the DB file may still be held/being-flushed by a previous
    instance, which can raise an "operational error: database is locked". We
    don't want that to kill the process on startup, so retry with a short
    backoff until it succeeds (or give up after max_retries).
    """
    from models import Task  # noqa: F401 - ensure models are registered

    attempt = 0
    while True:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception as exc:  # e.g. database is locked
            attempt += 1
            if attempt >= max_retries:
                raise
            await asyncio.sleep(delay)