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

## Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **Rust** (for Tauri) — ` winget install Rustlang.Rustup `
- **Visual Studio C++ Build Tools** (Windows, for Tauri) — ` winget install Microsoft.VisualStudio.2022.BuildTools --override "--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools"`

## Setup

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:

```
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
DEEPGRAM_LANGUAGE=pl
```

### 2. Frontend

```powershell
cd frontend
npm install
npm install -D @playwright/test
npx playwright install chromium
```

## Running

### Terminal 1 — Backend

```powershell
cd backend
.\.venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Terminal 2 — Frontend (browser dev)

```powershell
cd frontend
npx vite dev --host
```

Open ` http://localhost:5173 `.

### Terminal 2 — Desktop app (Tauri)

```powershell
cd frontend
npx tauri dev
```

This launches the floating transparent HUD window.

## Tests

```powershell
cd frontend

# Run all tests headless
npx playwright test

# Interactive — visible browser
npx playwright test --headed

# Debug mode with inspector
npx playwright test --debug

# Full UI mode (watch runs, re-run individual tests)
npx playwright test --ui
```

## Build a standalone executable

```powershell
cd frontend
npx tauri build
```

Produces an installer in ` frontend/src-tauri/target/release/bundle/ `.
