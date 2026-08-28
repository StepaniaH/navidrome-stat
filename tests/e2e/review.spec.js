import { expect, test } from "@playwright/test";

const REVIEW = {
  year: 2026,
  total_plays: 486,
  total_listen_sec: 87200,
  unique_tracks: 212,
  active_days: 190,
  longest_streak_days: 14,
  first_played_at: "2026-01-02T08:00:00+01:00",
  last_played_at: "2026-08-20T22:10:00+01:00",
  biggest_month: "2026-03",
  monthly: Array.from({ length: 12 }, (_, month) => ({
    month: `2026-${String(month + 1).padStart(2, "0")}`,
    count: month === 2 ? 120 : 30,
    total_listen_sec: month === 2 ? 40000 : 9000,
  })),
  hourly: Array.from({ length: 24 }, (_, hour) => ({ hour, count: hour === 9 ? 60 : 10, total_listen_sec: hour === 9 ? 18000 : 3000 })),
  weekday: Array.from({ length: 7 }, (_, weekday) => ({ weekday, count: weekday === 2 ? 90 : 40, total_listen_sec: weekday === 2 ? 26000 : 12000 })),
  top_artists: [{ name: "Synthetic Artist", count: 90, total_listen_sec: 18000, value: 18000 }],
  top_albums: [{ name: "Synthetic Album", count: 60, total_listen_sec: 12000, value: 12000, album_id: "al-1", source_id: "src-1" }],
  top_tracks: [{ name: "Synthetic Song", count: 40, total_listen_sec: 8000, value: 8000, track_id: "tr-1", source_id: "src-1" }],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/status", (route) =>
    route.fulfill({ json: { auth_required: false } }),
  );
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
  await page.route("**/api/stats/review*", (route) => {
    const year = Number(new URL(route.request().url()).searchParams.get("year")) || REVIEW.year;
    route.fulfill({ json: { ...REVIEW, year } });
  });
});

test("review page renders the yearly story", async ({ page }) => {
  await page.goto("/review");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("#reviewTotalPlays")).toHaveText("486");
  await expect(page.locator("#reviewStreak")).toContainText("14");
  await expect
    .poll(() =>
      page.evaluate(() =>
        echarts.getInstanceByDom(document.getElementById("reviewMonthlyChart")).getOption().series[0].data.length,
      ),
    )
    .toBe(12);
  await expect(page.locator("#reviewTopAlbums img[src*='id=al-1']")).toHaveCount(1);
  await expect(page.locator("#reviewTopTracks img[src*='id=tr-1']")).toHaveCount(1);
  await expect(page.locator("#reviewEmpty")).toBeHidden();
});

test("review page switches years through the selector", async ({ page }) => {
  await page.goto("/review");
  await expect
    .poll(() =>
      page.evaluate(() => {
        const chart = echarts.getInstanceByDom(document.getElementById("reviewMonthlyChart"));
        return Boolean(chart && chart.getOption().series[0].data.length);
      }),
    )
    .toBe(true);
  await page.locator("#reviewYearButton").click();
  await page.getByRole("option", { name: "2025" }).click();
  await expect(page.locator("#reviewSubtitle")).toContainText("2025");
});

test("review distribution charts switch between plays and listening time", async ({ page }) => {
  await page.goto("/review");
  await expect
    .poll(() =>
      page.evaluate(() => {
        const chart = echarts.getInstanceByDom(document.getElementById("reviewMonthlyChart"));
        return Boolean(chart && chart.getOption().series[0].data.length);
      }),
    )
    .toBe(true);
  const listenButton = page.locator('#reviewMetricControl [data-review-metric="listen_time"]');
  await listenButton.click();
  await expect(listenButton).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(() =>
      page.evaluate(() => {
        const chart = echarts.getInstanceByDom(document.getElementById("reviewMonthlyChart"));
        return chart.getOption().series[0].data[2];
      }),
    )
    .toBe(40000);
});

test("review charts redraw from the resolved theme tokens", async ({ page }) => {
  await page.goto("/review");
  await expect
    .poll(() =>
      page.evaluate(() => {
        const chart = echarts.getInstanceByDom(document.getElementById("reviewMonthlyChart"));
        return Boolean(chart && chart.getOption().series[0].data.length);
      }),
    )
    .toBe(true);

  await page.evaluate(() => {
    localStorage.setItem("navidrome-theme-mode", "light");
    localStorage.setItem("navidrome-theme-palette", "gruvbox");
    window.dispatchEvent(new StorageEvent("storage", {
      key: "navidrome-theme-mode",
      newValue: "light",
    }));
  });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "gruvbox-light");
  await expect
    .poll(() =>
      page.evaluate(() => {
        const styles = getComputedStyle(document.documentElement);
        const option = echarts.getInstanceByDom(document.getElementById("reviewMonthlyChart")).getOption();
        return option.series[0].itemStyle.color
          === styles.getPropertyValue("--chart-1").trim();
      }),
    )
    .toBe(true);
});
