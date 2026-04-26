const { test, expect } = require('@playwright/test');

test.describe('Authentication', () => {
  test('shows login screen on first visit', async ({ page }) => {
    await page.goto('/');
    // The h1 is the canonical "KeyForge" anchor; the tagline + page title also
    // contain the word, so getByText is ambiguous in strict mode.
    await expect(page.getByRole('heading', { name: 'KeyForge' })).toBeVisible();
    await expect(page.getByPlaceholder(/username/i)).toBeVisible();
    await expect(page.getByPlaceholder(/password/i)).toBeVisible();
  });

  test('can register a new account', async ({ page }) => {
    await page.goto('/');
    // AuthScreen has explicit Login / Register tabs; click the Register tab.
    await page.getByRole('button', { name: 'Register' }).click();
    await page.getByPlaceholder(/username/i).fill('testuser_' + Date.now());
    await page.getByPlaceholder(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /create account/i }).click();
  });

  test('shows error for invalid credentials', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder(/username/i).fill('nonexistent');
    await page.getByPlaceholder(/password/i).fill('wrongpass');
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page.getByText(/invalid|failed/i)).toBeVisible({ timeout: 5000 });
  });

  test('login form has required fields', async ({ page }) => {
    await page.goto('/');
    const usernameInput = page.getByPlaceholder(/username/i);
    const passwordInput = page.getByPlaceholder(/password/i);
    await expect(usernameInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(usernameInput).toHaveAttribute('required', '');
    await expect(passwordInput).toHaveAttribute('required', '');
  });

  test('can toggle between login and register modes', async ({ page }) => {
    await page.goto('/');
    // The form's submit button is the unique Sign In anchor; the Login tab
    // button is also called "Login" but the submit button is the affordance
    // we care about for "am I in login mode".
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();

    await page.getByRole('button', { name: 'Register' }).click();
    await expect(page.getByRole('button', { name: 'Create Account' })).toBeVisible();

    await page.getByRole('button', { name: 'Login' }).click();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });
});
