const { test, expect } = require("@playwright/test");

test("API reference loads, expands, and filters the runtime schema", async ({ page }) => {
  await page.goto("/docs");

  await expect(page).toHaveTitle("Navidrome Statistic API");
  const endpoints = page.locator(".api-endpoint");
  await expect(page.locator("#apiStatus")).toHaveText(/^\d+ endpoints?$/);
  expect(await endpoints.count()).toBeGreaterThan(10);
  const groups = await page.locator(".api-group h2").allTextContents();
  expect(groups).toEqual(expect.arrayContaining([
    "Authentication",
    "Connections",
    "Health",
    "Privacy",
    "Statistics",
  ]));

  await endpoints.first().locator("summary").click();
  await expect(endpoints.first()).toHaveAttribute("open", "");

  await page.locator("#endpointFilter").fill("retention");
  await expect(page.locator("#apiStatus")).toContainText("endpoint");
  const visibleAfterFilter = await page.locator(".api-endpoint:visible").count();
  expect(visibleAfterFilter).toBeGreaterThan(0);
  expect(visibleAfterFilter).toBeLessThan(await endpoints.count());

  await page.locator("#endpointFilter").fill("no-such-endpoint-value");
  await expect(page.locator("#apiStatus")).toHaveText("0 endpoints");
  await expect(page.locator(".api-group:visible")).toHaveCount(0);
});

test("API reference has no horizontal overflow on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/docs");
  await expect(page.locator("#apiStatus")).toHaveText(/^\d+ endpoints?$/);

  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
});
