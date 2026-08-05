import { test, expect } from '@playwright/test'

// URLs configurable for Docker (tests-e2e) vs local run.
// Locally the frontend runs on :5173 and the isolated test backend on :8100.
const FRONTEND_URL = process.env.E2E_FRONTEND_URL || 'http://localhost:5173'
const TEST_BACKEND_URL = process.env.E2E_BACKEND_URL || 'http://127.0.0.1:8100'

// Clear all tasks via the isolated test backend for deterministic test state
async function clearAllTasks(page) {
  const res = await page.request.delete(`${TEST_BACKEND_URL}/tasks/all`)
  if (!res.ok()) throw new Error(`Failed to clear tasks: ${res.status()}`)
  await page.goto(FRONTEND_URL)
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

  test('priority selector exists and defaults to medium', async ({ page }) => {
    const select = page.locator('select')
    await expect(select).toBeVisible()
    await expect(select).toHaveValue('3')
    await expect(select).toContainText('Medium')
  })
  test('can create a task with selected priority', async ({ page }) => {
    const select = page.locator('select')
    await select.selectOption('1')
    await page.locator('textarea').fill('urgent task')
    await page.locator('text=+ Add Task').click()
    // The priority dropdown shows in the task row - value 1 = Critical
    const taskSelect = page.locator('select[title="Change priority"]').first()
    await expect(taskSelect).toHaveValue('1')
  })

  test('priority dropdown changes and re-sorts', async ({ page }) => {
    // Create one task then change its priority
    await page.locator('textarea').fill('my task')
    await page.locator('text=+ Add Task').click()
    const taskSelect = page.locator('select[title="Change priority"]').first()
    // default to Medium (3)
    await expect(taskSelect).toHaveValue('3')
    // change to Critical (1)
    await taskSelect.selectOption('1')
    await expect(taskSelect).toHaveValue('1')
    // Create another task - it should sort below the Critical one
    await page.locator('textarea').fill('second task')
    await page.locator('text=+ Add Task').click()
    // Critical task is still first
    await expect(page.locator('select[title="Change priority"]').nth(0)).toHaveValue('1')
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
})

