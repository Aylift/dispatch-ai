# Test Infrastructure Overhaul

## Problem Statement

E2E and backend tests keep failing with stale-schema / stale-image / port-conflict
issues that require manual, fragile recovery (deleting DB files inside containers,
restarting, force-recreating, rebuilding images). Root causes:

1. **Stale test-backend image.** `test-backend` builds `./backend` as a *separate*
   image (`dispatch-ai-test-backend`). When `requirements.txt` changes (e.g. added
   `alembic`), the prod `backend` image rebuilds but `test-backend` keeps its stale
   cached image → `ImportError: cannot import name 'command' from 'alembic'`.
2. **Manual E2E DB reset.** Tests clear state via `DELETE /tasks/all`, but the schema
   itself is only fixed by manually deleting the DB file inside the container and
   restarting. No deterministic schema reset.
3. **Native backend shadows Docker on :8000.** The Tauri-spawned native backend binds
   `127.0.0.1:8000` and shadows the Docker `backend` container, causing confusion
   about which process serves what.
4. **Migrations coupled to app startup.** `run_migrations()` in the lifespan fails
   hard if alembic is missing from the image, and runs on every boot.

## Goals

- One shared backend image so prod/test can never drift.
- Deterministic, API-driven schema + data reset for E2E (no manual container surgery).
- Test backend clearly isolated on :8100, never touching :8000 or the personal DB.
- Migrations run as an explicit, idempotent step that is robust to missing deps.

## Design

### 1. Single shared backend image

`docker-compose.yml`: `backend`, `tests-backend`, and `test-backend` all reference the
same image name (`dispatch-ai-backend`) built once. Compose builds it once and reuses
the tag for all three services. No separate `dispatch-ai-test-backend` image to go stale.

```yaml
services:
  backend:
    build: ./backend
    image: dispatch-ai-backend:latest
    ...
  tests-backend:
    image: dispatch-ai-backend:latest
    ...
  test-backend:
    image: dispatch-ai-backend:latest
    ...
```

### 2. Deterministic E2E reset via gated endpoint

Add `POST /tasks/reset` that drops + recreates the `tasks` table (schema reset) and is
**only registered when `TEST_MODE=1`**. The real backend (native + Docker prod) never
sets `TEST_MODE`, so the endpoint does not exist there. The isolated `test-backend`
sets `TEST_MODE=1`, so E2E can reset schema + data deterministically through the API.

```python
# main.py
if os.environ.get("TEST_MODE") == "1":
    @app.post("/tasks/reset", status_code=204)
    async def reset_tasks(db: AsyncSession = Depends(get_db)):
        await db.execute(text("DROP TABLE IF EXISTS tasks"))
        await db.commit()
        await init_db()
```

E2E `beforeEach` calls `POST /tasks/reset` instead of `DELETE /tasks/all`. This makes
every test start from a clean, correctly-migrated schema — no manual DB deletion.

### 3. Port separation (already correct, keep enforced)

- Real backend: :8000 (native app primary; Docker `backend` for dev).
- Isolated test backend: :8100 (Docker `test-backend`).
- Playwright vite: :5174 (never reuses :5173 dev server).

Document in AGENTS.md that the native app owns :8000 and Docker `backend` is only for
dev; tests must only ever talk to :8100.

### 4. Robust migrations

Keep `run_migrations()` in the lifespan but make it fail-soft: if alembic is missing,
log a warning and fall back to `Base.metadata.create_all` (idempotent). This prevents a
hard crash when the image is stale, and the shared-image fix (goal 1) removes the
stale-image cause entirely.

## Files Changed

| File | Change |
|------|--------|
| `docker-compose.yml` | Shared `image:` for backend services |
| `backend/main.py` | Gated `POST /tasks/reset` under `TEST_MODE` |
| `backend/database.py` | Fail-soft `run_migrations()` |
| `frontend/tests/basic.spec.js` | Use `POST /tasks/reset` in `clearAllTasks` |
| `AGENTS.md` | Document reset endpoint + port ownership |

## Verification

1. `docker compose --profile test build` — one image, no drift.
2. `docker compose --profile test up -d test-backend` — starts clean.
3. `docker compose --profile test run --rm tests-backend` — backend tests pass.
4. Local E2E: `cmd /c "set RUN_LOCAL_E2E=1&& set E2E_BACKEND_URL=http://127.0.0.1:8100&& set E2E_FRONTEND_URL=http://localhost:5174&& npx playwright test"` — all pass with no manual DB surgery.
