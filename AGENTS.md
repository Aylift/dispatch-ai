# AGENTS.md — Dispatch AI

Context for AI coding agents working in this repo.

## Stack

- **Backend**: FastAPI + WebSocket streaming (Deepgram STT, DeepSeek LLM), SQLite via SQLAlchemy async.
- **Frontend**: Vue 3 `<script setup>` + TailwindCSS, Vite. Desktop shell is Tauri 2 (Rust).
- **Primary runtime**: the Tauri app spawns the native backend (`backend\.venv\Scripts\pythonw.exe`) on startup and kills it on exit. Docker is only for isolated test environments.

## Ports

| Port | Purpose |
|------|---------|
| 8000 | Real backend (native app / dev). **Personal DB.** |
| 8100 | Isolated test backend (Docker `test-backend`). Own DB. |
| 5173 | Dev vite server (points at :8000). |
| 5174 | Playwright-managed vite (points at :8100). |

## CRITICAL — never let E2E touch the real backend

The E2E suite must read/write **only** the isolated test backend on `:8100`.
The playwright-managed vite runs on a dedicated port `:5174` with
`VITE_API_URL=http://127.0.0.1:8100` and `reuseExistingServer: false`.

- If the app hits `:8000` during tests, your **personal tasks get polluted**.
- Never run E2E against a reused dev server on `:5173` (it points at :8000).
- The frontend API base is `import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'`
  in `frontend/src/api.js`. Vite bakes this in at serve/build time from the env.

## How to run tests

### Backend unit/API tests (host, from `backend/`)

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

### Backend tests (Docker)

```powershell
docker compose --profile test run --rm tests-backend
```

### E2E (Docker)

```powershell
docker compose --profile test run --rm tests-e2e
```

### E2E (local, no Docker)

```powershell
# 1. Isolated test backend (own DB)
docker compose --profile test up -d test-backend

# 2. From frontend/
cd frontend
$env:RUN_LOCAL_E2E = "1"
$env:E2E_BACKEND_URL = "http://127.0.0.1:8100"
$env:E2E_FRONTEND_URL = "http://localhost:5174"
npx playwright test
```

The shell is **cmd.exe** (not PowerShell) in this environment. For cmd:

```cmd
cmd /c "set RUN_LOCAL_E2E=1&& set E2E_BACKEND_URL=http://127.0.0.1:8100&& set E2E_FRONTEND_URL=http://localhost:5174&& npx playwright test"
```

## Transcription pipeline (streaming)

- `frontend/src/useVoice.js` captures PCM16 (Float32→Int16) via
  `ScriptProcessorNode` at 48 kHz and streams raw bytes over a WebSocket.
- `backend/main.py` `ws_transcribe` receives bytes → `stream_agent.stream_transcribe`.
- `backend/stream_agent.py` connects to Deepgram (`encoding=linear16`,
  `sample_rate=48000`, `interim_results=true`, `endpointing=300`, `model=nova-3`).
  Deepgram interims are **cumulative** within an utterance; the pure
  `accumulate_transcript()` commits only the delta on final to avoid
  duplication/overwrite.
- Idle auto-stop: after 10s of no speech the backend emits `{"idle": true}` and
  the frontend releases the mic.
- Timestamped logs are tagged `[ws]`, `[stream]`, `[dg]`, `[emit]`, `[flush]`,
  `[voice]` for tracing the pipeline.
