const { test, expect } = require("@playwright/test");

const delay = (milliseconds) => new Promise((resolve) => {
  setTimeout(resolve, milliseconds);
});

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
    track_id: "tr-1",
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
    album_id: "al-1",
  }],
};

const playAccountingSnapshot = {
  short_count: 2,
  counted_count: 6,
  attempt_count: 8,
  short_listen_sec: 21,
  short_play_rate_pct: 25,
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
  await page.route("**/api/stats/short-plays?*", (route) =>
    route.fulfill({ json: playAccountingSnapshot }),
  );
  await page.route("**/api/diagnostics", (route) =>
    route.fulfill({
      json: {
        schema_version: 1,
        category: "ready",
        configured_connection_count: 1,
        enabled_connection_count: 1,
        history_record_count: 3,
        healthy_collector_count: 1,
        degraded_collector_count: 0,
        last_success_at: "2026-07-28T12:00:00+00:00",
        retry_in_seconds: null,
      },
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
  await expect(page.locator("#nowPlayingList .source-badge")).toHaveText(
    "Synthetic Server",
  );
  await expect(page.locator("#historyTable .history-user-source")).toHaveText(
    "Synthetic Server",
  );
  await expect(page.locator("#topArtistsChart")).toHaveAttribute("role", "list");
  await expect(page.locator("#topArtistsChart [role=listitem]")).toHaveCount(1);
  await expect(page.locator("#topArtistsChart .ranking-cover-fallback").first()).toHaveText("S");
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
  await expect(page.locator("#reviewLink")).toHaveAttribute("href", /source_id=server-1/);
  await expect(page.locator("#reviewLink")).toHaveAttribute("title", "Year in Review");
});

test("shared timezone and mobile history columns are restored", async ({ page }) => {
  const dashboardRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/stats/dashboard")) dashboardRequests.push(request.url());
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    localStorage.setItem("navidrome-timezone", "UTC");
    localStorage.setItem("navidrome-history-columns", "track");
  });
  await page.goto("/?timezone=Europe%2FBerlin");
  await expect(page.locator("#historyTable .history-cell-title")).toBeVisible();
  await expect(page.locator("#historyTable .history-cell-artist")).toBeHidden();
  await expect.poll(() => dashboardRequests.some((url) => (
    new URL(url).searchParams.get("timezone") === "Europe/Berlin"
  ))).toBe(true);
});

test("history column menu stays usable when history is empty", async ({ page }) => {
  await page.unroute("**/api/stats/dashboard?*");
  await page.route("**/api/stats/dashboard?*", (route) => route.fulfill({
    json: { ...snapshot, history: [] },
  }));
  await page.setViewportSize({ width: 1440, height: 648 });
  await page.goto("/");
  await page.locator("#historyColumnsButton").click();

  const options = page.locator("#historyColumnsPanel .column-option");
  await expect(options).toHaveCount(6);
  const lastOptionIsExposed = await options.last().evaluate((option) => {
    const rect = option.getBoundingClientRect();
    const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return top === option || option.contains(top);
  });
  expect.soft(lastOptionIsExposed).toBe(true);

  await options.nth(2).click();
  await expect(page.locator("#historyColumnsPanel")).toBeVisible();
});

test("playback accounting details load only when opened", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/stats/short-plays")) requests.push(request.url());
  });

  await page.goto("/");
  expect(requests).toHaveLength(0);

  await page.locator("#playAccountingButton").click();
  const panel = page.locator("#playAccountingPanel");
  await expect(panel).toBeVisible();
  await expect(panel.locator("#playAccountingTitle")).toHaveText(
    "Playback attempts below the counting threshold",
  );
  await expect(panel.locator("#playAccountingValue")).toHaveText(
    "2 attempts · 25% of observed playback attempts",
  );
  await expect(panel).toContainText("were not recorded as plays");
  await expect.poll(() => requests.length).toBe(1);
  const query = new URL(requests[0]).searchParams;
  expect(query.get("days")).toBe("30");
  expect(query.has("timezone")).toBe(true);
  expect(query.has("metric")).toBe(false);

  await page.locator("#playAccountingClose").click();
  await expect(panel).toBeHidden();
  await expect(page.locator("#playAccountingButton")).toBeFocused();
  await page.locator("#playAccountingButton").click();
  await expect(panel).toBeVisible();
  expect(requests).toHaveLength(1);
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
  await expect(page.locator("#historyTable tr")).toHaveCount(1);
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

