import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:3011',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command:
        'python3 -m uvicorn app.dev.browser:app --host 127.0.0.1 --port 8011 --workers 1',
      env: {
        AI_OFFICE_M52_FIXTURE: '1',
        AI_OFFICE_M6_VISUAL: '1',
        OPENROUTER_API_KEY: 'browser-secret-sentinel',
      },
      cwd: fileURLToPath(new URL('../api', import.meta.url)),
      url: 'http://127.0.0.1:8011/docs',
      reuseExistingServer: false,
      timeout: 90000,
    },
    {
      command: 'npm run dev -- --port 3011',
      url: 'http://127.0.0.1:3011',
      reuseExistingServer: false,
      timeout: 90000,
      env: {
        AI_OFFICE_API_URL: 'http://127.0.0.1:8011',
        NEXT_TELEMETRY_DISABLED: '1',
      },
    },
  ],
});
