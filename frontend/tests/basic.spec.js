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
    const textarea = page.locator('[data-testid="task-input"]')
    await textarea.fill('buy milk')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=buy milk')).toBeVisible()
  })

  test('task appears with checkbox', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('test task')
    await page.locator('text=+ Add Task').click()
    const row = page.locator('div', { hasText: 'test task' }).filter({ has: page.locator('input[type="checkbox"]') }).first()
    const checkbox = row.locator('input[type="checkbox"]')
    await expect(checkbox).toBeVisible()
    await expect(checkbox).not.toBeChecked()
  })

  test('can toggle task done', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('toggle me')
    await page.locator('text=+ Add Task').click()
    const row = page.locator('div', { hasText: 'toggle me' }).filter({ has: page.locator('input[type="checkbox"]') }).first()
    const checkbox = row.locator('input[type="checkbox"]')
    await checkbox.check()
    await expect(checkbox).toBeChecked()
  })

  test('clear done button appears and works', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('done task')
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
    await page.locator('[data-testid="task-input"]').fill('urgent task')
    await page.locator('text=+ Add Task').click()
    // The task row shows its meter with priority 1 -> title mentions Critical
    const taskMeter = page.locator('[data-testid="priority-meter"]').nth(1)
    await expect(taskMeter).toHaveAttribute('title', /Critical/)
  })

  test('priority meter changes and re-sorts', async ({ page }) => {
    // Create one task then change its priority via its meter
    await page.locator('[data-testid="task-input"]').fill('my task')
    await page.locator('text=+ Add Task').click()
    // Task row meter defaults to Medium (3)
    const taskMeter0 = page.locator('[data-testid="priority-meter"]').nth(1)
    await expect(taskMeter0).toHaveAttribute('title', /Medium/)
    // change to Critical (1) by clicking its segment 1
    await taskMeter0.locator('button[data-priority="1"]').click()
    await expect(taskMeter0).toHaveAttribute('title', /Critical/)
    // Create another task - it should sort below the Critical one
    await page.locator('[data-testid="task-input"]').fill('second task')
    await page.locator('text=+ Add Task').click()
    // Critical task is still first
    await expect(page.locator('[data-testid="priority-meter"]').nth(1)).toHaveAttribute('title', /Critical/)
    await expect(page.locator('[data-testid="priority-meter"]').nth(2)).toHaveAttribute('title', /Medium/)
  })

  test('sort toggle defaults to Priority', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('sortable')
    await page.locator('text=+ Add Task').click()
    // The active sort option (Priority) is highlit while Created is muted
    const created = page.locator('[data-testid="sort-created"]')
    await expect(created).toBeVisible()
  })

  test('sorting by Created shows newest first', async ({ page }) => {
    // Create two tasks; newest should win in 'created' mode.
    // Wait for each task row to appear before adding the next, because the
    // async add clears the textarea when it resolves (would wipe the next input).
    await page.locator('[data-testid="task-input"]').fill('older task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('[data-testid="task-row"]')).toHaveCount(1)
    await page.locator('[data-testid="task-input"]').fill('newer task')
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
    await page.locator('[data-testid="task-input"]').fill('critical old task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('[data-testid="task-row"]')).toHaveCount(1)
    await page.locator('[data-testid="task-input"]').fill('medium new task')
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

    await page.locator('[data-testid="task-input"]').fill('fix the sink, buy milk asap and maybe organize photos')
    await page.getByRole('button', { name: 'Organize' }).click()

    // All three tasks appear
    await expect(page.locator('text=Fix the sink')).toBeVisible()
    await expect(page.locator('text=Buy milk ASAP')).toBeVisible()
    await expect(page.locator('text=Organize photos')).toBeVisible()
    // Input is cleared after parse
    await expect(page.locator('[data-testid="task-input"]')).toHaveValue('')
  })

  test('shows task count', async ({ page }) => {
    // After cleanup, should be 0
    await expect(page.locator('footer')).toContainText('0 tasks')
    await page.locator('[data-testid="task-input"]').fill('task one')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('footer')).toContainText('1 task')
    await page.locator('[data-testid="task-input"]').fill('task two')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('footer')).toContainText('2 tasks')
  })

  test('clicking the title edits it in place and Enter saves', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('old title')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=old title')).toBeVisible()

    await page.locator('text=old title').click()
    const input = page.locator('[data-testid="task-title-input"]')
    await expect(input).toBeVisible()
    await input.fill('new title')
    await input.press('Enter')

    await expect(page.locator('text=new title')).toBeVisible()
    await expect(page.locator('text=old title')).not.toBeVisible()
  })

  test('blur saves the edited title', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('blur me')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=blur me')).toBeVisible()

    await page.locator('text=blur me').click()
    const input = page.locator('[data-testid="task-title-input"]')
    await expect(input).toBeVisible()
    await input.fill('blur saved')
    await input.blur()

    await expect(page.locator('text=blur saved')).toBeVisible()
    await expect(page.locator('text=blur me')).not.toBeVisible()
  })

  test('TODAY tab shows only tagged tasks', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('normal task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=normal task')).toBeVisible()

    await page.locator('[data-testid="task-input"]').fill('today task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=today task')).toBeVisible()

    // Tag "today task" via its toggle button. The button turns into a 3s undo
    // countdown; wait for it to expire so the change commits and the toggle
    // button reappears.
    const todayTaskRow = page.locator('[data-testid="task-row"]', { hasText: 'today task' })
    await todayTaskRow.locator('[data-testid="toggle-today"]').click()
    await expect(todayTaskRow.locator('[data-testid="toggle-today"]')).toContainText('Today', { timeout: 5000 })

    // Switch to TODAY tab: only the tagged task shows
    await page.locator('[data-testid="tab-today"]').click()
    await expect(page.locator('text=today task')).toBeVisible()
    await expect(page.locator('text=normal task')).not.toBeVisible()
  })

  test('untagging removes task from TODAY tab but keeps it in All', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('temp today')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=temp today')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'temp today' })
    await row.locator('[data-testid="toggle-today"]').click()
    await expect(row.locator('[data-testid="toggle-today"]')).toContainText('Today', { timeout: 5000 })

    // Untag it (wait for the previous undo window to expire first)
    await row.locator('[data-testid="toggle-today"]').click()
    await expect(row.locator('[data-testid="toggle-today"]')).toContainText('Today', { timeout: 5000 })

    // TODAY tab is now empty
    await page.locator('[data-testid="tab-today"]').click()
    await expect(page.locator('text=temp today')).not.toBeVisible()

    // Still present in All
    await page.locator('[data-testid="tab-all"]').click()
    await expect(page.locator('text=temp today')).toBeVisible()
  })

  test('expanding a task edits its description', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('plan trip')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=plan trip')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'plan trip' })
    const expand = row.locator('[data-testid="task-expand"]')
    await expand.click()
    const detail = page.locator('[data-testid="task-detail"]')
    await expect(detail).toBeVisible()

    const desc = detail.locator('[data-testid="task-description-input"]')
    await desc.fill('book flights and hotel for June')
    await desc.blur()

    // Collapse and re-expand: description persists (saved to backend)
    await expand.click()
    await expect(detail).not.toBeVisible()
    await expand.click()
    await expect(detail).toBeVisible()
    await expect(detail.locator('[data-testid="task-description-input"]')).toHaveValue('book flights and hotel for June')
  })

  test('recurring task auto-tags TODAY and floats to top with divider', async ({ page }) => {
    // A normal today task
    await page.locator('[data-testid="task-input"]').fill('normal today')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=normal today')).toBeVisible()
    const normalRow = page.locator('[data-testid="task-row"]', { hasText: 'normal today' })
    await normalRow.locator('[data-testid="toggle-today"]').click()
    await expect(normalRow.locator('[data-testid="toggle-today"]')).toContainText('Today', { timeout: 5000 })

    // A recurring task
    await page.locator('[data-testid="task-input"]').fill('daily habit')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=daily habit')).toBeVisible()
    const recRow = page.locator('[data-testid="task-row"]', { hasText: 'daily habit' })
    await recRow.locator('[data-testid="toggle-recurring"]').click()
    await expect(recRow.locator('[data-testid="toggle-recurring"] svg')).toBeVisible({ timeout: 5000 })
    // Recurring auto-adds the TODAY tag
    await expect(recRow.locator('[data-testid="toggle-today"]')).toContainText('Today', { timeout: 5000 })

    // TODAY tab: recurring on top, divider present, normal below
    await page.locator('[data-testid="tab-today"]').click()
    await expect(page.locator('text=daily habit')).toBeVisible()
    await expect(page.locator('text=normal today')).toBeVisible()
    await expect(page.locator('text=Recurring')).toBeVisible()

    // Recurring task appears before the normal one in the DOM
    const recPos = await page.locator('[data-testid="task-row"]', { hasText: 'daily habit' }).evaluate(el => el.getBoundingClientRect().top)
    const normalPos = await page.locator('[data-testid="task-row"]', { hasText: 'normal today' }).evaluate(el => el.getBoundingClientRect().top)
    expect(recPos).toBeLessThan(normalPos)
  })

  test('undo arrow cancels the Today toggle before it commits', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('undo me')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=undo me')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'undo me' })

    // Click Today: the button becomes a 3s undo countdown with a reverse arrow
    await row.locator('[data-testid="toggle-today"]').click()
    await expect(row.locator('[data-testid="undo-today"]')).toBeVisible()
    await expect(row.locator('[data-testid="undo-today"] svg')).toBeVisible()

    // Cancel within the window: the toggle reverts, no commit happens
    await row.locator('[data-testid="undo-today"]').click()
    await expect(row.locator('[data-testid="toggle-today"]')).toBeVisible()
    await expect(row.locator('[data-testid="toggle-today"]')).toContainText('Today')

    // The task was NOT tagged TODAY, so it must not appear in the TODAY tab
    await page.locator('[data-testid="tab-today"]').click()
    await expect(page.locator('text=undo me')).not.toBeVisible()
  })

  test('undo arrow cancels the Recur toggle before it commits', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('undo recur')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=undo recur')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'undo recur' })

    await row.locator('[data-testid="toggle-recurring"]').click()
    await expect(row.locator('[data-testid="undo-recurring"]')).toBeVisible()
    await expect(row.locator('[data-testid="undo-recurring"] svg')).toBeVisible()

    await row.locator('[data-testid="undo-recurring"]').click()
    await expect(row.locator('[data-testid="toggle-recurring"]')).toBeVisible()

    // Recurring was cancelled, so the task must not be tagged TODAY
    await page.locator('[data-testid="tab-today"]').click()
    await expect(page.locator('text=undo recur')).not.toBeVisible()
  })

  test('untagging in TODAY tab keeps the row visible with undo until it commits', async ({ page }) => {
    // Add a task and tag it TODAY (wait for the undo window to expire + commit)
    await page.locator('[data-testid="task-input"]').fill('stay in today')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=stay in today')).toBeVisible()
    const row = page.locator('[data-testid="task-row"]', { hasText: 'stay in today' })
    await row.locator('[data-testid="toggle-today"]').click()
    await expect(row.locator('[data-testid="toggle-today"]')).toContainText('Today', { timeout: 5000 })

    // Go to TODAY tab: the task is there
    await page.locator('[data-testid="tab-today"]').click()
    await expect(page.locator('text=stay in today')).toBeVisible()

    // Untag it: the row must STAY visible (with the undo button) during the
    // countdown instead of vanishing to the All list.
    const todayRow = page.locator('[data-testid="task-row"]', { hasText: 'stay in today' })
    await todayRow.locator('[data-testid="toggle-today"]').click()
    await expect(todayRow.locator('[data-testid="undo-today"]')).toBeVisible()
    await expect(page.locator('text=stay in today')).toBeVisible()

    // Click revert: the task keeps its TODAY tag and stays in the TODAY tab
    await todayRow.locator('[data-testid="undo-today"]').click()
    await expect(todayRow.locator('[data-testid="toggle-today"]')).toBeVisible()
    await expect(page.locator('text=stay in today')).toBeVisible()
  })

  test('clear done does not delete recurring tasks', async ({ page }) => {
    // A recurring task
    await page.locator('[data-testid="task-input"]').fill('daily habit')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=daily habit')).toBeVisible()
    const recRow = page.locator('[data-testid="task-row"]', { hasText: 'daily habit' })
    await recRow.locator('[data-testid="toggle-recurring"]').click()
    await expect(recRow.locator('[data-testid="toggle-recurring"] svg')).toBeVisible({ timeout: 5000 })

    // A normal task to clear
    await page.locator('[data-testid="task-input"]').fill('one off')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=one off')).toBeVisible()

    // Mark both done
    await page.locator('[data-testid="task-row"]', { hasText: 'daily habit' }).locator('input[type="checkbox"]').check()
    await page.locator('[data-testid="task-row"]', { hasText: 'one off' }).locator('input[type="checkbox"]').check()

    // Clear done
    await page.locator('text=Clear done').click()

    // Recurring survives, normal one-off is gone
    await expect(page.locator('text=daily habit')).toBeVisible()
    await expect(page.locator('text=one off')).not.toBeVisible()
  })

  test('per-task delete shows undo and reverts on cancel', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('delete me')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=delete me')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'delete me' })

    // Click delete: the row turns into a 3s undo countdown and stays visible
    await row.locator('[data-testid="task-delete"]').click()
    await expect(row.locator('[data-testid="undo-delete"]')).toBeVisible()
    await expect(row.locator('[data-testid="undo-delete"] svg')).toBeVisible()
    await expect(page.locator('text=delete me')).toBeVisible()

    // Cancel: the task is restored and stays
    await row.locator('[data-testid="undo-delete"]').click()
    await expect(row.locator('[data-testid="task-delete"]')).toBeVisible()
    await expect(page.locator('text=delete me')).toBeVisible()
  })

  test('per-task delete commits after the undo window expires', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('really delete')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=really delete')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'really delete' })
    await row.locator('[data-testid="task-delete"]').click()
    await expect(row.locator('[data-testid="undo-delete"]')).toBeVisible()

    // Wait for the 3s undo window to expire; the task is then deleted
    await expect(page.locator('text=really delete')).not.toBeVisible({ timeout: 5000 })
  })

  test('starting a task shows a live timer and adds it to TODAY', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('focus task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=focus task')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'focus task' })
    // Start the task: the focus button turns into a pause button with a timer
    await row.locator('[data-testid="task-focus"]').click()
    await expect(row.locator('[data-testid="task-focus"] svg')).toBeVisible()
    await expect(row.locator('[data-testid="task-focus"]')).toContainText(/s|m/, { timeout: 5000 })

    // Starting auto-tags TODAY: the task appears in the TODAY tab
    await page.locator('[data-testid="tab-today"]').click()
    await expect(page.locator('text=focus task')).toBeVisible()
  })

  test('pausing a task keeps it in TODAY and stops the timer', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('pause task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=pause task')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'pause task' })
    await row.locator('[data-testid="task-focus"]').click()
    await expect(row.locator('[data-testid="task-focus"] svg')).toBeVisible()

    // Pause: the button shows the play icon again but the timer text remains
    await row.locator('[data-testid="task-focus"]').click()
    await expect(row.locator('[data-testid="task-focus"]')).toContainText(/s|m/, { timeout: 5000 })

    // Pausing keeps the TODAY tag: still visible in the TODAY tab
    await page.locator('[data-testid="tab-today"]').click()
    await expect(page.locator('text=pause task')).toBeVisible()
  })

  test('timebox input saves and shows a progress bar', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('timeboxed task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=timeboxed task')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'timeboxed task' })
    // Expand the detail panel
    await row.locator('[data-testid="task-expand"]').click()
    const detail = page.locator('[data-testid="task-detail"]')
    await expect(detail).toBeVisible()

    // Set a custom timebox by typing a value
    const timebox = detail.locator('[data-testid="task-timebox-input"]')
    await timebox.fill('30')
    await timebox.blur()
    await expect(timebox).toHaveValue('30')

    // The stepper increments by 5
    await detail.locator('[data-testid="timebox-plus"]').click()
    await expect(timebox).toHaveValue('35')

    // Starting the task reveals the progress bar container
    await row.locator('[data-testid="task-focus"]').click()
    await expect(detail.locator('[data-testid="task-progress"]')).toBeVisible({ timeout: 5000 })

    // The row shows a compact "elapsed/total min" label without opening the dropdown
    await expect(row.locator('[data-testid="task-timebox-label"]')).toHaveText('0/35m')

    // Typing 0 clears the timebox and removes the progress bar + row label
    await timebox.fill('0')
    await timebox.blur()
    await expect(detail.locator('[data-testid="task-progress"]')).not.toBeVisible()
    await expect(row.locator('[data-testid="task-timebox-label"]')).not.toBeVisible()
  })

  test('reset timer zeroes elapsed time and stops the task', async ({ page }) => {
    await page.locator('[data-testid="task-input"]').fill('reset task')
    await page.locator('text=+ Add Task').click()
    await expect(page.locator('text=reset task')).toBeVisible()

    const row = page.locator('[data-testid="task-row"]', { hasText: 'reset task' })
    // Start the task
    await row.locator('[data-testid="task-focus"]').click()
    await expect(row.locator('[data-testid="task-focus"]')).toContainText(/[0-9]s/, { timeout: 5000 })

    // Reset the timer
    await row.locator('[data-testid="task-reset"]').click()
    await expect(row.locator('[data-testid="task-reset"]')).not.toBeVisible()
    // The focus button returns to the idle "play" state (no elapsed shown)
    await expect(row.locator('[data-testid="task-focus"]')).not.toContainText(/[0-9]s/)
  })
})

