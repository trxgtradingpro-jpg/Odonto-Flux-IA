import fs from 'node:fs';
import { defineConfig, devices } from '@playwright/test';

const chromiumExecutablePath = (() => {
  if (process.env.PLAYWRIGHT_CHROMIUM_PATH) return process.env.PLAYWRIGHT_CHROMIUM_PATH;
  const defaultLinuxPath = '/usr/bin/chromium';
  return fs.existsSync(defaultLinuxPath) ? defaultLinuxPath : undefined;
})();

const e2ePort = Number(process.env.PLAYWRIGHT_WEB_PORT || 3100);
const webBaseUrl = process.env.WEB_BASE_URL || `http://127.0.0.1:${e2ePort}`;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: webBaseUrl,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `pnpm dev --port ${e2ePort}`,
    port: e2ePort,
    reuseExistingServer: false,
    timeout: 180_000,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: chromiumExecutablePath
          ? { executablePath: chromiumExecutablePath }
          : undefined,
      },
    },
  ],
});
