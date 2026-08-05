from contextlib import asynccontextmanager
import json
import asyncio
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import init_db, get_db
from models import Task
from schemas import TaskCreate, TaskUpdate, TaskOut
from agent import transcribe_audio
from stream_agent import stream_transcribe


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Dispatch AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "tauri://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_transcriptions = {}


@app.websocket("/ws/transcribe")
async def ws_transcribe(websocket: WebSocket):
    await websocket.accept()
    send_audio, transcript_gen, close = await stream_transcribe()
    listener_task = None

    async def send_transcripts():
        async for msg in transcript_gen:
            await websocket.send_json(msg)

    listener_task = asyncio.create_task(send_transcripts())

    try:
        while True:
            data = await websocket.receive_bytes()
            await send_audio(data)
    except WebSocketDisconnect:
        pass
    finally:
        await close()
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
    task = Task(text=body.text, priority=body.priority)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@app.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, body: TaskUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if body.text is not None:
        task.text = body.text
    if body.done is not None:
        task.done = body.done
    if body.priority is not None:
        task.priority = body.priority
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


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    await db.delete(task)
    await db.commit()

