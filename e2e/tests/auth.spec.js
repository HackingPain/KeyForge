const { test, expect } = require('@playwright/test');

// Tier 1.7 moved JWT auth from localStorage to httpOnly cookies. These tests
// never touch localStorage; cookies are cleared per test via context.clearCookies()
// so a previous test's session cannot leak in.
//
// App.js renders `null` until the initial /auth/me probe resolves, so the
// AuthScreen is not in the DOM at goto time. Each assertion polls with a 15s
// timeout to give the probe + render cycle enough room on a cold CI runner.
const ASSERTION_TIMEOUT = 15000;

test.describe('Authentication', () => {
  test.beforeEach(async ({ context, page }) => {
    // Defensive: clear cookies AND localStorage, then navigate. If the page
    // somehow lands in a logged-in state anyway (observed empirically when a
    // sibling suite leaves session state in the same Playwright worker),
    // click Logout and wait for AuthScreen to re-mount.
    await context.clearCookies();
    await page.goto('/');
    await page.evaluate(() => window.localStorage.clear()).catch(() => {});
    await page.waitForLoadState('networkidle');

    const logoutButton = page.getByRole('button', { name: 'Logout' });
    if (await logoutButton.isVisible({ timeout: 1000 }).catch(() => false)) {
      await logoutButton.click();
      await context.clearCookies();
      await page.goto('/');
      await page.waitForLoadState('networkidle');
    }
  });

  test('shows AuthScreen on first visit', async ({ page }) => {
    // The h1 "KeyForge" anchor is ambiguous (it appears in the AuthScreen
    // heading, the page tagline, and the document title), so we anchor on the
    // form fields and the submit button instead.
    await expect(page.getByPlaceholder(/username/i)).toBeVisible({ timeout: ASSERTION_TIMEOUT });
    await expect(page.getByPlaceholder(/password/i)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('can register a new account', async ({ page }) => {
    const username = `e2e_test_${Date.now()}`;
    const password = 'E2eTestPass123!';

    await page.getByRole('button', { name: 'Register' }).click({ timeout: ASSERTION_TIMEOUT });
    await page.getByPlaceholder(/username/i).fill(username);
    await page.getByPlaceholder(/password/i).fill(password);
    await page.getByRole('button', { name: 'Create Account' }).click();

    // After successful register-then-auto-login, App.js flips loggedIn=true
    // and renders the header (including the Logout button). That button is
    // the most reliable post-login marker because the wizard can be skipped
    // and the dashboard metric cards depend on a non-401 /credentials fetch.
    await expect(
      page.getByRole('button', { name: 'Logout' })
    ).toBeVisible({ timeout: ASSERTION_TIMEOUT });
  });

  test('shows error for invalid credentials', async ({ page }) => {
    await page.getByPlaceholder(/username/i).fill('nonexistent_e2e_user', { timeout: ASSERTION_TIMEOUT });
    await page.getByPlaceholder(/password/i).fill('WrongPass123!');
    await page.getByRole('button', { name: 'Sign In' }).click();

    // Backend returns 401 with detail "Invalid username or password";
    // AuthScreen surfaces it inside a red error banner. Match either word.
    await expect(page.getByText(/invalid|failed/i)).toBeVisible({ timeout: ASSERTION_TIMEOUT });
  });

  test('login form has required username and password inputs', async ({ page }) => {
    const usernameInput = page.getByPlaceholder(/username/i);
    const passwordInput = page.getByPlaceholder(/password/i);

    await expect(usernameInput).toBeVisible({ timeout: ASSERTION_TIMEOUT });
    await expect(passwordInput).toBeVisible();
    await expect(usernameInput).toHaveAttribute('required', '');
    await expect(passwordInput).toHaveAttribute('required', '');
  });

  test('can toggle between login and register tabs', async ({ page }) => {
    // Start in login mode: submit button reads "Sign In".
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible({ timeout: ASSERTION_TIMEOUT });

    // Switch to register: submit button reads "Create Account".
    await page.getByRole('button', { name: 'Register' }).click();
    await expect(page.getByRole('button', { name: 'Create Account' })).toBeVisible();

    // Switch back: submit button reads "Sign In" again.
    await page.getByRole('button', { name: 'Login' }).click();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });
});