function emptySnapshot() {
  return {
    summary: {
      total_plays: 0,
      total_listen_sec: 0,
      unique_tracks: 0,
      client_count: 0,
      active_days: 0,
      average_daily_plays: 0,
      average_daily_listen_sec: 0,
      previous_total_plays: 0,
      previous_total_listen_sec: 0,
      plays_change_pct: null,
      listen_change_pct: null,
      window_days: 30,
    },
    players: [],
    transcoding: [],
    hourly: [],
    daily: [],
    heatmap: Array.from({ length: 168 }, (_, index) => ({
      weekday: Math.floor(index / 24),
      hour: index % 24,
      count: 0,
    })),
    history: [],
    servers: [],
    available_servers: [],
    top_artists: [],
    top_albums: [],
  };
}

test("first-use dashboard collapses historical analysis", async ({ page }) => {
  await page.unroute("**/api/diagnostics");
  await page.route("**/api/diagnostics", (route) =>
    route.fulfill({ json: { history_record_count: 0 } }),
  );
  await page.route("**/api/stats/dashboard?*", (route) =>
    route.fulfill({ json: emptySnapshot() }),
  );
  await page.route("**/api/stats/now-playing*", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto("/");
  await expect(page.locator("#playerChartEmpty")).toBeHidden();
  await expect(page.locator("#summarySection")).toBeHidden();
  await expect(page.locator("[data-history-analysis]:visible")).toHaveCount(0);
  await expect(page.locator("#nowPlayingEmpty")).toBeVisible();
  await expect(page.locator("#playerChartError")).toBeHidden();
  await expect(page.locator("#errorBanner")).toBeHidden();
  await expect(page.locator("#newUserGuide")).toBeVisible();
  await expect(page.locator("#playAccountingButton")).toBeVisible();
  await page.locator("#playAccountingButton").click();
  await expect(page.locator("#playAccountingValue")).toContainText("25%");
});

test("empty filtered results do not look like first use", async ({ page }) => {
  await page.route("**/api/stats/dashboard?*", (route) =>
    route.fulfill({ json: emptySnapshot() }),
  );
  await page.route("**/api/stats/now-playing*", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto("/?username=listener");
  await expect(page.locator("#historyEmpty")).toContainText(
    "No plays match these filters",
  );
  await expect(page.locator("#newUserGuide")).toBeHidden();
  await expect(page.locator("#historyEmpty")).toBeVisible();
  await expect(page.locator("#summarySection")).toBeVisible();
});

test("401 shows login instead of empty statistics", async ({ page }) => {
  await page.route("**/api/auth/status", (route) =>
    route.fulfill({ json: { auth_required: true } }),
  );
  await page.route("**/api/stats/dashboard?*", (route) =>
    route.fulfill({ status: 401, json: { detail: "Unauthorized" } }),
  );
  await page.route("**/api/stats/now-playing*", (route) =>
    route.fulfill({ status: 401, json: { detail: "Unauthorized" } }),
  );
  await page.goto("/");
  await expect(page.locator("#loginOverlay")).toBeVisible();
  await expect(page.locator("#loginToken")).toBeFocused();
  await expect(page.locator("#dashboardApp")).toHaveJSProperty("inert", true);
  await expect(page.locator("#statTotalPlays")).toHaveText("—");
  await expect(page.locator("#playerChartEmpty")).toBeHidden();
});

test("now-playing failure keeps historical stats", async ({ page }) => {
  await page.route("**/api/stats/now-playing*", (route) =>
    route.fulfill({ status: 500, body: "fail" }),
  );
  await page.goto("/");
  await expect(page.locator("#statTotalPlays")).toHaveText("3");
  await expect(page.locator("#nowPlayingError")).toBeVisible();
  await expect(page.locator("#nowPlayingEmpty")).toBeHidden();
  await expect(page.locator("#errorBanner")).toBeHidden();
  await expect(page.locator("#historyTable")).toContainText("synthetic-user");
});

test("dashboard failure shows section errors without blanking now playing", async ({ page }) => {
  await page.route("**/api/stats/dashboard?*", (route) =>
    route.fulfill({ status: 500, body: "fail" }),
  );
  await page.goto("/");
  await expect(page.locator("#playerChartError")).toBeVisible();
  await expect(page.locator("#historyError")).toBeVisible();
  await expect(page.locator("#errorBanner")).toBeVisible();
  await expect(page.locator("#nowPlayingList")).toContainText("Synthetic Live Track");
  await expect(page.locator("#statTotalPlays")).toHaveText("—");
});

test("malformed players field fails only the clients panel", async ({ page }) => {
  await page.route("**/api/stats/dashboard?*", (route) =>
    route.fulfill({ json: { ...snapshot, players: null } }),
  );
  await page.goto("/");
  await expect(page.locator("#playerChartError")).toBeVisible();
  await expect(page.locator("#playerChartEmpty")).toBeHidden();
  await expect(page.locator("#historyTable")).toContainText("synthetic-user");
  await expect(page.locator("#statTotalPlays")).toHaveText("3");
  await expect(page.locator("#playerChartSummary")).toHaveText(
    "This section could not be loaded.",
  );
});

test("newer filter state aborts stale dashboard responses", async ({ page }) => {
  const requests = [];
  await page.route("**/api/stats/dashboard?*", async (route) => {
    const url = new URL(route.request().url());
    const days = url.searchParams.get("days");
    const metric = url.searchParams.get("metric");
    requests.push(`${days}:${metric}`);
    if (days === "7" && metric === "plays") {
      await delay(350);
      await route.fulfill({
        json: {
          ...snapshot,
          top_artists: [{
            artist: "Stale Artist",
            count: 99,
            total_listen_sec: 99,
            value: 99,
          }],
        },
      }).catch(() => {});
      return;
    }
    if (days === "7" && metric === "listen_time") {
      await route.fulfill({
        json: {
          ...snapshot,
          top_artists: [{
            artist: "Latest Artist",
            count: 3,
            total_listen_sec: 185,
            value: 185,
          }],
        },
      });
      return;
    }
    await route.fulfill({ json: snapshot });
  });

  await page.goto("/");
  await page.locator("#statsWindowButton").click();
  await page.locator('[data-days="7"]').click();
  await expect.poll(() => requests.includes("7:plays")).toBe(true);
  await page.locator('[data-ranking-metric="listen_time"]').click();
  await expect(page.locator("#topArtistsChart")).toContainText("Latest Artist");
  await delay(450);
  await expect(page.locator("#topArtistsChart")).not.toContainText("Stale Artist");
  await expect(page.locator("#topArtistsSubtitle")).toHaveText(
    "Ranked by listening time",
  );
});

test("newer source state aborts stale now-playing responses", async ({ page }) => {
  const multiSourceSnapshot = {
    ...snapshot,
    available_servers: [
      ...snapshot.available_servers,
      { id: "server-2", display_name: "Second Server" },
    ],
    servers: [
      ...snapshot.servers,
      {
        source_id: "server-2",
        source_name: "Second Server",
        count: 1,
        total_listen_sec: 60,
      },
    ],
  };
  await page.route("**/api/stats/dashboard?*", (route) =>
    route.fulfill({ json: multiSourceSnapshot }),
  );
  await page.route("**/api/stats/now-playing*", async (route) => {
    const url = new URL(route.request().url());
    const source = url.searchParams.get("source_id");
    if (source === "server-1") await delay(350);
    const title = source === "server-1" ? "Stale Live Track" : "Latest Live Track";
    await route.fulfill({
      json: [{
        username: "synthetic-user",
        title,
        artist: "Synthetic Artist",
        client_name: "Synthetic Player",
        seconds_elapsed: 42,
        source_name: source === "server-2" ? "Second Server" : "Synthetic Server",
      }],
    }).catch(() => {});
  });

  await page.goto("/");
  await page.locator("#statsSourceButton").click();
  await page.locator('[data-source-id="server-1"]').click();
  await page.locator("#statsSourceButton").click();
  await page.locator('[data-source-id="server-2"]').click();
  await expect(page.locator("#nowPlayingList")).toContainText("Latest Live Track");
  await delay(450);
  await expect(page.locator("#nowPlayingList")).not.toContainText("Stale Live Track");
  await expect(page.locator("#nowPlayingList .source-badge")).toHaveCount(0);
});

test("source menu merges current and historical sources then removes stale ones", async ({ page }) => {
  let requestCount = 0;
  await page.route("**/api/stats/dashboard?*", (route) => {
    requestCount += 1;
    const historicalServer = {
      source_id: "historical-server",
      source_name: "Historical Server",
      count: 1,
      total_listen_sec: 30,
    };
    const response = requestCount === 1
      ? {
          ...snapshot,
          servers: [historicalServer],
          available_servers: snapshot.available_servers,
        }
      : snapshot;
    return route.fulfill({ json: response });
  });

  await page.goto("/");
  await page.locator("#statsSourceButton").click();
  await expect(page.locator(".stats-source-option")).toHaveCount(3);
  await expect(page.locator("#statsSourceMenu")).toContainText("Historical Server");
  await page.keyboard.press("Escape");
  await page.locator("#refreshBtn").click();
  await expect.poll(() => requestCount).toBeGreaterThanOrEqual(2);
  await page.locator("#statsSourceButton").click();
  await expect(page.locator(".stats-source-option")).toHaveCount(2);
  await expect(page.locator("#statsSourceMenu")).not.toContainText("Historical Server");
});

test("successful first login starts realtime refresh and traps dialog focus", async ({ page }) => {
  await page.clock.install();
  let authenticated = false;
  let realtimeRequests = 0;
  await page.route("**/api/auth/status", (route) =>
    route.fulfill({ json: { auth_required: true } }),
  );
  await page.route("**/api/auth/login", (route) => {
    authenticated = true;
    return route.fulfill({ json: { authenticated: true } });
  });
  await page.route("**/api/stats/dashboard?*", (route) => (
    authenticated
      ? route.fulfill({ json: snapshot })
      : route.fulfill({ status: 401, json: { detail: "Unauthorized" } })
  ));
  await page.route("**/api/stats/now-playing*", (route) => {
    realtimeRequests += 1;
    return route.fulfill({ json: [] });
  });

  await page.goto("/");
  await expect(page.locator("#loginToken")).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(page.locator("#loginForm button[type=submit]")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.locator("#loginToken")).toBeFocused();
  await page.locator("#loginToken").fill("valid-token");
  await page.locator("#loginForm button[type=submit]").click();
  await expect(page.locator("#loginOverlay")).toBeHidden();
  const afterLogin = realtimeRequests;
  await page.clock.fastForward(10_100);
  await expect.poll(() => realtimeRequests).toBeGreaterThan(afterLogin);
});

test("an expired session stops refresh timers and the local playback ticker", async ({ page }) => {
  await page.clock.install();
  let realtimeRequests = 0;
  await page.route("**/api/stats/now-playing*", (route) => {
    realtimeRequests += 1;
    return route.fulfill({
      json: [{
        username: "synthetic-user",
        title: "Synthetic Live Track",
        artist: "Synthetic Artist",
        client_name: "Synthetic Player",
        seconds_elapsed: 42,
        source_name: "Synthetic Server",
      }],
    });
  });
  await page.goto("/");
  await expect(page.locator(".now-playing-elapsed")).toHaveText("0:42");
  await page.route("**/api/stats/dashboard?*", (route) =>
    route.fulfill({ status: 401, json: { detail: "Unauthorized" } }),
  );
  await page.locator("#refreshBtn").click();
  await expect(page.locator("#loginOverlay")).toBeVisible();
  const requestsAtExpiry = realtimeRequests;
  const elapsedAtExpiry = await page.locator(".now-playing-elapsed").textContent();
  await page.clock.fastForward(20_000);
  expect(realtimeRequests).toBe(requestsAtExpiry);
  await expect(page.locator(".now-playing-elapsed")).toHaveText(elapsedAtExpiry);
});

test("filter listboxes support arrow navigation and restore trigger focus", async ({ page }) => {
  await page.goto("/");
  await page.locator("#statsSourceButton").focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.locator('.stats-source-option[aria-selected="true"]')).toBeFocused();
  await page.keyboard.press("End");
  await expect(page.locator('[data-source-id="server-1"]')).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator("#statsSourceButton")).toBeFocused();

  await page.locator("#statsWindowButton").focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("End");
  await expect(page.locator("#customRangeOption")).toBeFocused();
  await page.keyboard.press("Home");
  await expect(page.locator('[data-days="7"]')).toBeFocused();
});

