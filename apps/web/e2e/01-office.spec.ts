import { test, expect, type Page } from '@playwright/test';
import { requestPause } from './pause';
async function capture(page: Page, name: string) {
  await page
    .getByRole('region', { name: 'AI Office room' })
    .scrollIntoViewIfNeeded();
  const stage = await page.locator('.office-stage').boundingBox();
  expect(stage).not.toBeNull();
  const office = await page
    .getByRole('region', { name: 'AI Office room' })
    .boundingBox();
  expect(office).not.toBeNull();
  await expect(page.locator('.office-stage canvas')).toBeVisible();
  for (const kind of ['manager', 'developer', 'reviewer']) {
    const station = await page.getByTestId(`desk-${kind}`).boundingBox();
    expect(station).not.toBeNull();
    // HTML status and task controls remain inside the office region, below its canvas.
    expect(station!.y).toBeGreaterThanOrEqual(stage!.y + stage!.height - 1);
    expect(station!.x).toBeGreaterThanOrEqual(office!.x);
    expect(station!.x + station!.width).toBeLessThanOrEqual(
      office!.x + office!.width + 1,
    );
  }
  await page.screenshot({ path: `test-results/m6-${name}.png` });
}
async function create(
  page: Page,
  goal = 'M6 visual verification: M6 reviewer capture. Expand a bounded disposable greeting.',
) {
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.goto('/projects/new');
  await page.getByLabel('Project name').fill('Office visual ' + Date.now());
  await page.getByLabel('Goal', { exact: true }).fill(goal);
  await page
    .getByLabel('Requirement 1 description')
    .fill('Greeting contains hello world');
  await page
    .getByLabel('Requirement 1 acceptance criteria')
    .fill('Greeting contains hello world');
  await page
    .getByRole('button', { name: 'Create project', exact: true })
    .click();
  await expect(page.getByTestId('connection')).toHaveText(
    'Live events connected',
  );
}
const desk = (page: Page, kind: string) => page.getByTestId(`desk-${kind}`);
const packet = (page: Page, type: string) =>
  page.locator(`[data-handoff-type="${type}"]`).last();
