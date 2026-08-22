from conftest import client
import main as main_module


def _fake_parse(text):
    # Deterministic fake parser so tests never touch the real DeepSeek API
    return [{"text": text.strip(), "priority": 3}]


def test_empty_task_list(client):
    res = client.get("/tasks")
    assert res.status_code == 200
    assert res.json() == []


def test_create_task(client):
    res = client.post("/tasks", json={"text": "buy milk"})
    assert res.status_code == 201
    data = res.json()
    assert data["text"] == "buy milk"
    assert data["done"] is False
    assert data["priority"] == 3  # default
    assert "id" in data


def test_create_task_with_priority(client):
    res = client.post("/tasks", json={"text": "urgent", "priority": 1})
    assert res.status_code == 201
    assert res.json()["priority"] == 1


def test_create_task_with_description(client):
    res = client.post("/tasks", json={"text": "plan trip", "description": "book flights and hotel for June"})
    assert res.status_code == 201
    data = res.json()
    assert data["description"] == "book flights and hotel for June"


def test_create_task_description_defaults_to_null(client):
    res = client.post("/tasks", json={"text": "no desc"})
    assert res.status_code == 201
    assert res.json()["description"] is None


def test_update_description(client):
    created = client.post("/tasks", json={"text": "desc me"}).json()
    tid = created["id"]
    res = client.patch(f"/tasks/{tid}", json={"description": "some long notes here"})
    assert res.status_code == 200
    assert res.json()["description"] == "some long notes here"


def test_create_task_rejects_invalid_priority(client):
    res = client.post("/tasks", json={"text": "bad", "priority": 9})
    assert res.status_code == 422


def test_parse_creates_tasks_without_ai_key(client, monkeypatch):
    monkeypatch.setattr(main_module, "parse_tasks", _fake_parse)
    res = client.post("/tasks/parse", json={"text": "remember to pay rent"})
    assert res.status_code == 201
    data = res.json()
    assert len(data) == 1
    assert data[0]["text"] == "remember to pay rent"
    assert data[0]["priority"] == 3


def test_parse_rejects_empty_text(client, monkeypatch):
    monkeypatch.setattr(main_module, "parse_tasks", _fake_parse)
    res = client.post("/tasks/parse", json={"text": "   "})
    assert res.status_code == 400


def test_parse_creates_multiple_tasks(client, monkeypatch):
    def fake(text):
        return [
            {"text": "send email", "priority": 1},
            {"text": "buy groceries", "priority": 3},
            {"text": "organize desk", "priority": 5},
        ]
    monkeypatch.setattr(main_module, "parse_tasks", fake)
    res = client.post("/tasks/parse", json={"text": "brain dump here"})
    assert res.status_code == 201
    data = res.json()
    assert len(data) == 3
    assert [t["text"] for t in data] == ["send email", "buy groceries", "organize desk"]
    assert [t["priority"] for t in data] == [1, 3, 5]


def test_parse_creates_description(client, monkeypatch):
    def fake(text):
        return [
            {"text": "plan trip", "priority": 2, "description": "book flights and hotel"},
            {"text": "no detail", "priority": 3, "description": ""},
        ]
    monkeypatch.setattr(main_module, "parse_tasks", fake)
    res = client.post("/tasks/parse", json={"text": "brain dump here"})
    assert res.status_code == 201
    data = res.json()
    assert data[0]["description"] == "book flights and hotel"
    assert data[1]["description"] == ""


def test_parse_isolation(client, monkeypatch):
    monkeypatch.setattr(main_module, "parse_tasks", _fake_parse)
    res = client.post("/tasks/parse", json={"text": "clean the garage"})
    assert res.status_code == 201
    # Ensure it created the fallback task in isolation (no other tasks)
    data = client.get("/tasks").json()
    assert [t["text"] for t in data] == ["clean the garage"]


def test_list_tasks_after_create(client):
    client.post("/tasks", json={"text": "task one"})
    client.post("/tasks", json={"text": "task two"})
    res = client.get("/tasks")
    data = res.json()
    assert len(data) == 2
    texts = [t["text"] for t in data]
    assert texts[0] == "task two"  # ordered by id desc
    assert texts[1] == "task one"


def test_sort_by_priority(client):
    # Create lower priority first, higher priority later
    client.post("/tasks", json={"text": "low", "priority": 5})
    client.post("/tasks", json={"text": "medium", "priority": 3})
    client.post("/tasks", json={"text": "critical", "priority": 1})
    data = client.get("/tasks").json()
    texts = [t["text"] for t in data]
    assert texts == ["critical", "medium", "low"]


