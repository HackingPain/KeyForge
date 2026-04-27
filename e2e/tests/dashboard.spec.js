const { test, expect } = require('@playwright/test');

// The CI e2e-test job in .github/workflows/ci.yml starts the backend on
// port 8001 and serves the built frontend on port 3000. The committed
// frontend/.env bakes REACT_APP_BACKEND_URL=http://localhost:8001 into the
// build, so the React app talks to the backend on 8001 at runtime.
//
// Browser cookies are scoped per host (port-agnostic in the cookie spec),
// so the keyforge_token cookie set by an XHR to localhost:8001 is sent on
// subsequent XHRs to localhost:8001 from the page loaded at localhost:3000.
// Playwright's APIRequestContext (page.request) shares the cookie jar with
// the page, so logging in via page.request.post('http://localhost:8001/...')
// authenticates the page that follows page.goto('/').
const BACKEND_URL = process.env.E2E_BACKEND_URL || 'http://localhost:8001';

/**
 * Register and log in a fresh test user. Returns the username.
 *
 * register: JSON body { username, password }
 * login: OAuth2PasswordRequestForm-encoded form { username, password }
 *
 * Both endpoints are CSRF-exempt (see backend/middleware/csrf.py EXEMPT_PATHS),
 * so no X-CSRF-Token header is required for the initial handshake.
 */
async function registerAndLogin(request, suffix) {
  const username = `e2e_dash_${Date.now()}_${suffix}`;
  const password = 'E2eDashPass123!';

  const registerRes = await request.post(`${BACKEND_URL}/api/auth/register`, {
    data: { username, password },
  });
  if (!registerRes.ok()) {
    throw new Error(
      `register failed: ${registerRes.status()} ${await registerRes.text()}`
    );
  }

  const loginRes = await request.post(`${BACKEND_URL}/api/auth/login`, {
    form: { username, password },
  });
  if (!loginRes.ok()) {
    throw new Error(
      `login failed: ${loginRes.status()} ${await loginRes.text()}`
    );
  }

  return { username, password };
}

