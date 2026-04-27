const { test, expect } = require('@playwright/test');

// The CI e2e-test job in .github/workflows/ci.yml starts the backend on
// port 8001 and serves the built frontend on port 3000. The committed
// frontend/.env bakes REACT_APP_BACKEND_URL=http://localhost:8001 into the
// build, so the React app talks to the backend on 8001 at runtime.
//
// Browser cookies are scoped per host (port-agnostic in the cookie spec),
// so the keyforge_token cookie set by an XHR to localhost:8001 is sent on
// subsequent XHRs to localhost:8001 from the page loaded at localhost:3000.
//
// The auth rate limiter (Tier 4.3) is strict on /api/auth/{login,register}:
// 5-token burst per IP, refills at 10/min. We only register and log in ONCE
// per worker via test.beforeAll, then share the cookies across all tests in
// the suite. App.js never renders before the auth probe completes, so each
// test polls with a generous timeout.
const BACKEND_URL = process.env.E2E_BACKEND_URL || 'http://localhost:8001';
const ASSERTION_TIMEOUT = 15000;

let sharedCookies = null;

test.beforeAll(async ({ browser }) => {
  const username = `e2e_dash_${Date.now()}`;
  const password = 'E2eDashPass123!';

  const ctx = await browser.newContext();
  const request = ctx.request;

  const registerRes = await request.post(`${BACKEND_URL}/api/auth/register`, {
    data: { username, password },
  });
  if (!registerRes.ok()) {
    await ctx.close();
    throw new Error(`register failed: ${registerRes.status()} ${await registerRes.text()}`);
  }

  const loginRes = await request.post(`${BACKEND_URL}/api/auth/login`, {
    form: { username, password },
  });
  if (!loginRes.ok()) {
    await ctx.close();
    throw new Error(`login failed: ${loginRes.status()} ${await loginRes.text()}`);
  }

  // Capture cookies for reuse in every test.
  sharedCookies = await ctx.cookies();
  await ctx.close();
});

test.describe('Dashboard', () => {
  // Inject the shared cookies into every per-test context BEFORE goto so the
  // very first request the page makes carries the keyforge_token cookie.
  test.beforeEach(async ({ context, page }) => {
    if (!sharedCookies) throw new Error('beforeAll did not establish a session');
    await context.addCookies(sharedCookies);
    // Reset both wizard and advanced-toggle flags so per-test assertions
    // start from a known state.
    await page.goto('/');
    await page.evaluate(() => {
      window.localStorage.removeItem('keyforge_wizard_dismissed');
      window.localStorage.setItem('keyforge_advanced_enabled', 'false');
    });
    await page.reload();
    await page.waitForLoadState('networkidle');
  });

  test('dashboard renders after login', async ({ page }) => {
    // App header h1 is the canonical "KeyForge" anchor.
    await expect(
      page.getByRole('heading', { name: 'KeyForge', level: 1 })
    ).toBeVisible({ timeout: ASSERTION_TIMEOUT });
    // Basic-mode sidebar always renders Credentials.
    await expect(
      page.getByRole('button', { name: /Credentials/ }).first()
    ).toBeVisible();
  });

  test('first-run wizard appears for a brand-new user with zero credentials', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Welcome to KeyForge', level: 2 })
    ).toBeVisible({ timeout: ASSERTION_TIMEOUT });
    await expect(page.getByRole('button', { name: 'Skip for now' })).toBeVisible();
  });

  test('wizard skip dismisses to the empty dashboard', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'Welcome to KeyForge', level: 2 })
    ).toBeVisible({ timeout: ASSERTION_TIMEOUT });
    await page.getByRole('button', { name: 'Skip for now' }).click();

    // After dismissal, Dashboard renders the four metric cards. Their labels
    // are stable text; pick two unique ones.
    await expect(page.getByText('Total Credentials')).toBeVisible({ timeout: ASSERTION_TIMEOUT });
    await expect(page.getByText('Health Score')).toBeVisible();
  });

  test('clicking Logout returns to AuthScreen', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: 'Logout' })
    ).toBeVisible({ timeout: ASSERTION_TIMEOUT });
    await page.getByRole('button', { name: 'Logout' }).click();

    // App.js flips loggedIn=false; AuthScreen mounts with the username input.
    await expect(page.getByPlaceholder(/username/i)).toBeVisible({ timeout: ASSERTION_TIMEOUT });
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('Basic-mode sidebar shows the canonical 5 items only', async ({ page }) => {
    // Wait for header so post-login UI has hydrated.
    await expect(
      page.getByRole('heading', { name: 'KeyForge', level: 1 })
    ).toBeVisible({ timeout: ASSERTION_TIMEOUT });

    // Basic items (sidebar buttons).
    await expect(page.getByRole('button', { name: /Profile/ }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Dashboard/ }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Credentials/ }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Audit Log/ }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /MFA Setup/ }).first()).toBeVisible();

    // Advanced items must NOT be visible while the toggle is off.
    await expect(page.getByRole('button', { name: /KMS Manager/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Envelope Encryption/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Audit Integrity/ })).toHaveCount(0);
  });

  test('flipping the Show advanced toggle reveals advanced items', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'KeyForge', level: 1 })
    ).toBeVisible({ timeout: ASSERTION_TIMEOUT });

    // Advanced items hidden initially.
    await expect(page.getByRole('button', { name: /KMS Manager/ })).toHaveCount(0);

    // Flip the Show advanced switch. App.js renders it as
    // <input type="checkbox" role="switch" aria-label="Show advanced features">.
    await page.getByRole('switch', { name: 'Show advanced features' }).check();

    // After the toggle, advanced items appear in the sidebar.
    await expect(
      page.getByRole('button', { name: /KMS Manager/ }).first()
    ).toBeVisible({ timeout: ASSERTION_TIMEOUT });
    await expect(
      page.getByRole('button', { name: /Envelope Encryption/ }).first()
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /Audit Integrity/ }).first()
    ).toBeVisible();
  });
});
