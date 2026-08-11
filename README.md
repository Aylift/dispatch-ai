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
docker compose down -v     # also remove data volumes
```

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
