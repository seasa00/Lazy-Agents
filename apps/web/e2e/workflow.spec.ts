import { requestPause } from './pause';
import { test, expect, type Page } from '@playwright/test';
test.afterEach(async ({ page, context }) => {
  await context.setOffline(false);
  const cancel = page.getByRole('button', {
    name: 'Cancel / Stop run',
    exact: true,
  });
  if (await cancel.isVisible().catch(() => false)) {
    await cancel.click();
    await expect(page.getByTestId('run-status')).toHaveText('canceled');
  }
});
async function create(page: Page, name: string) {
  await page.goto('/');
  await page.getByRole('link', { name: 'Create project', exact: true }).click();
  await page.getByLabel('Project name').fill(name);
  await page
    .getByLabel('Goal', { exact: true })
    .fill('Expand a bounded disposable greeting.');
  await page
    .getByLabel('Requirement 1 description')
    .fill('Greeting contains hello world');
  await page
    .getByLabel('Requirement 1 acceptance criteria')
    .fill('Greeting contains hello world');
  await page
    .getByRole('button', { name: 'Create project', exact: true })
    .click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Request Manager planning' }).click();
  await expect(
    page.getByRole('heading', { name: 'Manager plan' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Approve plan', exact: true }).click();
  await expect(page.getByTestId('run-status')).toHaveText('running');
}
async function requestPermission(page: Page) {
  await page
    .getByRole('button', { name: 'Start / Continue execution', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Permission required: fixture-check' }),
  ).toBeVisible();
}
test('complete browser workflow: permission, revision, pause, refresh, resume, final result', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const name = 'Browser greeting ' + Date.now();
  await create(page, name);
  await requestPermission(page);
  await expect(
    page.getByText(/approved disposable fixture check/),
  ).toBeVisible();
  await page.screenshot({
    path: 'test-results/browser-permission.png',
    fullPage: true,
  });
  await page
    .getByLabel(/^Decision reason /)
    .fill('Approve exact harmless command in disposable workspace');
  await page
    .getByRole('button', { name: 'Approve permission', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Permission required: fixture-check' }),
  ).not.toBeVisible();
  await page
    .getByRole('button', { name: 'Start / Continue execution', exact: true })
    .click();
  await expect(
    page.getByText('Developer started', { exact: true }),
  ).toBeVisible();
  // A committed activity event can arrive before its snapshot refresh. Wait for
  // the authoritative pending invocation before capturing the command version.
  await expect(
    page.getByRole('article', { name: 'developer details' }),
  ).toContainText('running · Invocation pending');
  await requestPause(page);
  await expect(
    page.getByText(/Pause requested — waiting for the backend safe boundary/),
  ).toBeVisible();
  await expect(page.getByTestId('run-status')).toHaveText('pause requested');
  await page.screenshot({
    path: 'test-results/browser-pause-requested.png',
    fullPage: true,
  });
  await expect(page.getByTestId('run-status')).toHaveText('paused');
  await page.screenshot({
    path: 'test-results/browser-paused.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(
    page.getByText('Revision requested', { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId('task-t0-0')).toContainText('Reviews: 1');
  // Refresh while the second Developer invocation is executing.
  await expect(page.getByTestId('task-t0-0')).toContainText('IN_PROGRESS');
  await page.reload();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  await expect(page.getByTestId('task-t0-0')).toContainText('Reviews: 1');
  await expect(page.getByTestId('connection')).toHaveText(
    'Live events connected',
  );
  await page.screenshot({
    path: 'test-results/browser-refreshed.png',
    fullPage: true,
  });
  await expect(
    page.getByRole('heading', { name: 'Final result', exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId('run-status')).toHaveText('completed');
  await expect(page.getByTestId('task-t0-0')).toContainText('DONE');
  await expect(page.getByTestId('task-t0-0')).toContainText('Reviews: 2');
  await expect(
    page.getByRole('link', { name: 'Open backend evidence JSON' }),
  ).toBeVisible();
  const ids = await page
    .locator('[data-event-id]')
    .evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('data-event-id')),
    );
  expect(new Set(ids).size).toBe(ids.length);
  expect(errors).toEqual([]);
  await page.screenshot({
    path: 'test-results/browser-completed.png',
    fullPage: true,
  });
});
test('permission denial is durable, then cancel through the browser', async ({
  page,
}) => {
  await create(page, 'Denied permission ' + Date.now());
  await requestPermission(page);
  await page
    .getByLabel(/^Decision reason /)
    .fill('Do not execute this fixture command');
  await page
    .getByRole('button', { name: 'Deny permission', exact: true })
    .click();
  await expect(
    page.getByText(/Permission denied: fixture-check/),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText(/Permission denied: fixture-check/),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Cancel / Stop run', exact: true })
    .click();
  await expect(page.getByTestId('run-status')).toHaveText('canceled');
});
test('SSE disconnect indicator and reconnect restore authoritative progress', async ({
  page,
  context,
}) => {
  await create(page, 'Reconnect ' + Date.now());
  await requestPermission(page);
  await context.setOffline(true);
  await expect(page.getByTestId('connection')).toContainText(
    'SSE disconnected',
  );
  await context.setOffline(false);
  await expect(page.getByTestId('connection')).toHaveText(
    'Live events connected',
  );
  await expect(
    page.getByRole('heading', { name: 'Permission required: fixture-check' }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Cancel / Stop run', exact: true })
    .click();
  await expect(page.getByTestId('run-status')).toHaveText('canceled');
});

test('unavailable event cursor refetches snapshot and reconnects', async ({
  page,
}) => {
  let intercepted = false;
  await page.route('**/api/backend/projects/*/events?*', async (route) => {
    if (!intercepted) {
      intercepted = true;
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: '{"detail":"unavailable cursor; fetch snapshot"}',
      });
    } else await route.continue();
  });
  await create(page, 'Snapshot reset ' + Date.now());
  await expect(page.getByTestId('connection')).toHaveText(
    'Live events connected',
  );
  expect(intercepted).toBe(true);
  await expect(
    page.getByRole('heading', { name: 'Manager plan' }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Cancel / Stop run', exact: true })
    .click();
  await expect(page.getByTestId('run-status')).toHaveText('canceled');
});
