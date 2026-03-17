const { test, expect } = require('@playwright/test');

test.describe('Authentication', () => {
  test('shows login screen on first visit', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('KeyForge')).toBeVisible();
    // Look for login form elements
    await expect(page.getByPlaceholderText(/username/i)).toBeVisible();
    await expect(page.getByPlaceholderText(/password/i)).toBeVisible();
  });

  test('can register a new account', async ({ page }) => {
    await page.goto('/');
    // Click register/signup tab if present
    const registerBtn = page.getByText(/register|sign up/i);
    if (await registerBtn.isVisible()) {
      await registerBtn.click();
    }
    await page.getByPlaceholderText(/username/i).fill('testuser_' + Date.now());
    await page.getByPlaceholderText(/password/i).fill('testpassword123');
    // Submit
    await page.getByRole('button', { name: /register|sign up|create/i }).click();
  });

  test('shows error for invalid credentials', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholderText(/username/i).fill('nonexistent');
    await page.getByPlaceholderText(/password/i).fill('wrongpass');
    await page.getByRole('button', { name: /login|sign in/i }).click();
    // Should show error
    await expect(page.getByText(/error|invalid|failed/i)).toBeVisible({ timeout: 5000 });
  });

  test('login form has required fields', async ({ page }) => {
    await page.goto('/');
    // Verify the form fields exist and are required
    const usernameInput = page.getByPlaceholderText(/username/i);
    const passwordInput = page.getByPlaceholderText(/password/i);
    await expect(usernameInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(usernameInput).toHaveAttribute('required', '');
    await expect(passwordInput).toHaveAttribute('required', '');
  });

  test('can toggle between login and register modes', async ({ page }) => {
    await page.goto('/');
    // Should start on login
    await expect(page.getByText('Sign In')).toBeVisible();

    // Switch to register
    await page.getByText('Register').click();
    await expect(page.getByText('Create Account')).toBeVisible();

    // Switch back to login
    await page.getByText('Login').click();
    await expect(page.getByText('Sign In')).toBeVisible();
  });
});