test("Chinese locale covers regions, chart labels, listboxes, and footer", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("navidrome-language", "zh-CN");
  });
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.getByRole("region", { name: "周时热力图" })).toBeVisible();
  await expect(page.getByRole("group", { name: "榜单指标" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "项目链接" })).toBeVisible();
  await page.locator("#statsWindowButton").click();
  await expect(page.getByRole("listbox", { name: "统计时间范围" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator('[data-i18n="subtitle.transcoding"]')).toHaveText(
    "直出与转码",
  );
  const chartLabels = await page.evaluate(() => ({
    weekdays: echarts.getInstanceByDom(
      document.getElementById("weekdayHourChart"),
    ).getOption().yAxis[0].data,
    transcoding: echarts.getInstanceByDom(
      document.getElementById("transcodingChart"),
    ).getOption().series[0].data.map((item) => item.name),
  }));
  expect(chartLabels.weekdays).toEqual([
    "周一", "周二", "周三", "周四", "周五", "周六", "周日",
  ]);
  expect(chartLabels.transcoding).toEqual(["直出"]);
});

test("changing the theme preference recolors charts without a reload", async ({ page }) => {
  await page.goto("/");
  await page.waitForFunction(() => {
    const chart = echarts.getInstanceByDom(document.getElementById("hourlyChart"));
    return Boolean(chart && chart.getOption().series[0]?.data?.length);
  });
  const before = await page.evaluate(() =>
    echarts.getInstanceByDom(document.getElementById("hourlyChart")).getOption().textStyle.color,
  );
  await page.evaluate(() => {
    localStorage.setItem("navidrome-theme-mode", "light");
    localStorage.setItem("navidrome-theme-palette", "catppuccin");
    window.dispatchEvent(new StorageEvent("storage", {
      key: "navidrome-theme-mode",
      newValue: "light",
    }));
  });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "latte");
  await expect
    .poll(() =>
      page.evaluate(() =>
        echarts.getInstanceByDom(document.getElementById("hourlyChart")).getOption().textStyle.color,
      ),
    )
    .not.toBe(before);
  const themedColors = await page.evaluate(() => {
    const styles = getComputedStyle(document.documentElement);
    const option = echarts.getInstanceByDom(document.getElementById("hourlyChart")).getOption();
    return {
      chart: option.series[0].itemStyle.color.colorStops[1].color,
      expectedChart: styles.getPropertyValue("--chart-1").trim(),
      text: option.textStyle.color,
      expectedText: styles.getPropertyValue("--text-muted").trim(),
    };
  });
  expect(themedColors.chart).toBe(themedColors.expectedChart);
  expect(themedColors.text).toBe(themedColors.expectedText);
});

