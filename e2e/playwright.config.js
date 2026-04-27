const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  // 60s per test gives the cookie + cold React hydration enough room.
  timeout: 60000,
  retries: 1,
  // Single worker forces auth.spec.js and dashboard.spec.js to run serially,
  // so the Tier 4.3 auth rate limiter (5-token burst per IP, refills at
  // 10/min) is not tripped by parallel register attempts and there is no
  // racing between the two suites' page lifecycle.
  workers: 1,
  // List for stdout, HTML for the artifact CI uploads on failure.
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://localhost:3000',
    headless: true,
    // Capture every screenshot + every trace + retain video only on
    // failure. The HTML report bundles them so an artifact download has
    // the full picture without inflating success-path artifacts.
    screenshot: 'on',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
  webServer: [
    {
      command: 'cd ../frontend && npm start',
      port: 3000,
      timeout: 120000,
      reuseExistingServer: true,
    },
  ],
});
