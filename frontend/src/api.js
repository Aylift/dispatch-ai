const BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export async function fetchTasks() {
  const res = await fetch(`${BASE}/tasks`)
  if (!res.ok) throw new Error('Failed to fetch tasks')
  return res.json()
}

export async function createTask(text, priority = 3) {
  const res = await fetch(`${BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, priority }),
  })
  if (!res.ok) throw new Error('Failed to create task')
  return res.json()
}

// Send a natural-language dump to the AI agent, which splits it into
// prioritized tasks and returns the created tasks.
export async function parseTasks(text) {
  const res = await fetch(`${BASE}/tasks/parse`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) throw new Error('Failed to parse tasks')
  return res.json()
}

export async function updateTask(id, data) {
  const res = await fetch(`${BASE}/tasks/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to update task')
  return res.json()
}

export async function deleteTask(id) {
  const res = await fetch(`${BASE}/tasks/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete task')
}

export async function clearDoneTasks() {
  const res = await fetch(`${BASE}/tasks`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to clear done tasks')
}

