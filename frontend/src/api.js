const BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

// Ping backend + DB readiness. 200/ok means the API is up AND the DB is usable.
export async function checkHealth() {
  const res = await fetch(`${BASE}/health`, { method: 'GET' })
  if (!res.ok) return { ok: false, status: res.status }
  const data = await res.json()
  return { ok: data.status === 'ok', status: res.status, data }
}

// Try `fn` repeatedly until it succeeds or timeBudgetMs runs out.
export async function withRetry(fn, { label = 'request', intervalMs = 1200, timeBudgetMs = 30000 } = {}) {
  const deadline = Date.now() + timeBudgetMs
  let lastErr
  while (Date.now() < deadline) {
    try {
      return await fn()
    } catch (err) {
      lastErr = err
      await new Promise(r => setTimeout(r, intervalMs))
    }
  }
  throw new Error(`${label} still failing after retries: ${lastErr?.message ?? 'unknown error'}`)
}
export async function fetchTasks() {
  const res = await fetch(`${BASE}/tasks`)
  if (!res.ok) throw new Error('Failed to fetch tasks')
  return res.json()
}

export async function createTask(text, priority = 3, description = null, recurring = false) {
  const res = await fetch(`${BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, priority, description, recurring }),
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

export async function fetchSettings() {
  const res = await fetch(`${BASE}/settings`)
  if (!res.ok) throw new Error('Failed to fetch settings')
  return res.json()
}

export async function updateSettings(data) {
  const res = await fetch(`${BASE}/settings`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to update settings')
  return res.json()
}
