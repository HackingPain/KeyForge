const { test, expect } = require('@playwright/test');

// Tier 1.7 moved JWT auth from localStorage to httpOnly cookies. These tests
// never touch localStorage; cookies are cleared per test via context.clearCookies()
// so a previous test's session cannot leak in.
test.describe('Authentication', () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test('shows AuthScreen on first visit', async ({ page }) => {
    await page.goto('/');
    // The h1 "KeyForge" anchor is ambiguous (it appears in the AuthScreen
    // heading, the page tagline, and the document title), so we anchor on the
    // form fields and the submit button instead.
    await expect(page.getByPlaceholder(/username/i)).toBeVisible();
    await expect(page.getByPlaceholder(/password/i)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('can register a new account', async ({ page }) => {
    const username = `e2e_test_${Date.now()}`;
    const password = 'E2eTestPass123!';

    await page.goto('/');
    await page.getByRole('button', { name: 'Register' }).click();
    await page.getByPlaceholder(/username/i).fill(username);
    await page.getByPlaceholder(/password/i).fill(password);
    await page.getByRole('button', { name: 'Create Account' }).click();

    // After successful register-then-auto-login, App.js flips loggedIn=true
    // and renders the header (with Logout button) and the Dashboard. A brand
    // new user has zero credentials, so Dashboard mounts FirstRunWizard,
    // whose h2 "Welcome to KeyForge" is a unique post-login marker. We look
    // for either the Logout button (always present when logged in) or the
    // wizard heading; the Logout button is the more reliable anchor because
    // the wizard can be skipped and persists that decision in localStorage.
    await expect(
      page.getByRole('button', { name: 'Logout' })
    ).toBeVisible({ timeout: 10000 });
  });

  test('shows error for invalid credentials', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder(/username/i).fill('nonexistent_e2e_user');
    await page.getByPlaceholder(/password/i).fill('WrongPass123!');
    await page.getByRole('button', { name: 'Sign In' }).click();

    // Backend returns 401 with detail "Invalid username or password";
    // AuthScreen surfaces it inside a red error banner. Match either word.
    await expect(page.getByText(/invalid|failed/i)).toBeVisible({ timeout: 5000 });
  });

  test('login form has required username and password inputs', async ({ page }) => {
    await page.goto('/');
    const usernameInput = page.getByPlaceholder(/username/i);
    const passwordInput = page.getByPlaceholder(/password/i);

    await expect(usernameInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(usernameInput).toHaveAttribute('required', '');
    await expect(passwordInput).toHaveAttribute('required', '');
  });

  test('can toggle between login and register tabs', async ({ page }) => {
    await page.goto('/');
    // Start in login mode: submit button reads "Sign In".
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();

    // Switch to register: submit button reads "Create Account".
    await page.getByRole('button', { name: 'Register' }).click();
    await expect(page.getByRole('button', { name: 'Create Account' })).toBeVisible();

    // Switch back: submit button reads "Sign In" again.
    await page.getByRole('button', { name: 'Login' }).click();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });
});
