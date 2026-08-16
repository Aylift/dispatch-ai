import { test, expect } from '@playwright/test'

// URLs configurable for Docker (tests-e2e) vs local run.
// Locally the frontend runs on :5173 and the isolated test backend on :8100.
const FRONTEND_URL = process.env.E2E_FRONTEND_URL || 'http://localhost:5173'
const TEST_BACKEND_URL = process.env.E2E_BACKEND_URL || 'http://127.0.0.1:8100'

// Reset schema + data via the isolated test backend for deterministic test state.
// POST /tasks/reset only exists on the TEST_MODE backend (:8100), never the real one.
async function clearAllTasks(page) {
  const res = await page.request.post(`${TEST_BACKEND_URL}/tasks/reset`)
  if (!res.ok()) throw new Error(`Failed to reset tasks: ${res.status()}`)
  await page.goto(FRONTEND_URL)
  // TODAY is the default tab on startup; switch to All so the generic tests
  // (which create untagged tasks) see them. TODAY-specific tests switch tabs
  // themselves. Wait for the tab to render (app shows a loading state until the
  // backend health check passes) before clicking.
  const allTab = page.locator('[data-testid="tab-all"]')
  await allTab.waitFor({ state: 'visible' })
  await allTab.click()
}

test.describe('Dispatch AI - basic UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(FRONTEND_URL)
    await clearAllTasks(page)
  })

  test('page loads with title', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('DISPATCH')
    await expect(page.locator('text=ai-powered task hud')).toBeVisible()
  })

  test('can type in textarea and add task', async ({ page }) => {
    const textarea = page.locator('textarea')
    await textarea.fill('buy milk')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=buy milk')).toBeVisible()
  })

  test('task appears with checkbox', async ({ page }) => {
    await page.locator('textarea').fill('test task')
    await page.locator('text=+ Add Task').click()
    const row = page.locator('div', { hasText: 'test task' }).filter({ has: page.locator('input[type="checkbox"]') }).first()
    const checkbox = row.locator('input[type="checkbox"]')
    await expect(checkbox).toBeVisible()
    await expect(checkbox).not.toBeChecked()
  })

  test('can toggle task done', async ({ page }) => {
    await page.locator('textarea').fill('toggle me')
    await page.locator('text=+ Add Task').click()
    const row = page.locator('div', { hasText: 'toggle me' }).filter({ has: page.locator('input[type="checkbox"]') }).first()
    const checkbox = row.locator('input[type="checkbox"]')
    await checkbox.check()
    await expect(checkbox).toBeChecked()
  })

  test('clear done button appears and works', async ({ page }) => {
    await page.locator('textarea').fill('done task')
    await page.locator('text=+ Add Task').click()
    const row = page.locator('div', { hasText: 'done task' }).filter({ has: page.locator('input[type="checkbox"]') }).first()
    const checkbox = row.locator('input[type="checkbox"]')
    await checkbox.check()
    await expect(page.locator('text=Clear done')).toBeVisible()
    await page.locator('text=Clear done').click()
    await expect(page.locator('text=done task')).not.toBeVisible()
  })

  test('toggle dark/light theme', async ({ page }) => {
    const btn = page.locator('button[title*="Switch"]')
    await btn.click()
    await expect(page.locator('.bg-white\\/95')).toBeVisible()
    await btn.click()
    await expect(page.locator('.bg-zinc-900\\/95')).toBeVisible()
  })

  test('voice mic button exists', async ({ page }) => {
    await expect(page.locator('button:has(svg) >> text=Voice')).toBeVisible()
  })

  test('priority meter exists and defaults to medium', async ({ page }) => {
    const meter = page.locator('[data-testid="priority-meter"]').first()
    await expect(meter).toBeVisible()
    // The input's priority meter shows "3 (Medium)" in its tooltip
    await expect(meter).toHaveAttribute('title', /Medium/)
  })

  test('can create a task with selected priority', async ({ page }) => {
    // Set the input priority to Critical by clicking segment 1 on the toolbar meter
    await page.locator('[data-testid="priority-meter"]').first()
      .locator('button[data-priority="1"]').click()
    await page.locator('textarea').fill('urgent task')
    await page.locator('text=+ Add Task').click()
    // The task row shows its meter with priority 1 -> title mentions Critical
    const taskMeter = page.locator('[data-testid="priority-meter"]').nth(1)
    await expect(taskMeter).toHaveAttribute('title', /Critical/)
  })

  test('priority meter changes and re-sorts', async ({ page }) => {
    // Create one task then change its priority via its meter
    await page.locator('textarea').fill('my task')
    await page.locator('text=+ Add Task').click()
    // Task row meter defaults to Medium (3)
    const taskMeter0 = page.locator('[data-testid="priority-meter"]').nth(1)
    await expect(taskMeter0).toHaveAttribute('title', /Medium/)
    // change to Critical (1) by clicking its segment 1
    await taskMeter0.locator('button[data-priority="1"]').click()
    await expect(taskMeter0).toHaveAttribute('title', /Critical/)
    // Create another task - it should sort below the Critical one
    await page.locator('textarea').fill('second task')
    await page.locator('text=+ Add Task').click()
    // Critical task is still first
    await expect(page.locator('[data-testid="priority-meter"]').nth(1)).toHaveAttribute('title', /Critical/)
    await expect(page.locator('[data-testid="priority-meter"]').nth(2)).toHaveAttribute('title', /Medium/)
  })

  test('sort toggle defaults to Priority', async ({ page }) => {
    await page.locator('textarea').fill('sortable')
    await page.locator('text=+ Add Task').click()
    // The active sort option (Priority) is highlit while Created is muted
    const created = page.locator('[data-testid="sort-created"]')
    await expect(created).toBeVisible()
  })

  test('sorting by Created shows newest first', async ({ page }) => {
    // Create two tasks; newest should win in 'created' mode.
    // Wait for each task row to appear before adding the next, because the
    // async add clears the textarea when it resolves (would wipe the next input).
    await page.locator('textarea').fill('older task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('[data-testid="task-row"]')).toHaveCount(1)
    await page.locator('textarea').fill('newer task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('[data-testid="task-row"]')).toHaveCount(2)

    // Switch to created-descending sort
    await page.locator('[data-testid="sort-created"]').click()

    const rows = page.locator('[data-testid="task-row"]')
    await expect(rows).toHaveCount(2)
    // First row should be the most recently created
    await expect(rows.nth(0)).toContainText('newer task')
    await expect(rows.nth(1)).toContainText('older task')
  })

  test('toggling back to Priority sorts by priority', async ({ page }) => {
    // Create a Critical task first (older), then a Medium task (newer).
    await page.locator('[data-testid="priority-meter"]').first()
      .locator('button[data-priority="1"]').click()
    await page.locator('textarea').fill('critical old task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('[data-testid="task-row"]')).toHaveCount(1)
    await page.locator('textarea').fill('medium new task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('[data-testid="task-row"]')).toHaveCount(2)

    // In 'created' mode the newest (medium) is on top.
    await page.locator('[data-testid="sort-created"]').click()
    let rows = page.locator('[data-testid="task-row"]')
    await expect(rows.nth(0)).toContainText('medium new task')
    await expect(rows.nth(1)).toContainText('critical old task')

    // Switch back to 'priority' -> Critical (higher priority) surfaces on top.
    await page.locator('[data-testid="sort-priority"]').click()
    rows = page.locator('[data-testid="task-row"]')
    await expect(rows.nth(0)).toContainText('critical old task')
    await expect(rows.nth(1)).toContainText('medium new task')
  })

  test('AI parse splits dump into prioritized tasks', async ({ page }) => {
    // Mock the AI parse endpoint so the test never calls the real DeepSeek API
    await page.route('**/tasks/parse', async (route) => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 1, text: 'Fix the sink', done: false, priority: 2, created_at: '2026-01-01T00:00:00' },
          { id: 2, text: 'Buy milk ASAP', done: false, priority: 1, created_at: '2026-01-01T00:00:00' },
          { id: 3, text: 'Organize photos', done: false, priority: 5, created_at: '2026-01-01T00:00:00' },
        ]),
      })
    })

    await page.locator('textarea').fill('fix the sink, buy milk asap and maybe organize photos')
    await page.getByRole('button', { name: 'Organize' }).click()

    // All three tasks appear
    await expect(page.locator('text=Fix the sink')).toBeVisible()
    await expect(page.locator('text=Buy milk ASAP')).toBeVisible()
    await expect(page.locator('text=Organize photos')).toBeVisible()
    // Input is cleared after parse
    await expect(page.locator('textarea')).toHaveValue('')
  })

  test('shows task count', async ({ page }) => {
    // After cleanup, should be 0
    await expect(page.locator('footer')).toContainText('0 tasks')
    await page.locator('textarea').fill('task one')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('footer')).toContainText('1 task')
    await page.locator('textarea').fill('task two')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('footer')).toContainText('2 tasks')
  })

  test('double-click enters edit mode and Enter saves new title', async ({ page }) => {
    await page.locator('textarea').fill('old title')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=old title')).toBeVisible()

    await page.locator('text=old title').dblclick()
    const input = page.locator('[data-testid="task-title-input"]')
    await expect(input).toBeVisible()
    await input.fill('new title')
    await input.press('Enter')

    await expect(page.locator('text=new title')).toBeVisible()
    await expect(page.locator('text=old title')).not.toBeVisible()
  })

  test('Esc cancels edit without saving', async ({ page }) => {
    await page.locator('textarea').fill('keep me')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=keep me')).toBeVisible()

    await page.locator('text=keep me').dblclick()
    const input = page.locator('[data-testid="task-title-input"]')
    await expect(input).toBeVisible()
    await input.fill('should not save')
    await input.press('Escape')

    await expect(page.locator('text=keep me')).toBeVisible()
    await expect(page.locator('text=should not save')).not.toBeVisible()
  })

  test('blur saves the edited title', async ({ page }) => {
    await page.locator('textarea').fill('blur me')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=blur me')).toBeVisible()

    await page.locator('text=blur me').dblclick()
    const input = page.locator('[data-testid="task-title-input"]')
    await expect(input).toBeVisible()
    await input.fill('blur saved')
    await input.blur()

    await expect(page.locator('text=blur saved')).toBeVisible()
    await expect(page.locator('text=blur me')).not.toBeVisible()
  })

  test('TODAY tab shows only tagged tasks', async ({ page }) => {
    await page.locator('textarea').fill('normal task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=normal task')).toBeVisible()

    await page.locator('textarea').fill('today task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=today task')).toBeVisible()

    // Tag "today task" via its toggle button
    const todayTaskRow = page.locator('[data-testid="task-row"]', { hasText: 'today task' })
    await todayTaskRow.locator('[data-testid="toggle-today"]').click()
    await expect(todayTaskRow.locator('[data-testid="toggle-today"]')).toContainText('TODAY')

    // Switch to TODAY tab: only the tagged task shows
    await page.locator('[data-testid="tab-today"]').click()
    await expect(page.locator('text=today task')).toBeVisible()
    await expect(page.locator('text=normal task')).not.toBeVisible()
  })

  test('untagging removes task from TODAY tab but keeps it in All', async ({ page }) => {
    await page.locator('textarea').fill('temp today')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=temp today')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'temp today' })
    await row.locator('[data-testid="toggle-today"]').click()
    await expect(row.locator('[data-testid="toggle-today"]')).toContainText('TODAY')

    // Untag it
    await row.locator('[data-testid="toggle-today"]').click()
    await expect(row.locator('[data-testid="toggle-today"]')).toContainText('Today')

    // TODAY tab is now empty
    await page.locator('[data-testid="tab-today"]').click()
    await expect(page.locator('text=temp today')).not.toBeVisible()

    // Still present in All
    await page.locator('[data-testid="tab-all"]').click()
    await expect(page.locator('text=temp today')).toBeVisible()
  })
})

