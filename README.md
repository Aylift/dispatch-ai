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

Docker Compose cleanly separates the production backend, the browser frontend, and the test environments — each with its own isolated database, so tests never touch your production data.

## Quick start (Docker)

```powershell
docker compose up -d backend frontend
```

- Backend API:      http://localhost:8000
- Browser frontend: http://localhost:5173

Config secrets live in backend/.env (see backend/.env.example).

## Services

| service       | purpose                                        | DB           |
|---------------|------------------------------------------------|--------------|
| backend       | FastAPI app (uvicorn, live reload)             | dispatch.db  |
| frontend      | Vite dev server (browser dev)                  | —            |
| tests-backend | Backend unit/API tests                         | in-memory    |
| test-backend  | Isolated backend for E2E                       | test DB      |
| tests-e2e     | Playwright E2E (own vite + test backend)       | test DB      |

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

Docker covers the browser frontend + backend. To run the desktop HUD overlay
(not containerized — it needs local Rust toolchain + system audio):

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
