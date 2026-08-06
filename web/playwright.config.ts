import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.FIN_OPS_E2E_PORT ?? 5177);
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${PORT}`;
const skipWebServer = process.env.FIN_OPS_E2E_SKIP_WEBSERVER === "1";
const workbenchVisibilitySloEnabled = process.env.FIN_OPS_E2E_WORKBENCH_VISIBILITY_SLO === "1";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  forbidOnly: !!process.env.CI,
  expect: {
    timeout: 8_000,
  },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    trace: workbenchVisibilitySloEnabled ? "off" : "retain-on-failure",
    screenshot: workbenchVisibilitySloEnabled ? "off" : "only-on-failure",
    video: workbenchVisibilitySloEnabled ? "off" : "retain-on-failure",
  },
  webServer: skipWebServer
    ? undefined
    : {
        command: `npm run dev:raw -- --host 127.0.0.1 --port ${PORT}`,
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
