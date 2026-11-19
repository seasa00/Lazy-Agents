import { expect, type Page } from '@playwright/test';

// Live tool commits can invalidate the command version between rendering and
// clicking. Follow the existing UI's explicit review-and-retry path; never
// bypass the backend fence or issue an API mutation from a test.
export async function requestPause(page: Page) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) => r.request().method() === 'POST' && r.url().endsWith('/pause'),
      ),
      page.getByRole('button', { name: 'Pause', exact: true }).click(),
    ]);
    if (response.status() !== 409) {
      expect(response.ok()).toBe(true);
      return;
    }
    await expect(
      page.getByRole('alert').filter({ hasText: 'Stale project version' }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Pause', exact: true }),
    ).toBeEnabled();
  }
  throw new Error(
    'Pause remained stale after reviewing refreshed backend state',
  );
}
