const { defineConfig, devices } = require("@playwright/test");
const os = require("os");
const path = require("path");

const databasePath = path.join(
  os.tmpdir(),
  `navidrome-stat-e2e-${process.pid}.sqlite`,
);
const realDatabasePath = path.join(os.tmpdir(), `navidrome-stat-e2e-real-${process.pid}.sqlite`);
const serverEnvironment = {
  ...process.env,
  PYTHON_DOTENV_DISABLED: "1",
  NAVIDROME_URL: "",
  NAVIDROME_USER: "",
  NAVIDROME_PASS: "",
  STATS_API_TOKEN: "",
  STATS_READ_ONLY_TOKEN: "",
  STATS_READ_ONLY_SOURCE_ID: "",
  STATS_READ_ONLY_USERNAME: "",
  LISTENBRAINZ_INGEST_TOKEN: "",
  LISTENBRAINZ_INGEST_USERNAME: "",
};

module.exports = defineConfig({
  testDir: "./tests/e2e",
  globalTeardown: require.resolve("./tests/e2e/global-teardown.js"),
  metadata: { e2eDatabasePaths: [databasePath, realDatabasePath] },
  timeout: 30_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:39422",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [{
    command: `${process.env.CI ? "python3" : ".venv/bin/python"} -m uvicorn src.main:app --host 127.0.0.1 --port 39422`,
    url: "http://127.0.0.1:39422/health",
    reuseExistingServer: false,
    timeout: 30_000,
    env: { ...serverEnvironment, DATABASE_URL: databasePath },
  }, {
    command: `${process.env.CI ? "python3" : ".venv/bin/python"} tests/e2e/real_server.py`,
    url: "http://127.0.0.1:39424/health",
    reuseExistingServer: false,
    timeout: 30_000,
    env: { ...serverEnvironment, DATABASE_URL: realDatabasePath },
  }],
});
