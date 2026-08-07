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


def test_delete_nonexistent_task(client):
    res = client.delete("/tasks/99999")
    assert res.status_code == 404


