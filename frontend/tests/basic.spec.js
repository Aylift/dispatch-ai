import { test, expect } from '@playwright/test'

// Helper to clean all tasks before each test for deterministic results
async function clearAllTasks(page) {
  // Toggle any unchecked tasks to done, then clear done
  const checkboxes = page.locator('input[type="checkbox"]')
  const count = await checkboxes.count()
  for (let i = 0; i < count; i++) {
    const cb = checkboxes.nth(i)
    if (!(await cb.isChecked())) {
      await cb.check()
    }
  }
  const clearBtn = page.locator('text=Clear done')
  if (await clearBtn.isVisible()) {
    await clearBtn.click()
  }
}

test.describe('Dispatch AI - basic UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:5173')
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
    const checkbox = page.locator('input[type="checkbox"]').first()
    await expect(checkbox).toBeVisible()
    await expect(checkbox).not.toBeChecked()
  })

  test('can toggle task done', async ({ page }) => {
    await page.locator('textarea').fill('toggle me')
    await page.locator('text=+ Add Task').click()
    const checkbox = page.locator('input[type="checkbox"]').first()
    await checkbox.check()
    await expect(checkbox).toBeChecked()
  })

  test('clear done button appears and works', async ({ page }) => {
    await page.locator('textarea').fill('done task')
    await page.locator('text=+ Add Task').click()
    const checkbox = page.locator('input[type="checkbox"]').first()
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
    // The priority badge shows in the task row - Critical for priority 1
    const badge = page.locator('button[title="Click to change priority"]').first()
    await expect(badge).toContainText('Critical')
  })

  test('priority badge cycles on click', async ({ page }) => {
    await page.locator('textarea').fill('cycle me')
    await page.locator('text=+ Add Task').click()
    const badge = page.locator('button[title="Click to change priority"]').first()
    // default priority 3 = Medium
    await expect(badge).toContainText('Medium')
    await badge.click()  // 3 -> 4
    await expect(badge).toContainText('Low')
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

