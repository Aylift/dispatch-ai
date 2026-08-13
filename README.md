# Dispatch AI

An AI-powered task HUD that turns natural language into actionable tasks, plans, and priorities. Speak your intent, and let the AI break it down, adapt to changes, and keep everything on track.

## What it does

- **Voice input** — click the mic, speak, and your words get transcribed in real time into the text area (Deepgram streaming STT)
- **Natural language parsing** — an LLM (DeepSeek) parses transcription into structured tasks with priorities and categories
- **Floating HUD window** — a transparent, frameless desktop overlay built with Tauri. It's a normal draggable window that stays on top only while it has focus.
- **Task management** — add tasks with Ctrl+Enter, toggle completion, clear done items, counts displayed live
- **Dark/light themes**

## Architecture

```
backend/     FastAPI + WebSocket streaming + Deepgram/DeepSeek APIs
frontend/    Vue 3 + TailwindCSS + Tauri desktop shell
tests/       Playwright E2E tests
```

The **desktop app is the primary runtime** — the Tauri shell natively spawns
the FastAPI backend on startup (no Docker), keeps it running while the app is
open, and shuts it down on exit. Docker Compose is still available only for
the isolated test environments (unit tests + E2E), each with its own database,
so tests never touch your production data.

## Quick start (native, recommended)

One-time provisioning — installs Python if needed, creates `backend\.venv`,
installs backend + frontend dependencies, and builds the Tauri app:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

After setup, just run the built app (or `npx tauri dev` while developing). The
app:

1. Registers itself to **start at logon** (tauri-plugin-autostart) on first run.
2. **Spawns the backend** (`backend\.venv\Scripts\pythonw.exe -m uvicorn`)
   in the background, pointed at the host database.
3. **Kills the backend** when you quit the app.

Manual backend (optional, for debugging) — run from `backend/`:

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

- Backend API: http://localhost:8000
- Config secrets live in backend/.env (see backend/.env.example).

### Development (hot-reload on the host)

```powershell
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

- Browser frontend: http://localhost:5173

## Services

| service       | purpose                                              | DB           |
|---------------|------------------------------------------------------|--------------|
| backend       | FastAPI app (uvicorn, live reload)                   | dispatch.db  |
| tests-backend | Backend unit/API tests                               | in-memory    |
| test-backend  | Isolated backend for E2E                             | test DB      |
| tests-e2e     | Playwright E2E (own vite + test backend, in Docker)  | test DB      |

## Running tests

```powershell
# Backend unit/API tests (isolated in-memory DB)
docker compose --profile test run --rm tests-backend

# Playwright E2E (own vite + isolated test backend on :8100)
docker compose --profile test run --rm tests-e2e
```

## Cleaning up

```powershell
docker compose down        # stop containers
docker compose down -v     # also remove data volumes (NOT your database)
```

The live database is **not** a Docker volume — it lives on your Windows host
(see below), so neither command deletes your tasks.

## Data & backups

The live SQLite database is stored **on the Windows host, outside this repo:**

```
C:\Users\adamm\.dispatch-ai\dispatch.db
```

The native backend writes there directly. Because it's a real host file (not a
container volume), it survives reinstalls and app updates. To change the
location, set `DISPATCH_DATA_DIR` in the root `.env` (gitignored); the Tauri
app reads it when it spawns the backend.

### Logs & debugging

The app and its spawned backend each write to their own log file (in the host
data dir):

```
C:\Users\adamm\.dispatch-ai\logs\backend.log    # uvicorn / FastAPI (the spawned process)
%LOCALAPPDATA%\com.dispatch-ai.app\logs\dispatch.log   # the Tauri app shell
```

- `backend.log` captures the backend process stdout/stderr, so uvicorn start
  lines, requests (200/404/...), and any Python exceptions all land there.
- `dispatch.log` captures the Rust/Tauri side (spawn decisions, errors).

They append, so restarts keep their history. `tail` them while the app runs:

```powershell
Get-Content ("$env:USERPROFILE\.dispatch-ai\logs\backend.log") -Wait -Tail 40
```

> Note: the backend is spawned with `pythonw.exe` and no console, so if you
> want live terminal output use the manual command instead (see below).

### Backup

Run a timestamped snapshot into a `backups\` folder next to the DB:

```powershell
.\scripts\backup.ps1            # keeps the 14 most recent snapshots
.\scripts\backup.ps1 -Retention 30
```

Each run creates `dispatch-YYYYMMDD-HHMMSS.db` and prunes older ones:

```
C:\Users\adamm\.dispatch-ai\backups\dispatch-20260811-223344.db
```

Make it automatic with Task Scheduler (run on logon and/or daily, e.g. at 03:00).

### Restore

1. Quit the app (it stops the backend).
2. Replace `dispatch.db` with a snapshot:
   `Copy-Item C:\Users\adamm\.dispatch-ai\backups\dispatch-<pick>.db C:\Users\adamm\.dispatch-ai\dispatch.db -Force`
3. Relaunch the app (it respawns the backend).

## Desktop app (Tauri)

The Tauri HUD is the master controller. It **self-hosts everything**:

- **Autostart:** on first run it registers to start at logon
  (tauri-plugin-autostart); Windows launches the HUD when you log in.
- **Backend lifecycle:** it spawns the native Python backend
  (`backend\.venv\Scripts\pythonw.exe`) invisibly on startup and kills it on
  exit — no console window, no Docker.
- **Host DB:** the SQLite database lives at `C:\Users\adamm\.dispatch-ai\`.

The HUD window is a normal draggable window (frameless + skip-taskbar); the
header has a **theme toggle** and a **hide (—)** button that collapses the HUD
into the system tray. A **system tray icon** can restore or exit the app —
left-clicking it reopens the HUD, right-clicking it shows a Show / Hide / Quit
menu — since the frameless, skip-taskbar HUD has no taskbar presence of its own.

For development (`hot reload`), needs Rust and VS C++ Build Tools on Windows:

```powershell
cd frontend
npm install
npx tauri dev
```

## Build a standalone executable

```powershell
cd frontend
npx tauri build
```

Produces an installer in frontend/src-tauri/target/release/bundle/. Both a
`.msi` and an `.exe` installer are produced by default; the `.exe` (NSIS)
offers an install-folder + shortcut wizard, the `.msi` is a silent, scriptable
Windows Installer package. Pick one with `npx tauri build --bundles nsis|msi`.
