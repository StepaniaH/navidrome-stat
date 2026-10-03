const { test, expect } = require("@playwright/test");

const origin = "http://127.0.0.1:39424";
const scope = "days=0&timezone=UTC&source_id=legacy&username=listener&start_date=2026-10-01&end_date=2026-10-10";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("navidrome-language", "zh-CN"));
  await page.route("**/api/coverart*", (route) => route.fulfill({ status: 404 }));
  await page.route("**/api/stats/album-cover*", (route) => route.fulfill({ status: 404 }));
});

test("daily average preference changes real summary data and survives reload", async ({ page, context }) => {
  await page.goto(`${origin}/?${scope}`);
  await expect(page.locator("#statTotalPlays")).toHaveText("55");
  await expect(page.locator("#statActiveDays")).toContainText("日均 5.5 次");
  await expect(page.locator("#statusText")).toHaveText("尚未配置采集");
  const settings = await context.newPage();
  await settings.goto(`${origin}/settings#preferences`);
  await settings.locator("#dailyAverageSelectButton").click();
  await settings.getByRole("option", { name: "活跃日均", exact: true }).click();
  await expect(page.locator("#statActiveDays")).toContainText("日均 55.0 次");
  await page.reload();
  await expect(page.locator("#statActiveDays")).toContainText("日均 55.0 次");
  await settings.locator("#dailyAverageSelectButton").click();
  await settings.getByRole("option", { name: "实际日均", exact: true }).click();
  await expect(page.locator("#statActiveDays")).toContainText("日均 5.5 次");
  await expect(page.locator("#historyTable tr")).toHaveCount(10);
  const query = new URL(await page.locator("#historyLink").getAttribute("href"), origin).searchParams;
  expect(query.get("username")).toBe("listener");
  expect(query.get("source_id")).toBe("legacy");
  expect(query.get("start_date")).toBe("2026-10-01");
  expect(query.has("daily_average_mode")).toBe(false);
});

test("individual records paginate, search and open scoped album details", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${origin}/history?${scope}`);
  await expect(page.locator("#listeningRecords > li")).toHaveCount(50);
  await expect(page.locator(".listening-record-duration").first()).toHaveText("—");
  await expect(page.locator("#listeningRecords")).toContainText("<img src=x onerror=window.__listens_injected=true>");
  expect(await page.evaluate(() => window.__listens_injected)).toBeUndefined();
  await page.locator("#listeningMore").click();
  await expect(page.locator("#listeningRecords > li")).toHaveCount(55);
  await expect(page.locator("#listeningMore")).toBeHidden();
  await expect(page.locator("#listeningRecords")).not.toContainText("other-listener");
  await page.locator("#listeningSearch").fill("Night window");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.locator("#listeningRecords > li")).toHaveCount(2);
  const album = page.locator("#listeningRecords a", { hasText: "Returning album" }).first();
  const query = new URL(await album.getAttribute("href"), origin).searchParams;
  expect(query.get("entity_source_id")).toBe("legacy");
  expect(query.get("entity_id")).toBe("returning-album");
  expect(query.get("username")).toBe("listener");
  await album.click();
  await expect(page.locator("#entityDetailName")).toHaveText("Returning album");
  await expect(page.locator("#entityDetailPlays")).toHaveText("2");
  expect(errors).toEqual([]);
});

test("history preserves the first page when loading older records fails", async ({ page }) => {
  await page.goto(`${origin}/history?${scope}`);
  await expect(page.locator("#listeningRecords > li")).toHaveCount(50);
  await page.route("**/api/stats/listens*", (route) => route.fulfill({ status: 503 }));
  await page.locator("#listeningMore").click();
  await expect(page.locator("#listeningRetry")).toBeVisible();
  await expect(page.locator("#listeningRecords > li")).toHaveCount(50);
  await page.unroute("**/api/stats/listens*");
  await page.locator("#listeningRetry").click();
  await expect(page.locator("#listeningRecords > li")).toHaveCount(55);
});

test("real review highlights use prior records and preserve their calendar scope", async ({ page }) => {
  await page.goto(`${origin}/review?year=2026&period=month&month=10&timezone=UTC&source_id=legacy&username=listener`);
  await expect(page.locator("#reviewTotalPlays")).toHaveText("55");
  await expect(page.locator("#reviewFirstRecordedTracks")).toHaveText("55");
  await expect(page.locator("#reviewNewTracks > li")).toHaveCount(10);
  await expect(page.locator("#reviewReturningAlbums")).toContainText("Returning album");
  await expect(page.locator("#reviewRisingArtist")).toContainText("1 → 55 次");
  const link = page.locator("#reviewReturningAlbums a").first();
  const query = new URL(await link.getAttribute("href"), origin).searchParams;
  expect(query.get("start_date")).toBe("2026-10-01");
  expect(query.get("end_date")).toBe("2026-10-31");
  expect(query.get("username")).toBe("listener");
  await page.setViewportSize({ width: 375, height: 812 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test("collection failure and mixed collection stay visible with usable history", async ({ page }) => {
  await page.route("**/api/stats/collection-status*", (route) => route.fulfill({
    json: { status: "degraded", mixed_collection: true },
  }));
  await page.goto(`${origin}/?${scope}`);
  await expect(page.locator("#statTotalPlays")).toHaveText("55");
  await expect(page.locator("#statusText")).toHaveText("采集异常 · 双重采集已启用");
  await expect(page.locator("#statusBadge")).toHaveAttribute("title", /不同采集方式之间不会自动去重/);
  await expect(page.locator("#historyTable tr")).toHaveCount(10);
});
