from conftest import client


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

