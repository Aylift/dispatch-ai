from contextlib import asynccontextmanager
import json
import asyncio
import os
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import init_db, get_db, run_migrations
from models import Task
from schemas import TaskCreate, TaskUpdate, TaskOut, TaskParseIn
from agent import transcribe_audio, parse_tasks
from stream_agent import stream_transcribe, _ts


@asynccontextmanager
async def lifespan(app: FastAPI):
    # run_migrations is blocking (Alembic manages its own async engine), so run
    # it in a worker thread to avoid blocking the event loop.
    await asyncio.to_thread(run_migrations)
    await init_db()
    yield


app = FastAPI(title="Dispatch AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Wildcard origin: the frontend runs in the browser dev server (:5173) and
    # inside the Tauri webview (tauri://localhost / custom protocol), both of
    # which send different Origin values. The API uses no cookies/auth, so
    # wildcard + no-credentials is safe and avoids CORS preflight 400s.
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_transcriptions = {}

@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Liveness + readiness. 200 only when the API is up AND the DB is usable.

    The frontend polls this to know when it's safe to load tasks (the backend
    process + SQLite can take a second or two to come up on a cold start, so
    we must not just fire one GET /tasks and give up).
    """
    try:
        # Exercise the DB for real so a locked/unavailable DB is reported here
        # rather than silently failing on the first task load.
        await db.execute(select(Task.id).limit(1))
    except Exception as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "degraded", "error": str(exc)})
    return {"status": "ok", "database": "ok"}


@app.websocket("/ws/transcribe")
async def ws_transcribe(websocket: WebSocket):
    await websocket.accept()
    print(f"[{_ts()}] [ws] connection open")
    send_audio, transcript_gen, close = await stream_transcribe()
    listener_task = None

    async def send_transcripts():
        async for msg in transcript_gen:
            print(f"[{_ts()}] [ws] -> frontend {msg}")
            await websocket.send_json(msg)

    listener_task = asyncio.create_task(send_transcripts())

    try:
        while True:
            data = await websocket.receive_bytes()
            print(f"[{_ts()}] [ws] recv {len(data)}B audio")
            await send_audio(data)
    except WebSocketDisconnect:
        print(f"[{_ts()}] [ws] client disconnected")
        pass
    finally:
        try:
            await close()
        except Exception as exc:
            print(f"[ws] error closing transcription stream: {exc}")
        if listener_task:
            listener_task.cancel()


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    audio_data = await file.read()
    text = transcribe_audio(audio_data, file.filename or "recording.webm")
    print(f"[transcribe] received {len(audio_data)} bytes, result: '{text}'")
    return {"text": text}


@app.get("/tasks", response_model=list[TaskOut])
async def list_tasks(db: AsyncSession = Depends(get_db)):
    # Sort by priority (1=highest) first, then undone first, then newest
    result = await db.execute(
        select(Task)
        .order_by(Task.done.asc(), Task.priority.asc(), Task.id.desc())
    )
    return result.scalars().all()


@app.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(text=body.text, description=body.description, priority=body.priority)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@app.post("/tasks/parse", response_model=list[TaskOut], status_code=201)
async def parse_and_create_tasks(body: TaskParseIn, db: AsyncSession = Depends(get_db)):
    """Parse a natural-language dump into prioritized tasks and create them."""
    if not body.text.strip():
        raise HTTPException(400, "text cannot be empty")
    parsed = parse_tasks(body.text)
    created = []
    for item in parsed:
        task = Task(
            text=item["text"],
            description=item.get("description"),
            priority=item["priority"],
        )
        db.add(task)
        created.append(task)
    await db.commit()
    for task in created:
        await db.refresh(task)
    return created


@app.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, body: TaskUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if body.text is not None:
        task.text = body.text
    if body.description is not None:
        task.description = body.description
    if body.done is not None:
        task.done = body.done
    if body.priority is not None:
        task.priority = body.priority
    if body.tags is not None:
        task.tags = body.tags
    await db.commit()
    await db.refresh(task)
    return task


@app.delete("/tasks", status_code=204)
async def clear_done_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.done == True))
    tasks = result.scalars().all()
    for task in tasks:
        await db.delete(task)
    await db.commit()


@app.delete("/tasks/all", status_code=204)
async def clear_all_tasks(db: AsyncSession = Depends(get_db)):
    """Delete every task (used to reset state, e.g. in tests)."""
    result = await db.execute(select(Task))
    for task in result.scalars().all():
        await db.delete(task)
    await db.commit()


# Test-only endpoint: drops + recreates the tasks table so E2E can reset both
# schema and data deterministically. Only registered when TEST_MODE=1, which the
# isolated test backend (:8100) sets and the real backend (:8000) never does.
if os.environ.get("TEST_MODE") == "1":

    @app.post("/tasks/reset", status_code=204)
    async def reset_tasks(db: AsyncSession = Depends(get_db)):
        await db.execute(text("DROP TABLE IF EXISTS tasks"))
        await db.commit()
        await init_db()


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    await db.delete(task)
    await db.commit()

