const { defineConfig, devices } = require("@playwright/test");
const os = require("os");
const path = require("path");

const databasePath = path.join(
  os.tmpdir(),
  `navidrome-stat-e2e-${process.pid}.sqlite`,
);

module.exports = defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:39422",
    trace: "retain-on-failure",
    ...(process.env.CI ? {} : { channel: "chrome" }),
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `${process.env.CI ? "python3" : ".venv/bin/python"} -m uvicorn src.main:app --host 127.0.0.1 --port 39422`,
    url: "http://127.0.0.1:39422/health",
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      ...process.env,
      PYTHON_DOTENV_DISABLED: "1",
      DATABASE_URL: databasePath,
      NAVIDROME_URL: "",
      NAVIDROME_USER: "",
      NAVIDROME_PASS: "",
      STATS_API_TOKEN: "",
    },
  },
});
