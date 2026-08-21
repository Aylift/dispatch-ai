from contextlib import asynccontextmanager
import json
import asyncio
import os
from datetime import date, datetime, timezone
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
    # Daily reset for recurring tasks: any recurring task that was completed on a
    # previous day comes back undone (it "resets every day").
    today = date.today()
    result = await db.execute(
        select(Task).where(
            Task.recurring == True,  # noqa: E712
            Task.done == True,  # noqa: E712
            (Task.last_completed_date.is_(None)) | (Task.last_completed_date < today),
        )
    )
    for task in result.scalars().all():
        task.done = False
        task.last_completed_date = None
    await db.commit()

    # Sort by priority (1=highest) first, then undone first, then newest
    result = await db.execute(
        select(Task)
        .order_by(Task.done.asc(), Task.priority.asc(), Task.id.desc())
    )
    return result.scalars().all()


@app.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(
        text=body.text,
        description=body.description,
        priority=body.priority,
        recurring=body.recurring,
        timebox_minutes=body.timebox_minutes,
        due_date=body.due_date,
    )
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


def _finalize_elapsed(task: Task) -> None:
    """Fold any running time into elapsed_seconds and clear started_at."""
    if task.started_at is not None:
        now = datetime.now(timezone.utc)
        started = task.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        task.elapsed_seconds += max(0, int((now - started).total_seconds()))
        task.started_at = None


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
        # Track the day a recurring task was completed so it can reset tomorrow.
        if task.recurring:
            task.last_completed_date = date.today() if body.done else None
        # Completing (or un-completing) stops any running timer.
        _finalize_elapsed(task)
        if body.done:
            task.status = "todo"
    if body.priority is not None:
        task.priority = body.priority
    if body.tags is not None:
        task.tags = body.tags
    if body.recurring is not None:
        task.recurring = body.recurring
        if not body.recurring:
            task.last_completed_date = None
    if "timebox_minutes" in body.model_fields_set:
        task.timebox_minutes = body.timebox_minutes
    if body.due_date is not None:
        task.due_date = body.due_date
    if body.status is not None:
        if body.status == "active":
            # Starting: fold any prior running time, then begin a fresh session.
            _finalize_elapsed(task)
            task.status = "active"
            task.started_at = datetime.now(timezone.utc)
            # Starting a task naturally puts it in Today.
            if "TODAY" not in (task.tags or []):
                task.tags = (task.tags or []) + ["TODAY"]
        elif body.status == "paused":
            # Pausing: keep the TODAY tag (stays in Today), just stop the clock.
            _finalize_elapsed(task)
            task.status = "paused"
        elif body.status == "todo":
            _finalize_elapsed(task)
            task.status = "todo"
    if body.reset_elapsed:
        # Reset the focus timer: zero accumulated time and stop any running session.
        task.elapsed_seconds = 0
        task.started_at = None
        task.status = "todo"
    await db.commit()
    await db.refresh(task)
    return task


@app.delete("/tasks", status_code=204)
async def clear_done_tasks(db: AsyncSession = Depends(get_db)):
    # Recurring tasks are never bulk-deleted: they reset daily instead. Only
    # non-recurring done tasks are cleared. To remove a recurring task, use the
    # per-task DELETE /tasks/{id}.
    result = await db.execute(
        select(Task).where(Task.done == True, Task.recurring == False)  # noqa: E712
    )
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

