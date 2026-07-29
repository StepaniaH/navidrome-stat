const { test, expect } = require("@playwright/test");

const snapshot = {
  summary: {
    total_plays: 3,
    total_listen_sec: 185,
    unique_tracks: 2,
    client_count: 1,
    active_days: 1,
    average_daily_plays: 3,
    average_daily_listen_sec: 185,
    previous_total_plays: 2,
    previous_total_listen_sec: 120,
    plays_change_pct: 50,
    listen_change_pct: 54.17,
    window_days: 30,
  },
  players: [{
    client_name: "Synthetic Player",
    count: 3,
    total_listen_sec: 185,
    average_listen_sec: 61.67,
    transcoded_count: 1,
    transcoding_rate_pct: 33.33,
  }],
  transcoding: [{
    is_transcoding: 0,
    count: 2,
    total_listen_sec: 125,
    plays_pct: 66.67,
    listen_sec_pct: 67.57,
  }],
  hourly: [{ hour: 12, count: 3 }],
  daily: [{ date: "2026-07-28", count: 3 }],
  heatmap: Array.from({ length: 168 }, (_, index) => ({
    weekday: Math.floor(index / 24),
    hour: index % 24,
    count: index === 60 ? 3 : 0,
  })),
  history: [{
    username: "synthetic-user",
    title: "<img src=x onerror=window.__injected=true>",
    artist: "Synthetic Artist",
    album: "Synthetic Album",
    play_count: 2,
    last_played_at: "2026-07-28T12:00:00+00:00",
    total_listen_sec: 120,
    source_id: "server-1",
    source_name: "Synthetic Server",
  }],
  servers: [{
    source_id: "server-1",
    source_name: "Synthetic Server",
    count: 3,
    total_listen_sec: 185,
  }],
  available_servers: [{
    id: "server-1",
    display_name: "Synthetic Server",
  }],
  top_artists: [{
    artist: "Synthetic Artist",
    count: 3,
    total_listen_sec: 185,
    value: 3,
  }],
  top_albums: [{
    album: "Synthetic Album",
    count: 3,
    total_listen_sec: 185,
    value: 3,
  }],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/status", (route) =>
    route.fulfill({ json: { auth_required: false } }),
  );
  await page.route("**/api/stats/dashboard?*", (route) =>
    route.fulfill({ json: snapshot }),
  );
  await page.route("**/api/stats/now-playing*", (route) =>
    route.fulfill({
      json: [{
        username: "synthetic-user",
        title: "Synthetic Live Track",
        artist: "Synthetic Artist",
        client_name: "Synthetic Player",
        seconds_elapsed: 42,
        source_name: "Synthetic Server",
      }],
    }),
  );
});

test("renders synthetic statistics without executing metadata", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#statTotalPlays")).toHaveText("3");
  await expect(page.locator("#historyTable")).toContainText(
    "<img src=x onerror=window.__injected=true>",
  );
  await expect(page.locator("#nowPlayingList")).toContainText(
    "Synthetic Live Track",
  );
  expect(await page.evaluate(() => window.__injected)).toBeUndefined();
  await page.locator("#statsSourceButton").click();
  await expect(page.locator(".stats-source-option")).toHaveCount(2);
});

test("desktop header stays on one compact row", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const layout = await page.evaluate(() => {
    const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
    const header = rect(".dashboard-header");
    const nextSection = rect("section");
    const items = [
      ".dashboard-brand",
      ".dashboard-filters",
      ".dashboard-meta",
      ".dashboard-actions",
    ].map((selector) => rect(selector));
    return {
      headerHeight: Math.round(header.height),
      headerBottom: Math.round(header.bottom),
      nextSectionTop: Math.round(nextSection.top),
      centers: items.map((item) => Math.round(item.top + item.height / 2)),
      hasLegacyToolbar: Boolean(document.querySelector(".dashboard-toolbar")),
    };
  });
  expect(layout.headerHeight).toBeLessThan(70);
  expect(Math.max(...layout.centers) - Math.min(...layout.centers)).toBeLessThanOrEqual(1);
  expect(layout.hasLegacyToolbar).toBe(false);
  expect(layout.nextSectionTop).toBeGreaterThanOrEqual(layout.headerBottom);
});

test("history fits the page and footer exposes project links", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const layout = await page.evaluate(() => {
    const wrap = document.querySelector(".history-table-wrap");
    const headers = [...document.querySelectorAll(".history-table th")];
    const footerLinks = [...document.querySelectorAll(".app-footer a")];
    return {
      historyOverflow: wrap.scrollWidth - wrap.clientWidth,
      overflowX: getComputedStyle(wrap).overflowX,
      visibleHeaders: headers.filter((header) => getComputedStyle(header).display !== "none").length,
      footer: footerLinks.map((link) => ({
        text: link.textContent,
        href: link.href,
        rel: link.rel,
      })),
    };
  });
  expect(layout.historyOverflow).toBeLessThanOrEqual(0);
  expect(layout.overflowX).toBe("hidden");
  expect(layout.visibleHeaders).toBe(6);
  expect(layout.footer).toEqual([
    {
      text: "GitHub",
      href: "https://github.com/StepaniaH/navidrome-stat",
      rel: "noopener noreferrer",
    },
    {
      text: "MIT",
      href: "https://github.com/StepaniaH/navidrome-stat/blob/main/LICENSE",
      rel: "noopener noreferrer",
    },
  ]);
});

test("server filter is encoded into historical and realtime requests", async ({
  page,
}) => {
  const requests = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/stats/")) requests.push(request.url());
  });
  await page.goto("/");
  await page.locator("#statsSourceButton").click();
  await page.locator('[data-source-id="server-1"]').click();
  await expect.poll(() =>
    requests.some((url) => url.includes("source_id=server-1")),
  ).toBe(true);
});

test("custom date range is encoded into the dashboard request", async ({
  page,
}) => {
  const requests = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/stats/dashboard")) requests.push(request.url());
  });
  await page.goto("/");
  await page.locator("#statsWindowButton").click();
  await page.locator("#customStartDate").fill("2026-07-01");
  await page.locator("#customEndDate").fill("2026-07-28");
  await page.locator("#customRangeApply").click();
  await expect(page.locator("#statsWindowButtonLabel")).toHaveText(
    "2026-07-01 — 2026-07-28",
  );
  await expect.poll(() =>
    requests.some((url) =>
      url.includes("start_date=2026-07-01")
      && url.includes("end_date=2026-07-28")
    ),
  ).toBe(true);
});

test("mobile viewport keeps primary content inside the page", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const layout = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    historyOverflow:
      document.querySelector(".history-table-wrap").scrollWidth
      - document.querySelector(".history-table-wrap").clientWidth,
    visibleHistoryCells: [...document.querySelector("#historyTable tr").children]
      .filter((cell) => getComputedStyle(cell).display !== "none").length,
    offenders: [...document.querySelectorAll("body *")]
      .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
      .slice(0, 5)
      .map((element) => ({
        tag: element.tagName,
        id: element.id,
        className: element.className,
        right: Math.round(element.getBoundingClientRect().right),
      })),
  }));
  expect(layout.overflow, JSON.stringify(layout.offenders)).toBeLessThanOrEqual(1);
  expect(layout.historyOverflow).toBeLessThanOrEqual(1);
  expect(layout.visibleHistoryCells).toBe(6);
});
