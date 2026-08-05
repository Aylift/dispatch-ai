import { defineConfig } from '@playwright/test'

// URL configuration:
//  - E2E_FRONTEND_URL / baseURL where the browser loads the app.
//  - E2E_BACKEND_URL  the isolated test backend that must be reachable.
// In local dev, vite runs on :5173 and the isolated test backend on :8100.
const PORTAL = process.env.E2E_FRONTEND_URL || 'http://localhost:5173'
const TEST_BACKEND = process.env.E2E_BACKEND_URL || 'http://127.0.0.1:8100'

// When RUN_LOCAL_E2E=1, start our own vite inside this process so the frontend
// is served with the correct VITE_API_URL pointing at the isolated test backend.
const startOwnVite = process.env.RUN_LOCAL_E2E === '1'

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
  },
  webServer: startOwnVite
    ? [
        {
          command: 'npx vite dev --host 0.0.0.0 --port 5173',
          port: 5173,
          env: { VITE_API_URL: TEST_BACKEND },
          reuseExistingServer: true,
        },
      ]
    : undefined,
})
