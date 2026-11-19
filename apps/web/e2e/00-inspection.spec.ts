import { test, expect } from '@playwright/test';

test.afterEach(async ({ page }) => {
  const cancel = page.getByRole('button', {
    name: 'Cancel / Stop run',
    exact: true,
  });
  if (await cancel.isVisible().catch(() => false)) {
    await cancel.click();
    await expect(page.getByTestId('run-status')).toHaveText('canceled');
  }
});

test('M5.2 browser inspection, future settings, permissions and explicit recovery', async ({
  page,
}) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  const leaks: string[] = [];
  const checks: Promise<void>[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('response', (response) => {
    if (
      response.url().includes('/api/backend/') &&
      response.headers()['content-type']?.includes('application/json')
    )
      checks.push(
        response
          .text()
          .then((body) => {
            for (const forbidden of [
              'browser-secret-sentinel',
              'OPENROUTER_API_KEY',
              'Authorization:',
              '"environment":',
              '"effective_environment":',
            ])
              if (body.includes(forbidden)) leaks.push(forbidden);
          })
          .catch(() => {}),
      );
  });
  await page.goto('/');
  const fixture = await page.request.post(
    'http://127.0.0.1:8011/__fixture__/m52/seed',
  );
  expect(fixture.ok()).toBe(true);
  await page.getByRole('link', { name: /Completed evidence fixture/ }).click();
  await expect(page.getByTestId('run-status')).toHaveText('completed');
  await page
    .getByRole('button', { name: 'Inspect Developer', exact: true })
    .click();
  const details = page.getByRole('article', { name: 'developer details' });
  await expect(
    details.getByText('Software Developer', { exact: true }),
  ).toBeVisible();
  await expect(
    details.getByText('deterministic-mock-v1', { exact: true }),
  ).toBeVisible();
  await expect(details.getByText(/develop ·/).first()).toBeVisible();
  await expect(
    details
      .getByRole('listitem')
      .filter({ hasText: 'operation.started' })
      .first(),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Inspect Manager', exact: true })
    .click();
  await expect(
    page.getByRole('article', { name: 'manager details' }),
  ).toContainText('Orchestrator');
  await page
    .getByRole('button', { name: 'Inspect Reviewer', exact: true })
    .click();
  await expect(
    page.getByRole('article', { name: 'reviewer details' }),
  ).toContainText('Quality Reviewer');
  await page.getByTestId('task-t0-0').click();
  await expect(page.getByText('Reviewer FAIL · round 1')).toBeVisible();
  await expect(page.getByText('Reviewer PASS · round 2')).toBeVisible();
  await expect(page.getByText(/major: Controlled defect/)).toBeVisible();
  await expect(
    page.getByText('Production code and automated tests').first(),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Open diff / file greeting.txt · attempt 1' })
    .click();
  await expect(
    page.getByRole('region', { name: 'Artifact viewer' }),
  ).toBeVisible();
  await expect(page.getByLabel('File diff')).toContainText('+hello world');
  await expect(page.getByText(/Stale evidence:/)).toBeVisible();
  await page.screenshot({
    path: 'test-results/m52-evidence.png',
    fullPage: true,
  });
  await page
    .getByRole('button', { name: 'Tool activity', exact: true })
    .click();
  await page.getByText(/^Command evidence .*succeeded/).click();
  await expect(
    page.getByText('approved disposable fixture check', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Trusted local execution:/)).toBeVisible();
  await page.getByRole('button', { name: 'Usage', exact: true }).click();
  await expect(
    page.getByText('Developer usage', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Review rounds: 2').first()).toBeVisible();
  await expect(
    page.getByText('Unavailable / Incomplete').first(),
  ).toBeVisible();
  await page.screenshot({ path: 'test-results/m52-usage.png', fullPage: true });
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await expect(
    page.getByText('Provider credentials: Configured (backend only)'),
  ).toBeVisible();
  await page
    .getByLabel('Model slug', { exact: true })
    .fill('anthropic/browser-next-model');
  await page.getByRole('button', { name: 'Save future configuration' }).click();
  await expect(page.getByText(/Saved for future runs/)).toBeVisible();
  await page.getByRole('button', { name: 'Agents', exact: true }).click();
  await page
    .getByRole('button', { name: 'Inspect Developer', exact: true })
    .click();
  await expect(
    details.getByText('deterministic-mock-v1', { exact: true }),
  ).toBeVisible();
  await page.getByRole('link', { name: '← Projects' }).click();
  await page
    .getByRole('link', { name: /Interrupted recovery fixture/ })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Recovery required', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Recovery', exact: true }).click();
  await expect(
    page.getByText('provider · UNCERTAIN', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Resume when safe' }),
  ).toBeDisabled();
  await page.getByText('Inspect retained evidence', { exact: true }).click();
  await expect(page.getByText(/Usage \/ billing unavailable/)).toBeVisible();
  await page
    .getByLabel(/^Recovery reason /)
    .fill('Abandon interrupted proposal; unknown billing remains retained');
  await page
    .getByRole('button', {
      name: 'Abandon proposal; billing remains uncertain',
    })
    .click();
  await expect(page.getByTestId('run-status')).toHaveText('paused');
  await expect(page.getByText(/Resolved:/)).toBeVisible();
  await page.screenshot({
    path: 'test-results/m52-recovery.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Resume when safe' }).click();
  await expect(page.getByTestId('run-status')).toHaveText('completed');
  await page.reload();
  await expect(page.getByTestId('run-status')).toHaveText('completed');
  await page.getByRole('link', { name: '← Projects' }).click();
  await page.getByRole('link', { name: /Completed evidence fixture/ }).click();
  await page.getByRole('button', { name: 'Request Manager planning' }).click();
  await expect(page.getByTestId('run-status')).toHaveText('awaiting approval');
  await page.getByRole('button', { name: 'Approve plan', exact: true }).click();
  await page
    .getByRole('button', { name: 'Start / Continue execution', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Permission required: fixture-check' }),
  ).toBeVisible();
  await page
    .getByLabel(/^Decision reason /)
    .fill('Approve exact command for the future-configured run');
  await page
    .getByRole('button', { name: 'Approve permission', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Permission required: fixture-check' }),
  ).not.toBeVisible();
  await page
    .getByRole('button', { name: 'Start / Continue execution', exact: true })
    .click();
  await expect(page.getByTestId('run-status')).toHaveText('completed');
  await page.getByRole('button', { name: 'Agents', exact: true }).click();
  await page
    .getByRole('button', { name: 'Inspect Developer', exact: true })
    .click();
  await expect(
    details.getByText('anthropic/browser-next-model', { exact: true }),
  ).toBeVisible();
  const invocation = details
    .locator('details')
    .filter({ hasText: 'develop ·' })
    .first();
  await invocation.locator('summary').click();
  await expect(invocation).toContainText(
    'anthropic/browser-next-model · succeeded',
  );
  // Earlier run inspection is independent from current workflow command targeting.
  const prior = await page
    .getByLabel('Inspection run')
    .locator('option')
    .nth(1)
    .getAttribute('value');
  await page.getByLabel('Inspection run').selectOption(prior!);
  await expect(
    details.getByText('deterministic-mock-v1', { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId('run-status')).toHaveText('completed');
  await page.getByLabel('Inspection run').selectOption('');
  await expect(
    details.getByText('anthropic/browser-next-model', { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: 'test-results/m52-narrow-agent.png',
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await Promise.all(checks);
  expect(errors).toEqual([]);
  expect(leaks).toEqual([]);
});
