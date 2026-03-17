const { test, expect } = require('@playwright/test');

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/');
    // Set a token in localStorage to skip login
    await page.evaluate(() => {
      localStorage.setItem('keyforge_token', 'test-token');
    });
    await page.goto('/');
  });

  test('shows navigation sidebar', async ({ page }) => {
    await expect(page.getByText('Dashboard')).toBeVisible();
    await expect(page.getByText('Credentials')).toBeVisible();
  });

  test('can navigate between views', async ({ page }) => {
    // Click on different nav items
    await page.getByText('Credentials').click();
    await expect(page.getByText('Credential Management')).toBeVisible();

    await page.getByText('Audit Log').click();
    await page.getByText('Dashboard').click();
  });

  test('dark mode toggle works', async ({ page }) => {
    const toggle = page.getByTitle(/dark|light/i);
    if (await toggle.isVisible()) {
      await toggle.click();
      // Verify dark mode class is applied
      const html = page.locator('html');
      await expect(html).toHaveClass(/dark/);
    }
  });

  test('shows KeyForge branding in header', async ({ page }) => {
    await expect(page.getByText('KeyForge')).toBeVisible();
    await expect(page.getByText('Universal API Infrastructure Assistant')).toBeVisible();
  });

  test('logout button returns to login screen', async ({ page }) => {
    await page.getByText('Logout').click();
    // Should be back at login screen
    await expect(page.getByText('Sign In')).toBeVisible();
    await expect(page.getByPlaceholderText(/username/i)).toBeVisible();
  });

  test('navigation sidebar has all section groups', async ({ page }) => {
    await expect(page.getByText('Overview')).toBeVisible();
    await expect(page.getByText('Management')).toBeVisible();
    await expect(page.getByText('Security')).toBeVisible();
    await expect(page.getByText('Analytics')).toBeVisible();
    await expect(page.getByText('Tools')).toBeVisible();
  });
});
