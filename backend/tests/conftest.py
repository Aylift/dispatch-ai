import os
import pytest
import tempfile
import asyncio

# Use a separate in-memory/test DB for tests, NOT the production dispatch.db
TEST_DB = "sqlite+aiosqlite:///:memory:"

os.environ["DATABASE_URL"] = TEST_DB

from fastapi.testclient import TestClient  # noqa: E402
from fastapi import FastAPI  # noqa: E402

# Import app AFTER setting env vars
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402
from database import Base, engine, async_session  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """Isolated test client with in-memory DB."""
    asyncio.run(_init())
    with TestClient(app) as c:
        yield c
    asyncio.run(_drop())


@pytest.fixture(autouse=True)
def clean_db(client):
    """Reset the task table before each test for full isolation."""
    asyncio.run(_clean())
    yield


async def _init():
    async with engine.begin() as conn:
        from models import Task  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)


async def _clean():
    from database import get_db
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM tasks"))


async def _drop():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
