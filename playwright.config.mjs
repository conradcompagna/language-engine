import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  testMatch: '**/*.spec.mjs',
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:8791', browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: {
    command: 'node tests/browser/fixture-server.mjs',
    url: 'http://127.0.0.1:8791',
    reuseExistingServer: false
  }
});