test.describe('Dashboard', () => {
  // Per-test register + login. Cheaper than storageState for a small suite,
  // and gives every test a clean user with no credentials so wizard-vs-empty
  // assertions stay deterministic.
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
    // Clear localStorage too, so the wizard-dismissed flag from a prior test
    // run never leaks across tests.
    // We need a page to access localStorage; a blank navigation is enough.
  });

  test('dashboard renders after login', async ({ page, context }, testInfo) => {
    await registerAndLogin(context.request, `render_${testInfo.workerIndex}`);
    await page.goto('/');
    // Clear any wizard-dismissed flag from a prior worker run; this user is
    // fresh, the wizard SHOULD appear for them.
    await page.evaluate(() => window.localStorage.removeItem('keyforge_wizard_dismissed'));
    await page.reload();

    // Header h1 is the canonical "KeyForge" anchor. App.js renders it inside
    // <header> so we scope by role to avoid the Welcome heading inside the
    // FirstRunWizard component.
    await expect(
      page.getByRole('heading', { name: 'KeyForge', level: 1 })
    ).toBeVisible();
    // Basic-mode sidebar always renders Credentials.
    await expect(
      page.getByRole('button', { name: /Credentials/ }).first()
    ).toBeVisible();
  });

  test('first-run wizard appears for a brand-new user with zero credentials', async ({ page, context }, testInfo) => {
    await registerAndLogin(context.request, `wizard_${testInfo.workerIndex}`);
    await page.goto('/');
    await page.evaluate(() => window.localStorage.removeItem('keyforge_wizard_dismissed'));
    await page.reload();

    // FirstRunWizard renders inside Dashboard when credentials.length === 0
    // and the dismissed flag is unset. Welcome step h2 is unique post-login.
    await expect(
      page.getByRole('heading', { name: 'Welcome to KeyForge', level: 2 })
    ).toBeVisible({ timeout: 10000 });
    // "Skip for now" is the dismissal link rendered alongside the Continue
    // button on the Welcome step.
    await expect(page.getByRole('button', { name: 'Skip for now' })).toBeVisible();
  });

  test('wizard skip dismisses to the empty dashboard', async ({ page, context }, testInfo) => {
    await registerAndLogin(context.request, `skip_${testInfo.workerIndex}`);
    await page.goto('/');
    await page.evaluate(() => window.localStorage.removeItem('keyforge_wizard_dismissed'));
    await page.reload();

    // Wait for the wizard, then dismiss it.
    await expect(
      page.getByRole('heading', { name: 'Welcome to KeyForge', level: 2 })
    ).toBeVisible({ timeout: 10000 });
    await page.getByRole('button', { name: 'Skip for now' }).click();

    // After dismissal, Dashboard renders the four metric cards. "Total
    // Credentials" is the first card label and is unique on the page.
    await expect(page.getByText('Total Credentials')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Health Score')).toBeVisible();
  });

  test('clicking Logout returns to AuthScreen', async ({ page, context }, testInfo) => {
    await registerAndLogin(context.request, `logout_${testInfo.workerIndex}`);
    await page.goto('/');

    await expect(
      page.getByRole('button', { name: 'Logout' })
    ).toBeVisible({ timeout: 10000 });
    await page.getByRole('button', { name: 'Logout' }).click();

    // App.js flips loggedIn=false; AuthScreen mounts with the username input.
    await expect(page.getByPlaceholder(/username/i)).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('Basic-mode sidebar shows the canonical 5 items only', async ({ page, context }, testInfo) => {
    await registerAndLogin(context.request, `basic_${testInfo.workerIndex}`);
    await page.goto('/');
    // Force advanced=false. The toggle persists in localStorage; a worker
    // that previously ran the advanced test could leave it on.
    await page.evaluate(() => {
      window.localStorage.setItem('keyforge_advanced_enabled', 'false');
      window.localStorage.removeItem('keyforge_wizard_dismissed');
    });
    await page.reload();

    // Wait for header so we know the post-login UI has hydrated.
    await expect(
      page.getByRole('heading', { name: 'KeyForge', level: 1 })
    ).toBeVisible();

    // Basic items (sidebar buttons). The button accessible name includes
    // the leading emoji icon (e.g. "👤 Profile"), so we match by regex
    // anchored to the visible label.
    await expect(page.getByRole('button', { name: /Profile/ }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Dashboard/ }).first()).toBeVisible();
    // Two sidebar items contain "Credentials" in basic mode? No: only one
    // ("Credentials"). In advanced mode "Credential Groups" / "Credential
    // Proxy" / "Credential Permissions" exist, but they are advanced and
    // hidden right now.
    await expect(page.getByRole('button', { name: /Credentials/ }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Audit Log/ }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /MFA Setup/ }).first()).toBeVisible();

    // Advanced items must NOT be visible while the toggle is off.
    // The KMS Manager / Envelope Encryption / Audit Integrity sidebar items
    // each wrap their core term in a JargonTerm which renders an inner span
    // with role="button". To avoid matching the inner spans, we look for
    // the outer sidebar button by the regex that matches the full visible
    // label and assert there are zero of them.
    await expect(page.getByRole('button', { name: /KMS Manager/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Envelope Encryption/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Audit Integrity/ })).toHaveCount(0);
  });

  test('flipping the Show advanced toggle reveals advanced items', async ({ page, context }, testInfo) => {
    await registerAndLogin(context.request, `adv_${testInfo.workerIndex}`);
    await page.goto('/');
    await page.evaluate(() => {
      window.localStorage.setItem('keyforge_advanced_enabled', 'false');
      window.localStorage.removeItem('keyforge_wizard_dismissed');
    });
    await page.reload();

    await expect(
      page.getByRole('heading', { name: 'KeyForge', level: 1 })
    ).toBeVisible();

    // Advanced items hidden initially.
    await expect(page.getByRole('button', { name: /KMS Manager/ })).toHaveCount(0);

    // Flip the Show advanced switch. App.js renders it as
    // <input type="checkbox" role="switch" aria-label="Show advanced features">
    // wrapped in a label whose visible text is "Show advanced".
    await page.getByRole('switch', { name: 'Show advanced features' }).check();

    // After the toggle, advanced items appear in the sidebar.
    await expect(
      page.getByRole('button', { name: /KMS Manager/ }).first()
    ).toBeVisible({ timeout: 5000 });
    await expect(
      page.getByRole('button', { name: /Envelope Encryption/ }).first()
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /Audit Integrity/ }).first()
    ).toBeVisible();
  });
});