async function expectSingleHandoffCue(
  page: Page,
  type: string,
  kind: string,
  verdict?: 'PASS' | 'FAIL',
) {
  const cue = packet(page, type);
  await expect(cue).toBeVisible();
  await expect(cue).toHaveAttribute('data-handoff-kind', kind);
  if (verdict) await expect(cue).toHaveAttribute('data-verdict', verdict);
  const eventId = await cue.getAttribute('data-handoff-id');
  if (!eventId) throw new Error(`${type} cue has no committed event ID`);
  const copies = await page
    .locator('[data-handoff-id]')
    .evaluateAll(
      (nodes, id) =>
        nodes.filter((node) => node.getAttribute('data-handoff-id') === id)
          .length,
      eventId,
    );
  expect(copies).toBe(1);
  return eventId;
}
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
test('M6 headed office: real planning, handoffs, revision, pause, completion and navigation', async ({
  page,
}) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await create(page);
  await expect(desk(page, 'developer')).toHaveAttribute('data-active', 'false');
  await expect(desk(page, 'developer')).toHaveAttribute(
    'data-interaction',
    'idle',
  );
  await capture(page, '01-day-idle');
  await page.getByRole('button', { name: '☾ Night' }).click();
  await expect(page.locator('main')).toHaveAttribute(
    'data-office-theme',
    'night',
  );
  await capture(page, '02-night-idle');
  await page.reload();
  await expect(page.locator('main')).toHaveAttribute(
    'data-office-theme',
    'night',
  );
  await expect(page.locator('[data-handoff-id]')).toHaveCount(0);
  await page.getByRole('button', { name: '☀ Day' }).click();
  await page.getByRole('button', { name: 'Request Manager planning' }).click();
  await expect(desk(page, 'manager')).toHaveAttribute(
    'data-status',
    'Thinking',
  );
  await capture(page, '03-manager-thinking');
  await expect(
    page.getByRole('heading', { name: 'Manager plan' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Approve plan', exact: true }).click();
  await expect(page.getByTestId('run-status')).toHaveText('running');
  await page
    .getByRole('button', { name: 'Start / Continue execution', exact: true })
    .click();
  const initialAssignmentId = await expectSingleHandoffCue(
    page,
    'task.assigned',
    'assignment',
  );
  await expect(desk(page, 'manager')).toHaveAttribute(
    'data-interaction',
    'assigning',
  );
  await expect(desk(page, 'developer')).toHaveAttribute(
    'data-received',
    'true',
  );
  await expect(desk(page, 'developer')).toHaveAttribute(
    'data-interaction',
    'receiving',
  );
  await capture(page, '04-assignment-received');
  await expect(
    page.getByRole('heading', { name: 'Permission required: fixture-check' }),
  ).toBeVisible();
  await expect(desk(page, 'developer')).toHaveAttribute(
    'data-status',
    'Blocked',
  );
  await expect(desk(page, 'developer')).toHaveAttribute(
    'data-interaction',
    'blocked',
  );
  await expect(desk(page, 'developer')).toHaveAttribute('data-active', 'false');
  await capture(page, '05-permission-blocked');
  await page
    .getByLabel(/^Decision reason /)
    .fill('Inspected the exact disposable fixture command');
  await page
    .getByRole('button', { name: 'Approve permission', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Permission required: fixture-check' }),
  ).not.toBeVisible();
  await page
    .getByRole('button', { name: 'Start / Continue execution', exact: true })
    .click();
  await expect(desk(page, 'developer')).toHaveAttribute('data-active', 'true');
  await expect(desk(page, 'developer')).toHaveAttribute(
    'data-interaction',
    'working',
  );
  await expect(
    page
      .getByRole('article', { name: 'developer details' })
      .locator('summary')
      .filter({ hasText: 'develop ·' })
      .first(),
  ).toBeVisible();
  await capture(page, '06-developer-working');
  await requestPause(page);
  await expect(page.getByTestId('run-status')).toHaveText('pause requested');
  await expect(desk(page, 'developer')).toHaveAttribute('data-active', 'true');
  await capture(page, '07-pause-requested');
  await expect(page.getByTestId('run-status')).toHaveText('paused');
  await expect(page.locator('[data-active="true"]')).toHaveCount(0);
  await expect(page.locator('[data-handoff-id]')).toHaveCount(0);
  await capture(page, '08-paused');
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(desk(page, 'developer')).toHaveAttribute('data-active', 'true');
  await capture(page, '09-resumed');
  const firstSubmissionId = await expectSingleHandoffCue(
    page,
    'submission.admitted',
    'submission',
  );
  await expect(desk(page, 'developer')).toHaveAttribute(
    'data-interaction',
    'submitting',
  );
  await expect(desk(page, 'reviewer')).toHaveAttribute(
    'data-interaction',
    'receiving',
  );
  await capture(page, '10-submission-handoff');
  await expect(desk(page, 'reviewer')).toHaveAttribute(
    'data-status',
    'Reviewing',
  );
  await expect(desk(page, 'reviewer')).toHaveAttribute(
    'data-interaction',
    'reviewing',
  );
  await capture(page, '11-reviewing');
  const failedReviewId = await expectSingleHandoffCue(
    page,
    'review.completed',
    'review',
    'FAIL',
  );
  await expect(packet(page, 'review.completed')).toContainText('FAIL');
  await expect(packet(page, 'review.completed')).toHaveAttribute(
    'data-verdict',
    'FAIL',
  );
  await expect(desk(page, 'reviewer')).toHaveAttribute(
    'data-interaction',
    'review-fail',
  );
  await capture(page, '12-review-fail');
  const revisionId = await expectSingleHandoffCue(
    page,
    'revision.requested',
    'revision',
  );
  await expect(desk(page, 'developer')).toHaveAttribute(
    'data-interaction',
    'receiving',
  );
  await capture(page, '13-manager-revision');
  await expect(desk(page, 'developer')).toHaveAttribute('data-active', 'true');
  const revisionAssignmentId = await expectSingleHandoffCue(
    page,
    'task.assigned',
    'assignment',
  );
  expect(revisionAssignmentId).not.toBe(initialAssignmentId);
  const secondSubmissionId = await expectSingleHandoffCue(
    page,
    'submission.admitted',
    'submission',
  );
  expect(secondSubmissionId).not.toBe(firstSubmissionId);
  const passedReviewId = await expectSingleHandoffCue(
    page,
    'review.completed',
    'review',
    'PASS',
  );
  expect(passedReviewId).not.toBe(failedReviewId);
  await expect(packet(page, 'review.completed')).toContainText('PASS');
  await expect(desk(page, 'reviewer')).toHaveAttribute(
    'data-interaction',
    'review-pass',
  );
  const acceptedId = await expectSingleHandoffCue(
    page,
    'task.accepted',
    'accepted',
    'PASS',
  );
  expect(acceptedId).not.toBe(revisionId);
  await capture(page, '14-review-pass');
  await expect(page.getByTestId('run-status')).toHaveText('completed');
  await expect(desk(page, 'reviewer')).toHaveAttribute('data-status', 'Done');
  await expect(page.getByTestId('task-t0-0')).toContainText('DONE');
  await capture(page, '15-completed');
  for (const kind of ['Manager', 'Developer', 'Reviewer']) {
    await page
      .getByRole('button', { name: `Open ${kind} details`, exact: true })
      .click();
    await expect(
      page.getByRole('article', { name: `${kind.toLowerCase()} details` }),
    ).toBeVisible();
    await page.screenshot({ path: `test-results/m6-16-${kind}-details.png` });
  }
  await desk(page, 'reviewer')
    .getByRole('button', { name: 'Last review: PASS ↗' })
    .click();
  await expect(page.getByRole('heading', { name: /Attempt 1/ })).toBeVisible();
  await page.screenshot({ path: 'test-results/m6-17-task-details.png' });
  await page.getByRole('link', { name: 'Activity', exact: true }).click();
  await expect(
    page.getByRole('list', { name: 'Committed activity' }),
  ).toContainText('Submission created');
  await page.screenshot({ path: 'test-results/m6-18-activity.png' });
  await page
    .getByRole('button', { name: 'Open detailed resource usage' })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Durable usage', exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: 'test-results/m6-19-usage.png' });
  await page.getByRole('button', { name: '☾ Night' }).click();
  await capture(page, '20-night-completed');
  await page.setViewportSize({ width: 820, height: 1180 });
  await capture(page, '21-tablet');
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole('region', { name: 'AI Office room' })
    .screenshot({ path: 'test-results/m6-22-mobile.png' });
  for (const kind of ['manager', 'developer', 'reviewer'])
    await expect(desk(page, kind)).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await capture(page, '23-reduced-motion');
  await page.getByRole('button', { name: 'Open Manager details' }).focus();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Shift+Tab');
  expect(
    await page
      .getByRole('button', { name: 'Open Manager details' })
      .evaluate((el) => getComputedStyle(el).outlineStyle),
  ).toBe('solid');
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('article', { name: 'manager details' }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test('M6 reconnect restores state, suppresses historical handoffs and exposes fresh committed work cues', async ({
  page,
  context,
}) => {
  test.setTimeout(90000);
  await create(
    page,
    'M6 visual verification: Expand a bounded disposable greeting.',
  );
  await page.getByRole('button', { name: 'Request Manager planning' }).click();
  await expect(
    page.getByRole('heading', { name: 'Manager plan' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Approve plan', exact: true }).click();
  await expect(page.getByTestId('run-status')).toHaveText('running');
  await page
    .getByRole('button', { name: 'Start / Continue execution', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Permission required: fixture-check' }),
  ).toBeVisible();
  await page.getByLabel(/^Decision reason /).fill('Inspected');
  await page
    .getByRole('button', { name: 'Approve permission', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Permission required: fixture-check' }),
  ).not.toBeVisible();
  await page
    .getByRole('button', { name: 'Start / Continue execution', exact: true })
    .click();
  await expect(desk(page, 'developer')).toHaveAttribute('data-active', 'true');
  await expect(
    page
      .getByRole('article', { name: 'developer details' })
      .locator('summary')
      .filter({ hasText: 'develop ·' })
      .first(),
  ).toBeVisible();
  await context.setOffline(true);
  await expect(page.getByTestId('connection')).toContainText(
    'SSE disconnected',
  );
  await capture(page, '24-disconnected');
  // Backend keeps executing. Give it enough time to commit the first submission
  // while the browser is absent; this delay never manufactures UI state.
  await page.waitForTimeout(4500);
  await context.setOffline(false);
  await expect(page.getByTestId('connection')).toHaveText(
    'Live events connected',
  );
  await expect(
    page.getByRole('list', { name: 'Committed activity' }),
  ).toContainText('Submission created');
  await expect(packet(page, 'submission.admitted')).toHaveCount(0);
  await capture(page, '25-reconnected');
  await expect(packet(page, 'revision.requested')).toBeVisible();
  await expect(desk(page, 'developer')).toHaveAttribute(
    'data-received',
    'true',
  );
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(packet(page, 'task.assigned')).toBeVisible();
  expect(
    await packet(page, 'task.assigned').evaluate(
      (el) => getComputedStyle(el).animationName,
    ),
  ).toBe('none');
  await capture(page, '26-reduced-motion-handoff');
  await expect(desk(page, 'developer')).toHaveAttribute('data-active', 'true');
  expect(
    await page
      .locator('.office-stage canvas')
      .evaluate((el) => getComputedStyle(el).animationName),
  ).toBe('none');
  await page.reload();
  await expect(page.getByTestId('connection')).toHaveText(
    'Live events connected',
  );
  await expect(packet(page, 'task.assigned')).toHaveCount(0);
  await expect(page.getByTestId('run-status')).toHaveText('completed');
});