for (const theme of [
  {
    name: "built-in light",
    mode: "light",
    palette: "builtin",
    separator: "rgba(255, 255, 255, 0.52)",
    tooltipBorder: "rgba(122, 137, 154, 0.46)",
    tooltipShadow: "rgba(24, 34, 48, 0.32) 0px 12px 30px -12px",
  },
  {
    name: "Nord",
    mode: "dark",
    palette: "nord",
    separator: "rgba(46, 52, 64, 0.52)",
    tooltipBorder: "rgba(129, 145, 170, 0.46)",
    tooltipShadow: "rgba(14, 18, 25, 0.32) 0px 12px 30px -12px",
  },
]) {
  test(`${theme.name} pie charts use soft seams and theme-aware tooltip elevation`, async ({ page }) => {
    await page.addInitScript(({ mode, palette }) => {
      localStorage.setItem("navidrome-theme-mode", mode);
      localStorage.setItem("navidrome-theme-palette", palette);
    }, theme);
    await page.goto("/");
    await page.waitForFunction(() => {
      const chart = echarts.getInstanceByDom(document.getElementById("playerChart"));
      return Boolean(chart?.getOption()?.series?.[0]?.data?.length);
    });

    const pieStyle = await page.evaluate(() => {
      const chart = echarts.getInstanceByDom(document.getElementById("playerChart"));
      const series = chart.getOption().series[0];
      chart.dispatchAction({ type: "showTip", seriesIndex: 0, dataIndex: 0 });
      return series.itemStyle;
    });
    expect(pieStyle.borderWidth).toBe(2);
    expect(pieStyle.borderColor).toBe(theme.separator);

    const tooltip = page.locator('#playerChart div[style*="box-shadow"]').last();
    await expect(tooltip).toBeVisible();
    const tooltipStyle = await tooltip.evaluate((element) => {
      const styles = getComputedStyle(element);
      return {
        borderColor: styles.borderColor,
        borderWidth: styles.borderWidth,
        boxShadow: styles.boxShadow,
      };
    });
    expect(tooltipStyle.borderWidth).toBe("1px");
    expect(tooltipStyle.borderColor).toBe(theme.tooltipBorder);
    expect(tooltipStyle.boxShadow).toBe(theme.tooltipShadow);
  });
}

