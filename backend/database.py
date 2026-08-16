import asyncio
import os
from pathlib import Path
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


def run_migrations():
    """Apply Alembic migrations to the live DB before serving.

    The Tauri shell spawns this backend directly, so there is no separate
    deploy step; running `alembic upgrade head` on startup keeps the schema in
    sync with the models. Alembic is a no-op when the DB is already current.

    This is a blocking/sync call (Alembic manages its own async engine), so it
    must be invoked from an async context via asyncio.to_thread().

    Fail-soft: if Alembic is unavailable (e.g. a stale image without it), log a
    warning and fall back to Base.metadata.create_all, which is idempotent and
    keeps the app bootable. The shared-image build (docker-compose) guarantees
    Alembic is present in normal operation.
    """
    try:
        from alembic import command
        from alembic.config import Config

        backend_dir = Path(__file__).resolve().parent
        cfg = Config(str(backend_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
        command.upgrade(cfg, "head")
    except Exception as exc:
        print(f"[migrate] alembic unavailable ({exc}); falling back to create_all")
        import asyncio as _asyncio
        from models import Task  # noqa: F401 - ensure models are registered
        _asyncio.run(_create_all_fallback())


async def _create_all_fallback():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)