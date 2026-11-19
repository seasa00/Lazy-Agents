import { test, expect } from '@playwright/test';

async function createOfficeProject(page: import('@playwright/test').Page) {
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.goto('/projects/new');
  await page.getByLabel('Project name').fill(`M6-3D office ${Date.now()}`);
  await page
    .getByLabel('Goal', { exact: true })
    .fill('Keep this project idle for a static office scene review.');
  await page
    .getByLabel('Requirement 1 description')
    .fill('The office scene renders three agents.');
  await page
    .getByLabel('Requirement 1 acceptance criteria')
    .fill('Manager, Developer, and Reviewer are visible in the office.');
  await page
    .getByRole('button', { name: 'Create project', exact: true })
    .click();
  await expect(page.getByTestId('connection')).toHaveText(
    'Live events connected',
  );
}

test('M6-3D.1 keeps the fixed miniature office legible across themes and widths', async ({
  page,
}) => {
  await createOfficeProject(page);
  await expect(page.locator('.office-stage canvas')).toBeVisible();
  await expect(page.locator('.office-canvas')).toHaveAttribute(
    'data-scene-layout',
    'fixed',
  );

  for (const width of [1660, 1280, 820, 390]) {
    await page.setViewportSize({ width, height: 1100 });
    for (const theme of ['day', 'night'] as const) {
      const themeButton = page.getByRole('button', {
        name: theme === 'day' ? '☀ Day' : '☾ Night',
      });
      if ((await themeButton.getAttribute('aria-pressed')) !== 'true')
        await themeButton.click();
      await expect(page.locator('main')).toHaveAttribute(
        'data-office-theme',
        theme,
      );
      await expect(page.locator('.office-stage canvas')).toBeVisible();
      await expect(page.locator('.office-canvas')).toHaveAttribute(
        'data-scene-layout',
        'fixed',
      );
      await expect(page.locator('.office-stage canvas')).toHaveCount(1);
      await expect(
        page.locator('.office-stage [data-testid^="desk-"]'),
      ).toHaveCount(0);
      for (const kind of ['manager', 'developer', 'reviewer']) {
        const station = page.getByTestId(`desk-${kind}`);
        await expect(
          station.getByRole('button', {
            name: `Open ${kind[0].toUpperCase() + kind.slice(1)} details`,
          }),
        ).toBeVisible();
        await expect(station.locator('.office-status')).toBeVisible();
      }
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page
        .getByRole('region', { name: 'AI Office room' })
        .screenshot({ path: `test-results/m6-3d1-${width}-${theme}.png` });
    }
  }

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('button', { name: 'Open Manager details' }).focus();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Shift+Tab');
  expect(
    await page
      .getByRole('button', { name: 'Open Manager details' })
      .evaluate((element) => getComputedStyle(element).outlineStyle),
  ).toBe('solid');
  await expect(page.locator('.office-stage canvas')).toBeVisible();
  await page
    .getByRole('region', { name: 'AI Office room' })
    .screenshot({ path: 'test-results/m6-3d1-reduced-motion.png' });
});
