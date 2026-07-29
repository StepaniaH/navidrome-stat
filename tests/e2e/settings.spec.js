const { test, expect } = require("@playwright/test");

async function routeSyntheticSettings(page) {
  await page.route("**/api/auth/status", (route) =>
    route.fulfill({ json: { auth_required: false } }),
  );
  await page.route("**/api/privacy/settings", (route) =>
    route.fulfill({ json: { retention_days: null, permanent: true } }),
  );
  await page.route("**/api/privacy/retention/preview*", (route) =>
    route.fulfill({
      json: {
        retention_days: null,
        total_records: 0,
        records_to_delete: 0,
        database_bytes: 65536,
        estimated_database_bytes_after: 65536,
      },
    }),
  );
  await page.route("**/api/privacy/users", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/source/config", (route) =>
    route.fulfill({
      json: {
        url: "",
        username: "",
        password_configured: false,
      },
    }),
  );
  await page.route("**/api/servers", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/health/ready", (route) =>
    route.fulfill({
      json: {
        status: "ok",
        checks: { upstream: "ok" },
      },
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await routeSyntheticSettings(page);
});

test("privacy policy settles and remains dynamic after locale changes", async ({
  page,
}) => {
  await page.goto("/settings#privacy");
  await expect(page.locator("#policySummary")).toHaveAttribute(
    "data-state",
    "ready",
  );
  await expect(page.locator("#policySummary")).toHaveText(
    "Kept forever unless you explicitly delete it.",
  );
  await expect(page.locator("#policySummary")).not.toContainText("Loading");

  await page.getByRole("tab", { name: "Preferences" }).click();
  await page.locator("#languageSelectButton").click();
  await page.getByRole("option", { name: "简体中文" }).click();
  await page.getByRole("tab", { name: "隐私" }).click();

  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.locator("#policySummary")).toHaveText(
    "永久保留，除非你主动删除。",
  );
  await expect(page.locator("#policySummary")).not.toContainText("加载中");
});

test("custom listboxes support keyboard selection and preferences persist", async ({
  page,
}) => {
  await page.goto("/settings#preferences");
  await expect(page.locator("select")).toHaveCount(0);

  const languageButton = page.locator("#languageSelectButton");
  await languageButton.focus();
  await languageButton.press("ArrowDown");
  await expect(languageButton).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(languageButton).toHaveAttribute("aria-expanded", "false");

  await page.locator("#themeSelectButton").click();
  await page.getByRole("option", { name: /Latte/ }).click();
  await page.locator("#settingsTimezoneSelectButton").click();
  await page.getByRole("option", { name: "UTC" }).click();
  await page.locator("#motionToggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "latte");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "reduced");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "latte");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "reduced");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.locator("#settingsTimezoneSelectButton")).toContainText(
    "UTC",
  );

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#resetPreferencesBtn").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "frappe");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "system");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("privacy load failure resolves to an explicit retry state", async ({
  page,
}) => {
  await page.unroute("**/api/privacy/settings");
  await page.route("**/api/privacy/settings", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "synthetic failure" }),
    }),
  );

  await page.goto("/settings#privacy");
  await expect(page.locator("#policySummary")).toHaveAttribute(
    "data-state",
    "error",
  );
  await expect(page.locator("#policySummary")).toHaveText(
    "The policy could not be loaded. Existing data was not changed.",
  );
  await expect(page.locator("#policyRetry")).toBeVisible();
  await expect(page.locator("#policySummary")).not.toContainText("Loading");
});

test("mobile settings keep all four sections inside the viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/settings#preferences");

  await expect(page.locator('#settingsTabBar [role="tab"]')).toHaveCount(4);
  const layout = await page.evaluate(() => {
    const pageOverflow =
      document.documentElement.scrollWidth
      - document.documentElement.clientWidth;
    const panel = document.querySelector('[role="tabpanel"]:not([hidden])');
    const nav = document.querySelector("#settingsTabBar");
    return {
      pageOverflow,
      panelRight: Math.round(panel.getBoundingClientRect().right),
      viewport: document.documentElement.clientWidth,
      navRight: Math.round(nav.getBoundingClientRect().right),
    };
  });
  expect(layout.pageOverflow).toBeLessThanOrEqual(0);
  expect(layout.panelRight).toBeLessThanOrEqual(layout.viewport);
  expect(layout.navRight).toBeLessThanOrEqual(layout.viewport);

  await page.locator("#settingsTimezoneSelectButton").click();
  const menuBounds = await page.locator("#settingsTimezoneSelectMenu").evaluate(
    (menu) => {
      const bounds = menu.getBoundingClientRect();
      return {
        left: Math.round(bounds.left),
        right: Math.round(bounds.right),
        viewport: document.documentElement.clientWidth,
      };
    },
  );
  expect(menuBounds.left).toBeGreaterThanOrEqual(0);
  expect(menuBounds.right).toBeLessThanOrEqual(menuBounds.viewport);
});
