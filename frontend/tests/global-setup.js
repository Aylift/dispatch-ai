// Warm up Vite before the first test so the initial page.goto doesn't time out
// on a cold compile. In Docker the frontend is served on :5173 (see
// playwright.config.js webServer). We fetch the root and the entry module so
// Vite pre-bundles deps and compiles App.vue once, up front.
export default async function globalSetup() {
  const base = process.env.E2E_FRONTEND_URL || 'http://localhost:5173'
  const urls = [
    `${base}/`,
    `${base}/src/main.js`,
  ]
  for (const url of urls) {
    try {
      await fetch(url)
    } catch {
      // Server may still be starting; the first test will retry via its own
      // navigation. Non-fatal.
    }
  }
}
