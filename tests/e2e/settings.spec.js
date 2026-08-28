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
  await page.route("**/api/privacy/storage", (route) =>
    route.fulfill({
      json: {
        database_bytes: 65536,
        total_records: 0,
        history_records: 0,
        attempt_records: 0,
        estimated_data_bytes: 0,
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
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/settings#preferences");
  await expect(page.locator("select")).toHaveCount(0);

  const languageButton = page.locator("#languageSelectButton");
  await languageButton.focus();
  await languageButton.press("ArrowDown");
  await expect(languageButton).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(languageButton).toHaveAttribute("aria-expanded", "false");

  await page.locator('#themeModePicker input[value="light"]').check();
  await page.locator('#themePalettePicker input[value="catppuccin"]').check();
  await page.locator("#settingsTimezoneSelectButton").click();
  await page.getByRole("option", { name: "UTC" }).click();
  await page.locator("#motionToggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "latte");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "reduced");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "latte");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "reduced");
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.locator("#settingsTimezoneSelectButton")).toContainText(
    "UTC",
  );

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("#resetPreferencesBtn").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "builtin-dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme-mode", "system");
  await expect(page.locator("html")).toHaveAttribute("data-palette", "builtin");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "system");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("system mode follows the OS and keeps an unavailable palette selected", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/settings#preferences");

  const nord = page.locator('#themePalettePicker input[value="nord"]');
  await nord.check();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "nord");
  await expect(nord).toBeChecked();

  const systemMode = page.locator('#themeModePicker input[value="system"]');
  const darkMode = page.locator('#themeModePicker input[value="dark"]');
  await systemMode.focus();
  await systemMode.press("ArrowRight");
  await expect(darkMode).toBeChecked();
  await systemMode.check();
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "builtin-light");
  await expect(page.locator("html")).toHaveAttribute("data-palette", "nord");
  await expect(nord).toBeChecked();
  await expect(nord).toBeDisabled();
  await expect(nord.locator("..")).toHaveClass(/is-unavailable/);

  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "nord");
  await expect(nord).toBeEnabled();
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

  const paletteBounds = await page.locator("#themePalettePicker").evaluate(
    (picker) => {
      const bounds = picker.getBoundingClientRect();
      return {
        left: Math.round(bounds.left),
        right: Math.round(bounds.right),
        viewport: document.documentElement.clientWidth,
      };
    },
  );
  expect(paletteBounds.left).toBeGreaterThanOrEqual(0);
  expect(paletteBounds.right).toBeLessThanOrEqual(paletteBounds.viewport);

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

test("retention draft must be saved before apply and binds cleanup to that policy", async ({
  page,
}) => {
  let persistedDays = 1;
  let appliedBody = null;
  await page.unroute("**/api/privacy/settings");
  await page.unroute("**/api/privacy/retention/preview*");
  await page.route("**/api/privacy/settings", async (route) => {
    if (route.request().method() === "PUT") {
      persistedDays = route.request().postDataJSON().retention_days;
    }
    await route.fulfill({
      json: {
        retention_days: persistedDays,
        permanent: persistedDays === null,
      },
    });
  });
  await page.route("**/api/privacy/retention/preview*", async (route) => {
    const days = Number(new URL(route.request().url()).searchParams.get("days"));
    await route.fulfill({
      json: {
        retention_days: days,
        total_records: 12,
        records_to_delete: days === 30 ? 2 : 8,
        database_bytes: 65536,
        estimated_database_bytes_after: 60000,
      },
    });
  });
  await page.route("**/api/privacy/retention/apply", async (route) => {
    appliedBody = route.request().postDataJSON();
    await route.fulfill({
      json: {
        deleted: 2,
        history_deleted: 2,
        attempts_deleted: 0,
        retention_days: persistedDays,
      },
    });
  });

  await page.goto("/settings#privacy");
  await expect(page.locator("#saveRetentionBtn")).toBeDisabled();
  await expect(page.locator("#applyRetentionBtn")).toBeEnabled();

  await page.locator("#retentionSlider").fill("30");
  await expect(page.locator("#saveRetentionBtn")).toBeEnabled();
  await expect(page.locator("#applyRetentionBtn")).toBeDisabled();

  page.on("dialog", (dialog) => dialog.accept());
  await page.locator("#saveRetentionBtn").click();
  await expect(page.locator("#policySummary")).toContainText("30 days");
  await expect(page.locator("#applyRetentionBtn")).toBeEnabled();
  await page.locator("#applyRetentionBtn").click();
  await expect.poll(() => appliedBody).toEqual({
    confirm: true,
    expected_retention_days: 30,
  });
});

test("editing exposes disabled state, uses the saved password, and can re-enable", async ({
  page,
}) => {
  let server = {
    id: "server-1",
    display_name: "Synthetic Server",
    url: "https://navidrome.example.invalid",
    username: "synthetic-user",
    password_configured: true,
    enabled: false,
    runtime_status: "not_running",
    last_poll_ok: null,
    seconds_since_last_poll: null,
  };
  let testBody = null;
  let updateBody = null;
  await page.unroute("**/api/servers");
  await page.route("**/api/servers", (route) =>
    route.fulfill({ json: [server] }),
  );
  await page.route("**/api/servers/server-1/test", async (route) => {
    testBody = route.request().postDataJSON();
    await route.fulfill({ json: { ok: true, message: "ok" } });
  });
  await page.route("**/api/servers/server-1", async (route) => {
    updateBody = route.request().postDataJSON();
    server = { ...server, ...updateBody };
    await route.fulfill({ json: server });
  });

  await page.goto("/settings#source");
  await expect(page.locator(".server-status")).toHaveText("Disabled");
  await page.getByRole("button", { name: "Edit" }).click();
  await expect(page.locator("#cancelSourceEditBtn")).toBeVisible();
  await expect(page.locator("#sourcePass")).not.toHaveAttribute("required", "");
  await expect(page.locator("#sourceEnabled")).not.toBeChecked();

  await page.locator("#testSourceBtn").click();
  await expect.poll(() => testBody).not.toBeNull();
  expect(testBody.password).toBe("");
  expect(testBody.enabled).toBe(false);

  await page.locator("#sourceEnabled").check();
  await page.locator("#saveSourceBtn").click();
  await expect.poll(() => updateBody).not.toBeNull();
  expect(updateBody.enabled).toBe(true);
  await expect(page.locator(".server-status")).toHaveText("Enabled");
  await expect(page.locator("#cancelSourceEditBtn")).toBeHidden();
  await expect(page.locator("#sourceName")).toHaveValue("");
  await expect(page.locator("#sourcePass")).toHaveAttribute("required", "");
});
