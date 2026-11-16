import { defineConfig, devices, type PlaywrightTestConfig } from "@playwright/test";

const PORT = process.env.PLAYWRIGHT_PORT ?? "3000";
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://localhost:${PORT}`;
const skipWebServer = process.env.PLAYWRIGHT_SKIP_WEBSERVER === "true";
const slowMo = process.env.PLAYWRIGHT_SLOW_MO
  ? Number(process.env.PLAYWRIGHT_SLOW_MO)
  : undefined;
// With PLAYWRIGHT_REPORT_DIR set (CI), the run also writes a JUnit report for
// the run summary and an HTML report with traces that CI keeps as an artifact.
const reportDir = process.env.PLAYWRIGHT_REPORT_DIR;
const reporter: PlaywrightTestConfig["reporter"] = reportDir
  ? [
      [process.env.CI ? "github" : "list"],
      ["junit", { outputFile: `${reportDir}/junit.xml` }],
      ["html", { outputFolder: `${reportDir}/html`, open: "never" }],
    ]
  : process.env.CI
    ? "github"
    : "list";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter,
  timeout: slowMo ? 180_000 : 60_000,
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(slowMo ? { launchOptions: { slowMo } } : {}),
      },
    },
  ],
  ...(skipWebServer
    ? {}
    : {
        webServer: {
          command: "npm run dev",
          url: `${baseURL}/login`,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            ...process.env,
            NEXT_PUBLIC_DEV_AUTH: "true",
          },
        },
      }),
});