test("dashboard filters persist across a reload and are shareable", async ({ page }) => {
  await page.goto("/");
  await page.waitForFunction(() => {
    const chart = echarts.getInstanceByDom(document.getElementById("hourlyChart"));
    return Boolean(chart?.getOption()?.series?.[0]?.data?.length);
  });
  await page.locator("#statsWindowButton").click();
  await page.locator('.stats-window-option[data-days="7"]').click();
  await expect(page).toHaveURL(/days=7/);

  await page.reload();
  await page.waitForFunction(() => {
    const chart = echarts.getInstanceByDom(document.getElementById("hourlyChart"));
    return Boolean(chart?.getOption()?.series?.[0]?.data?.length);
  });
  await expect(page.locator("#statsWindowButton")).toContainText("Last 7 days");
});

test("the user filter narrows stats and now playing, and persists", async ({ page }) => {
  await page.route("**/api/stats/users", (route) =>
    route.fulfill({ json: { users: ["listener", "synthetic-user"] } }),
  );
  await page.goto("/");
  await page.waitForFunction(() => {
    const chart = echarts.getInstanceByDom(document.getElementById("hourlyChart"));
    return Boolean(chart && chart.getOption().series[0]?.data?.length);
  });
  await expect(page.locator("#nowPlayingList .now-playing-item")).toHaveCount(1);

  const snapshotRequest = page.waitForRequest((request) =>
    request.url().includes("/api/stats/dashboard"),
  );
  await page.locator("#statsUserButton").click();
  await page.locator('.stats-user-option[data-username="listener"]').click();
  expect((await snapshotRequest).url()).toContain("username=listener");
  await expect(page).toHaveURL(/username=listener/);
  await expect(page.locator("#nowPlayingEmpty")).toBeVisible();
  await expect(page.locator("#statsUserButton")).toContainText("listener");
  await expect(page.locator("#reviewLink")).toHaveAttribute("href", /username=listener/);

  await page.reload();
  await page.waitForFunction(() => {
    const chart = echarts.getInstanceByDom(document.getElementById("hourlyChart"));
    return Boolean(chart && chart.getOption().series[0]?.data?.length);
  });
  await expect(page.locator("#statsUserButton")).toContainText("listener");
});

test("history and album rankings request cover art through the proxy", async ({ page }) => {
  await page.route("**/api/coverart*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "image/png",
      body: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
        "base64",
      ),
    }),
  );
  await page.goto("/");
  await expect(page.locator('#historyTable img.history-cover[src*="/api/coverart"]')).toHaveCount(1);
  await expect(page.locator('img.ranking-cover[src*="id=al-1"]')).toHaveCount(1);
});
