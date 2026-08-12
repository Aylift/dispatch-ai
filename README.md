# Dispatch AI

An AI-powered task HUD that turns natural language into actionable tasks, plans, and priorities. Speak your intent, and let the AI break it down, adapt to changes, and keep everything on track.

## What it does

- **Voice input** — click the mic, speak, and your words get transcribed in real time into the text area (Deepgram streaming STT)
- **Natural language parsing** — an LLM (DeepSeek) parses transcription into structured tasks with priorities and categories
- **Floating HUD window** — a transparent, always-on-top, frameless desktop overlay built with Tauri
- **Task management** — add tasks with Ctrl+Enter, toggle completion, clear done items, counts displayed live
- **Dark/light themes**

## Architecture

```
backend/     FastAPI + WebSocket streaming + Deepgram/DeepSeek APIs
frontend/    Vue 3 + TailwindCSS + Tauri desktop shell
tests/       Playwright E2E tests
```

Docker Compose runs the production backend and the isolated test environments — each with its own database, so tests never touch your production data. The frontend is **not** containerized: it runs natively on your host (needed for instant Vite hot-reload and later for the Tauri desktop shell).

## Quick start

**1. Start the backend (Docker):**

```powershell
docker compose up -d backend
```

- Backend API: http://localhost:8000

Config secrets live in backend/.env (see backend/.env.example).

**2. Start the frontend (host Vite dev server):**

```powershell
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

- Browser frontend: http://localhost:5173

Vite runs on the host so hot reload uses native file events (no slow polling
over Docker bind mounts).

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

Docker bind-mounts that folder into the backend as `/app/data`. Because it's a
real host file (not a Docker volume), it survives `docker compose down`, and
`down -v` won't touch it. To change the location, edit `DISPATCH_DATA_DIR` in
the root `.env` (gitignored) and recreate the container:

```powershell
docker compose up -d --force-recreate backend
```

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

1. Stop the backend:  `docker compose stop backend`
2. Replace `dispatch.db` with a snapshot:
   `Copy-Item C:\Users\adamm\.dispatch-ai\backups\dispatch-<pick>.db C:\Users\adamm\.dispatch-ai\dispatch.db -Force`
3. Start the backend: `docker compose start backend`

## Desktop app (Tauri)

The frontend runs on the host, so the Tauri desktop HUD overlay shares the same
source — no Docker involved (it needs local Rust toolchain + system audio):

```powershell
cd frontend
npm install
npx tauri dev
```

Requires Rust and VS C++ Build Tools on Windows.

## Build a standalone executable

```powershell
cd frontend
npx tauri build
```

Produces an installer in frontend/src-tauri/target/release/bundle/.