def test_update_priority(client):
    created = client.post("/tasks", json={"text": "change me", "priority": 3}).json()
    tid = created["id"]
    res = client.patch(f"/tasks/{tid}", json={"priority": 1})
    assert res.status_code == 200
    assert res.json()["priority"] == 1


def test_update_task(client):
    created = client.post("/tasks", json={"text": "original"}).json()
    tid = created["id"]
    res = client.patch(f"/tasks/{tid}", json={"done": True})
    assert res.status_code == 200
    assert res.json()["done"] is True


def test_task_defaults_to_empty_tags(client):
    created = client.post("/tasks", json={"text": "no tags"}).json()
    assert created["tags"] == []


def test_update_tags(client):
    created = client.post("/tasks", json={"text": "tag me"}).json()
    tid = created["id"]
    res = client.patch(f"/tasks/{tid}", json={"tags": ["TODAY"]})
    assert res.status_code == 200
    assert res.json()["tags"] == ["TODAY"]


def test_clear_tags(client):
    created = client.post("/tasks", json={"text": "untag me"}).json()
    tid = created["id"]
    client.patch(f"/tasks/{tid}", json={"tags": ["TODAY"]})
    res = client.patch(f"/tasks/{tid}", json={"tags": []})
    assert res.status_code == 200
    assert res.json()["tags"] == []


def test_delete_task(client):
    created = client.post("/tasks", json={"text": "delete me"}).json()
    tid = created["id"]
    res = client.delete(f"/tasks/{tid}")
    assert res.status_code == 204
    # verify gone
    res2 = client.get("/tasks")
    assert tid not in [t["id"] for t in res2.json()]


def test_clear_done(client):
    a = client.post("/tasks", json={"text": "done one", "done": False}).json()
    b = client.post("/tasks", json={"text": "keep me"}).json()
    # mark a as done
    client.patch(f"/tasks/{a['id']}", json={"done": True})
    res = client.delete("/tasks")  # clear done
    assert res.status_code == 204
    remaining = [t["id"] for t in client.get("/tasks").json()]
    assert a["id"] not in remaining
    assert b["id"] in remaining


def test_clear_done_preserves_recurring_tasks(client):
    """Clear done must NOT delete recurring tasks (they reset daily instead)."""
    rec = client.post("/tasks", json={"text": "daily habit", "recurring": True}).json()
    normal = client.post("/tasks", json={"text": "one-off"}).json()
    # mark both done
    client.patch(f"/tasks/{rec['id']}", json={"done": True})
    client.patch(f"/tasks/{normal['id']}", json={"done": True})
    res = client.delete("/tasks")  # clear done
    assert res.status_code == 204
    remaining = [t["id"] for t in client.get("/tasks").json()]
    assert rec["id"] in remaining  # recurring survives
    assert normal["id"] not in remaining  # normal done task is cleared


def test_delete_nonexistent_task(client):
    res = client.delete("/tasks/99999")
    assert res.status_code == 404


def test_create_recurring_task(client):
    res = client.post("/tasks", json={"text": "daily standup", "recurring": True})
    assert res.status_code == 201
    data = res.json()
    assert data["recurring"] is True


def test_create_task_recurring_defaults_to_false(client):
    res = client.post("/tasks", json={"text": "normal task"})
    assert res.status_code == 201
    assert res.json()["recurring"] is False


def test_update_recurring_flag(client):
    created = client.post("/tasks", json={"text": "flip me"}).json()
    tid = created["id"]
    res = client.patch(f"/tasks/{tid}", json={"recurring": True})
    assert res.status_code == 200
    assert res.json()["recurring"] is True
    res2 = client.patch(f"/tasks/{tid}", json={"recurring": False})
    assert res2.json()["recurring"] is False


def test_recurring_task_completed_today_stays_done(client):
    """A recurring task completed today must NOT reset on the same day."""
    created = client.post("/tasks", json={"text": "daily", "recurring": True}).json()
    tid = created["id"]
    client.patch(f"/tasks/{tid}", json={"done": True})
    # list_tasks runs the daily reset; today's completion should persist
    tasks = client.get("/tasks").json()
    task = next(t for t in tasks if t["id"] == tid)
    assert task["done"] is True


def test_recurring_task_resets_next_day(client):
    """A recurring task completed on a previous day comes back undone."""
    import asyncio
    from datetime import date, timedelta
    from database import async_session
    from models import Task
    from sqlalchemy import select

    created = client.post("/tasks", json={"text": "daily", "recurring": True}).json()
    tid = created["id"]
    client.patch(f"/tasks/{tid}", json={"done": True})

    # Simulate the completion happening yesterday.
    async def _backdate():
        async with async_session() as s:
            task = (await s.execute(select(Task).where(Task.id == tid))).scalar_one()
            task.last_completed_date = date.today() - timedelta(days=1)
            await s.commit()
    asyncio.run(_backdate())

    # list_tasks should reset it to undone.
    tasks = client.get("/tasks").json()
    task = next(t for t in tasks if t["id"] == tid)
    assert task["done"] is False


def test_recurring_task_reset_clears_timer_next_day(client):
    """A recurring task's focus timer resets when it rolls over to a new day."""
    import asyncio
    from datetime import date, timedelta
    from database import async_session
    from models import Task
    from sqlalchemy import select

    created = client.post("/tasks", json={"text": "daily", "recurring": True}).json()
    tid = created["id"]
    # Start the timer and accumulate some elapsed time.
    client.patch(f"/tasks/{tid}", json={"status": "active"})
    client.patch(f"/tasks/{tid}", json={"status": "paused"})
    client.patch(f"/tasks/{tid}", json={"done": True})

    # Simulate the completion happening yesterday.
    async def _backdate():
        async with async_session() as s:
            task = (await s.execute(select(Task).where(Task.id == tid))).scalar_one()
            task.last_completed_date = date.today() - timedelta(days=1)
            task.elapsed_seconds = 600
            await s.commit()
    asyncio.run(_backdate())

    # list_tasks should reset it to undone AND clear the timer.
    tasks = client.get("/tasks").json()
    task = next(t for t in tasks if t["id"] == tid)
    assert task["done"] is False
    assert task["status"] == "todo"
    assert task["elapsed_seconds"] == 0


def test_create_task_with_timebox(client):
    res = client.post("/tasks", json={"text": "focused", "timebox_minutes": 25})
    assert res.status_code == 201
    data = res.json()
    assert data["timebox_minutes"] == 25
    assert data["status"] == "todo"
    assert data["elapsed_seconds"] == 0


def test_create_task_with_due_date(client):
    res = client.post("/tasks", json={"text": "scheduled", "due_date": "2026-09-01"})
    assert res.status_code == 201
    assert res.json()["due_date"] == "2026-09-01"


def test_start_task_sets_active_and_today(client):
    created = client.post("/tasks", json={"text": "focus me"}).json()
    tid = created["id"]
    res = client.patch(f"/tasks/{tid}", json={"status": "active"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "active"
    assert data["started_at"] is not None
    # Starting a task naturally puts it in Today.
    assert "TODAY" in data["tags"]


def test_pause_task_keeps_today_and_accumulates_elapsed(client):
    created = client.post("/tasks", json={"text": "focus me"}).json()
    tid = created["id"]
    client.patch(f"/tasks/{tid}", json={"status": "active"})
    res = client.patch(f"/tasks/{tid}", json={"status": "paused"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "paused"
    assert data["started_at"] is None
    # Pausing must NOT remove the TODAY tag.
    assert "TODAY" in data["tags"]
    # Some elapsed time was folded in.
    assert data["elapsed_seconds"] >= 0


def test_completing_task_stops_timer(client):
    created = client.post("/tasks", json={"text": "focus me"}).json()
    tid = created["id"]
    client.patch(f"/tasks/{tid}", json={"status": "active"})
    res = client.patch(f"/tasks/{tid}", json={"done": True})
    assert res.status_code == 200
    data = res.json()
    assert data["done"] is True
    assert data["status"] == "todo"
    assert data["started_at"] is None


def test_update_timebox(client):
    created = client.post("/tasks", json={"text": "task"}).json()
    tid = created["id"]
    res = client.patch(f"/tasks/{tid}", json={"timebox_minutes": 45})
    assert res.status_code == 200
    assert res.json()["timebox_minutes"] == 45


def test_clear_timebox(client):
    created = client.post("/tasks", json={"text": "task"}).json()
    tid = created["id"]
    client.patch(f"/tasks/{tid}", json={"timebox_minutes": 45})
    res = client.patch(f"/tasks/{tid}", json={"timebox_minutes": None})
    assert res.status_code == 200
    assert res.json()["timebox_minutes"] is None


def test_reset_elapsed(client):
    created = client.post("/tasks", json={"text": "task"}).json()
    tid = created["id"]
    client.patch(f"/tasks/{tid}", json={"status": "active"})
    client.patch(f"/tasks/{tid}", json={"status": "paused"})
    res = client.patch(f"/tasks/{tid}", json={"reset_elapsed": True})
    assert res.status_code == 200
    body = res.json()
    assert body["elapsed_seconds"] == 0
    assert body["status"] == "todo"
    assert body["started_at"] is None


