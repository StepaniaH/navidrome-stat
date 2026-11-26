const fs = require("node:fs");
const path = require("node:path");
const { test, expect } = require("@playwright/test");

const ORIGIN = "http://127.0.0.1:39424";
const VECTORS_PATH = path.resolve(__dirname, "..", "supporter_vectors.py");
const VECTORS_SOURCE = fs.readFileSync(VECTORS_PATH, "utf8");

function readPyToken(name) {
  const blockMatch = VECTORS_SOURCE.match(new RegExp(`${name}\\s*=\\s*\\(([^)]+)\\)`, "m"));
  if (!blockMatch) {
    throw new Error(`Missing vector ${name} in tests/supporter_vectors.py`);
  }
  return Array.from(blockMatch[1].matchAll(/"([^"]+)"/g), (m) => m[1]).join("");
}

const PERSONAL_KEY = readPyToken("PERSONAL_KEY");
const PATRON_KEY = readPyToken("PATRON_KEY");
const ROTATED_KEY = readPyToken("ROTATED_KEY");

const PALETTES = [
  "builtin",
  "gruvbox",
  "catppuccin",
  "solarized",
  "nord",
  "dracula",
  "tokyo-night",
  "macchiato",
  "mocha",
];

async function resetSupporterState(request) {
  const delRes = await request.delete(`${ORIGIN}/api/supporter-key`);
  expect(delRes.ok()).toBeTruthy();
  const patchRes = await request.patch(`${ORIGIN}/api/supporter/preferences`, {
    data: { show_in_header: true },
  });
  expect(patchRes.ok()).toBeTruthy();
}

async function applyAppearance(page, { locale = "en", mode = "dark", palette = "builtin" } = {}) {
  await page.addInitScript(
    ({ loc, m, p }) => {
      localStorage.setItem("navidrome-language", loc);
      localStorage.setItem("navidrome-theme-mode", m);
      localStorage.setItem("navidrome-theme-palette", p);
    },
    { loc: locale, m: mode, p: palette },
  );
}

async function assertFiltersNotTruncated(page) {
  const truncated = await page.evaluate(() => {
    const ids = ["statsWindowButtonLabel", "statsSourceButtonLabel", "statsUserButtonLabel"];
    return ids
      .map((id) => {
        const el = document.getElementById(id);
        if (!el) return { id, missing: true };
        return {
          id,
          text: el.textContent.trim(),
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
        };
      })
      .filter((item) => item.missing || item.scrollWidth > item.clientWidth + 1);
  });
  expect(truncated, "Dashboard top-bar filter labels must not truncate").toEqual([]);
}

test.beforeEach(async ({ page, request }) => {
  await resetSupporterState(request);
  await page.route("**/api/coverart*", (route) => route.fulfill({ status: 404 }));
  await page.route("**/api/stats/album-cover*", (route) => route.fulfill({ status: 404 }));
});

test.afterAll(async ({ request }) => {
  await resetSupporterState(request);
});

test("unactivated state keeps settings header clean, previews inline brand bar, and localizes CTA", async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 1280, height: 840 });
  await applyAppearance(page, { locale: "en", mode: "dark", palette: "builtin" });

  await page.goto(`${ORIGIN}/`);
  await expect(page.locator("#supporterBadge")).toBeHidden();
  await expect(page.locator(".dashboard-header .brand-version")).toHaveCount(0);
  await expect(page.locator(".app-footer-ver")).toBeVisible();
  await expect(page.locator("#statusBadge")).toHaveClass(/is-quiet/);
  await expect(page.locator("#statusText")).toHaveClass(/visually-hidden/);
  await expect(page.locator("#refreshBtn")).toHaveAttribute("title", /Last updated/);
  await assertFiltersNotTruncated(page);
  await expect(page.locator("#footerSupportLink")).toHaveAttribute("href", "/settings#supporter");
  await expect(page.locator("#footerSupportLabel")).toHaveText("Support Navidrome Stat");

  await page.goto(`${ORIGIN}/settings#supporter`);
  await expect(page.locator("#tab-supporter")).toBeVisible();
  await expect(page.locator(".page-header #settingsSupporterBadge")).toHaveCount(0);
  await expect(page.locator(".page-header")).not.toHaveClass(/has-supporter-vinyl/);
  await expect(page.locator(".supporter-showcase")).toBeVisible();
  await expect(page.locator(".supporter-brandbar-preview")).toBeVisible();
  await expect(page.locator("#tabSupporterDot")).toBeHidden();
  await expect(page.locator(".supporter-cta-btn")).toHaveAttribute(
    "href",
    "https://navidrome-stat.stepaniah.me/?lang=en#support",
  );

  // Inline brand-bar preview switches between Personal and Patron without touching Settings H1
  const inlineLabel = page.locator("[data-supporter-inline-badge-label]");
  await expect(inlineLabel).toHaveText("Supporter");
  await page.locator('[data-supporter-preview="patron"]').click();
  await expect(page.locator('[data-supporter-preview="patron"]')).toHaveAttribute("aria-pressed", "true");
  await expect(inlineLabel).toHaveText("Patron");
  await expect(page.locator("[data-supporter-inline-badge]")).toHaveClass(/is-patron/);
  await expect(page.locator(".page-header #settingsSupporterBadge")).toHaveCount(0);

  // Navigating away resets preview tier back to default Personal
  await page.locator("#tab-about-btn").click();
  await page.locator("#tab-supporter-btn").click();
  await expect(inlineLabel).toHaveText("Supporter");

  // Localized CTA URL updates for other supported locales
  const jaPage = await context.newPage();
  await jaPage.addInitScript(() => localStorage.setItem("navidrome-language", "ja"));
  await jaPage.goto(`${ORIGIN}/settings#supporter`);
  await expect(jaPage.locator(".supporter-cta-btn")).toHaveAttribute(
    "href",
    "https://navidrome-stat.stepaniah.me/?lang=ja#support",
  );
  await jaPage.close();
});

test("invalid format and untrusted Ed25519 keys show errors without saving", async ({ page }) => {
  await applyAppearance(page, { locale: "en" });
  await page.goto(`${ORIGIN}/settings#supporter`);

  const input = page.locator("#supporterKeyInput");
  const activate = page.locator("[data-supporter-activate]");
  const status = page.locator("#supporterActionStatus");

  await input.fill("not-a-valid-key");
  await activate.click();
  await expect(status).toBeVisible();
  await expect(status).toHaveText(/Invalid key format/);
  await expect(page.locator(".supporter-showcase")).toBeVisible();

  await input.fill(ROTATED_KEY);
  await activate.click();
  await expect(status).toBeVisible();
  await expect(status).toHaveText(/Signature verification failed/);
  await expect(page.locator(".supporter-showcase")).toBeVisible();
});

test("personal and patron activation, non-truncating filters, header toggle, review seal, removal, and zero leakage", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1152, height: 840 });
  await applyAppearance(page, { locale: "en" });
  await page.goto(`${ORIGIN}/settings#supporter`);

  await page.locator("#supporterKeyInput").fill(PERSONAL_KEY);
  await page.locator("[data-supporter-activate]").click();

  await expect(page.locator(".supporter-plaque.is-activated")).toBeVisible();
  await expect(page.locator(".supporter-showcase")).toHaveCount(0);
  await expect(page.locator(".plaque-title")).toHaveText("Personal Supporter");
  await expect(page.locator(".supporter-receipt")).toContainText("NS1.");
  await expect(page.locator(".supporter-receipt")).toContainText("Verified offline");
  await expect(page.locator(".supporter-plaque .about-list")).toContainText("•••••001");
  await expect(page.locator(".plaque-since")).toContainText("2026-04-17");
  await expect(page.locator("[data-supporter-inline-badge]")).toBeVisible();
  await expect(page.locator("[data-supporter-inline-badge-label]")).toHaveText("Supporter");
  await expect(page.locator(".page-header #settingsSupporterBadge")).toHaveCount(0);
  await expect(page.locator("#tabSupporterDot")).toBeVisible();

  // Zero raw key or full order ID in rendered DOM or browser storage
  const leakCheck = await page.evaluate(() => ({
    text: document.body.innerText,
    local: JSON.stringify(localStorage),
    session: JSON.stringify(sessionStorage),
  }));
  const personalSig = PERSONAL_KEY.split(".")[2];
  for (const hay of [leakCheck.text, leakCheck.local, leakCheck.session]) {
    expect(hay).not.toContain(PERSONAL_KEY);
    expect(hay).not.toContain(personalSig);
    expect(hay).not.toContain("ORD-0001");
  }

  // Persists across reload and keeps Dashboard filters completely untruncated
  await page.reload();
  await expect(page.locator(".plaque-title")).toHaveText("Personal Supporter");

  await page.goto(`${ORIGIN}/`);
  await expect(page.locator("#supporterBadge")).toBeVisible();
  await expect(page.locator("#supporterBadgeLabel")).toHaveText("Supporter");
  await assertFiltersNotTruncated(page);
  await expect(page.locator("#footerSupportLabel")).toHaveText("Supporting since 2026-04-17");

  await page.goto(`${ORIGIN}/review`);
  await expect(page.locator("#reviewSupporterSeal")).toBeVisible();
  await expect(page.locator("#reviewSupporterSealTier")).toHaveText("Personal Supporter");
  await expect(page.locator("#reviewSupporterSealSince")).toHaveText("Supporting since 2026-04-17");

  // Toggle header visibility OFF: hides inline & dashboard/review indicators while keeping Settings plaque lit
  await page.goto(`${ORIGIN}/settings#supporter`);
  const toggle = page.locator("#supporterShowHeaderToggle");
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await expect(page.locator("[data-supporter-inline-badge]")).toBeHidden();
  await expect(page.locator(".supporter-plaque.is-activated")).toBeVisible();

  await page.goto(`${ORIGIN}/`);
  await expect(page.locator("#supporterBadge")).toBeHidden();

  await page.goto(`${ORIGIN}/review`);
  await expect(page.locator("#reviewSupporterSeal")).toBeHidden();

  // Re-enable header visibility and upgrade to Patron tier
  await page.goto(`${ORIGIN}/settings#supporter`);
  await page.locator("#supporterShowHeaderToggle").click();
  await expect(page.locator("#supporterShowHeaderToggle")).toHaveAttribute("aria-checked", "true");
  await page.locator(".supporter-manage summary").click();
  await page.locator("#supporterKeyInput").fill(PATRON_KEY);
  await page.locator("[data-supporter-activate]").click();

  await expect(page.locator(".plaque-title")).toHaveText("Patron Supporter");
  await expect(page.locator("[data-supporter-inline-badge-label]")).toHaveText("Patron");
  await expect(page.locator("[data-supporter-inline-badge]")).toHaveClass(/is-patron/);

  await page.goto(`${ORIGIN}/`);
  await expect(page.locator("#supporterBadge")).toHaveClass(/is-patron/);
  await expect(page.locator("#supporterBadgeLabel")).toHaveText("Patron");
  await assertFiltersNotTruncated(page);

  await page.goto(`${ORIGIN}/review`);
  await expect(page.locator("#reviewSupporterSeal")).toBeVisible();
  await expect(page.locator("#reviewSupporterSealTier")).toHaveText("Patron Supporter");

  // Clear stored key reverts back to inactive showcase
  await page.goto(`${ORIGIN}/settings#supporter`);
  await page.locator(".supporter-manage summary").click();
  await page.locator("[data-supporter-clear]").click();
  await expect(page.locator(".supporter-showcase")).toBeVisible();
  await expect(page.locator("#tabSupporterDot")).toBeHidden();
});

test("all 18 dark and light themes meet WCAG AA contrast for supporter plaque and inline badge", async ({
  page,
  request,
}) => {
  test.setTimeout(60_000);
  const res = await request.put(`${ORIGIN}/api/supporter-key`, {
    data: { key: PATRON_KEY },
  });
  expect(res.ok()).toBeTruthy();

  for (const mode of ["dark", "light"]) {
    for (const palette of PALETTES) {
      const checkPage = await page.context().newPage();
      await checkPage.addInitScript(
        ({ m, p }) => {
          localStorage.setItem("navidrome-language", "en");
          localStorage.setItem("navidrome-theme-mode", m);
          localStorage.setItem("navidrome-theme-palette", p);
        },
        { m: mode, p: palette },
      );
      await checkPage.goto(`${ORIGIN}/settings#supporter`);
      await expect(checkPage.locator("html")).toHaveAttribute("data-scheme", mode);
      await expect(checkPage.locator(".supporter-plaque.is-activated")).toBeVisible();
      await checkPage.locator(".supporter-manage summary").click();

      const failures = await checkPage.evaluate((scheme) => {
        function parseRgba(str) {
          const m = str.match(/rgba?\(([^)]+)\)/);
          if (!m) return [0, 0, 0, 0];
          const parts = m[1].split(",").map((s) => Number.parseFloat(s.trim()));
          return [parts[0] || 0, parts[1] || 0, parts[2] || 0, parts[3] === undefined ? 1 : parts[3]];
        }

        function blend(fg, bg) {
          const a = fg[3];
          return [
            fg[0] * a + bg[0] * (1 - a),
            fg[1] * a + bg[1] * (1 - a),
            fg[2] * a + bg[2] * (1 - a),
            1,
          ];
        }

        function luminance([r, g, b]) {
          const ch = [r, g, b].map((v) => {
            const s = v / 255;
            return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
        }

        function contrast(c1, c2) {
          const l1 = luminance(c1);
          const l2 = luminance(c2);
          return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        }

        function extractGradientStops(bgImage, bgClip = "") {
          if (!bgImage || bgImage === "none") return [];
          // Split top-level background-image layers and skip border-box-only border layers
          const layers = [];
          let depth = 0;
          let start = 0;
          for (let i = 0; i < bgImage.length; i++) {
            if (bgImage[i] === "(") depth += 1;
            else if (bgImage[i] === ")") depth -= 1;
            else if (bgImage[i] === "," && depth === 0) {
              layers.push(bgImage.slice(start, i).trim());
              start = i + 1;
            }
          }
          layers.push(bgImage.slice(start).trim());
          const clips = bgClip.split(",").map((s) => s.trim());
          const surfaceLayer = layers.find((_, idx) => clips[idx] !== "border-box") || layers[0];
          const matches = (surfaceLayer || "").match(/rgba?\([^)]+\)/g) || [];
          return matches.map(parseRgba).filter((c) => c[3] > 0);
        }

        function effectiveBgCandidates(el) {
          const stack = [];
          let gradientStops = [];
          for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
            const cs = getComputedStyle(cur);
            if (!gradientStops.length) {
              const stops = extractGradientStops(cs.backgroundImage, cs.backgroundClip);
              if (stops.length) gradientStops = stops;
            }
            const rgba = parseRgba(cs.backgroundColor);
            if (rgba[3] > 0) {
              stack.push(rgba);
              if (rgba[3] >= 1) break;
            }
            if (gradientStops.length && gradientStops.every((s) => s[3] >= 1)) break;
          }
          const rootBg = parseRgba(getComputedStyle(document.body).backgroundColor);
          let acc = rootBg[3] > 0
            ? blend(rootBg, scheme === "light" ? [255, 255, 255, 1] : [15, 20, 27, 1])
            : (scheme === "light" ? [255, 255, 255, 1] : [15, 20, 27, 1]);
          for (let i = stack.length - 1; i >= 0; i--) {
            acc = blend(stack[i], acc);
          }
          if (!gradientStops.length) return [acc];
          return gradientStops.map((stop) => blend(stop, acc));
        }

        const selectors = [
          "[data-supporter-inline-badge-label]",
          ".brandbar-preview-wordmark",
          ".plaque-eyebrow",
          ".plaque-title",
          ".plaque-tier-tag",
          ".plaque-since",
          ".plaque-thanks",
          ".supporter-receipt .rk",
          ".supporter-receipt .rv",
          ".supporter-plaque .about-list dt",
          ".supporter-plaque .about-list dd",
          ".supporter-manage summary",
        ];

        const issues = [];
        for (const sel of selectors) {
          const els = document.querySelectorAll(sel);
          for (const el of els) {
            const cs = getComputedStyle(el);
            const candidates = effectiveBgCandidates(el);
            const worstRatio = Math.min(
              ...candidates.map((bg) => contrast(blend(parseRgba(cs.color), bg), bg)),
            );
            const fontSize = Number.parseFloat(cs.fontSize);
            const weight = Number.parseInt(cs.fontWeight, 10) || 400;
            const isLarge = fontSize >= 24 || (fontSize >= 18.66 && weight >= 700);
            const minRequired = isLarge ? 3.0 : 4.5;
            if (worstRatio < minRequired) {
              issues.push({ sel, ratio: Number(worstRatio.toFixed(2)), minRequired });
            }
          }
        }
        return issues;
      }, mode);

      await checkPage.close();
      expect(failures, `WCAG contrast failures for ${mode} palette "${palette}"`).toEqual([]);
    }
  }
});

test("no horizontal overflow across desktop, tablet, and mobile viewports", async ({
  page,
  request,
}) => {
  await applyAppearance(page, { locale: "en" });

  const viewports = [
    { width: 1280, height: 800 },
    { width: 900, height: 800 },
    { width: 768, height: 900 },
    { width: 390, height: 844 },
    { width: 360, height: 780 },
  ];

  for (const vp of viewports) {
    await page.setViewportSize(vp);
    await page.goto(`${ORIGIN}/settings#supporter`);
    await expect(page.locator(".supporter-showcase")).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, `showcase overflow at ${vp.width}x${vp.height}`).toBeLessThanOrEqual(0);
  }

  const putRes = await request.put(`${ORIGIN}/api/supporter-key`, {
    data: { key: PATRON_KEY },
  });
  expect(putRes.ok()).toBeTruthy();

  for (const vp of viewports) {
    await page.setViewportSize(vp);
    for (const route of ["/", "/settings#supporter", "/review"]) {
      await page.goto(`${ORIGIN}${route}`);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow, `${route} overflow at ${vp.width}x${vp.height}`).toBeLessThanOrEqual(0);
    }
  }
});

test("multi-tab sync, slow GET race guard, keyboard focus, custom theme contrast, and responsive header alerts", async ({
  context,
  request,
}) => {
  test.setTimeout(60_000);

  // 1. Slow initial GET /api/supporter must never overwrite a faster key activation,
  //    and Patron preview updates pricing copy while preserving keyboard focus.
  const settingsPage = await context.newPage();
  await settingsPage.addInitScript(() => localStorage.setItem("navidrome-language", "en"));

  let releaseSlowGet;
  const slowGetGate = new Promise((resolve) => {
    releaseSlowGet = resolve;
  });
  let interceptedInitialGet = false;
  await settingsPage.route("**/api/supporter", async (route) => {
    if (!interceptedInitialGet && route.request().method() === "GET") {
      interceptedInitialGet = true;
      await slowGetGate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          supporter: {
            active: false,
            status: "inactive",
            tier: null,
            issued_at: null,
            key_preview: null,
            order_preview: null,
            origin: "none",
            env_configured: false,
            can_edit: true,
            can_clear: false,
            show_in_header: true,
          },
        }),
      });
      return;
    }
    await route.continue();
  });

  await settingsPage.goto(`${ORIGIN}/settings#supporter`);
  await expect(settingsPage.locator(".supporter-cta-note")).toContainText("Patron from $29");
  const patronPreviewBtn = settingsPage.locator('[data-supporter-preview="patron"]');
  await patronPreviewBtn.focus();
  await settingsPage.keyboard.press("Space");
  await expect(patronPreviewBtn).toHaveAttribute("aria-pressed", "true");
  await expect(settingsPage.locator(".supporter-showcase-pillars")).toContainText("Patron from $29");
  expect(
    await settingsPage.evaluate(() => document.activeElement?.getAttribute("data-supporter-preview")),
  ).toBe("patron");

  await settingsPage.locator("#supporterKeyInput").fill(PATRON_KEY);
  await settingsPage.locator("[data-supporter-activate]").click();
  await expect(settingsPage.locator(".plaque-title")).toHaveText("Patron Supporter");

  // Release the stale initial GET and verify it does NOT revert the active plaque
  releaseSlowGet();
  await settingsPage.waitForTimeout(150);
  await expect(settingsPage.locator(".plaque-title")).toHaveText("Patron Supporter");
  await settingsPage.unroute("**/api/supporter");

  // 2. Open Dashboard and Review tabs simultaneously, then toggle show_in_header OFF via keyboard Space
  const dashPage = await context.newPage();
  await dashPage.addInitScript(() => localStorage.setItem("navidrome-language", "en"));
  await dashPage.goto(`${ORIGIN}/`);
  await expect(dashPage.locator("#supporterBadge")).toBeVisible();

  const reviewPage = await context.newPage();
  await reviewPage.addInitScript(() => localStorage.setItem("navidrome-language", "en"));
  await reviewPage.goto(`${ORIGIN}/review`);
  await expect(reviewPage.locator("#reviewSupporterSeal")).toBeVisible();

  const toggleBtn = settingsPage.locator("#supporterShowHeaderToggle");
  await toggleBtn.focus();
  await settingsPage.keyboard.press("Space");
  await expect(toggleBtn).toHaveAttribute("aria-checked", "false");
  expect(await settingsPage.evaluate(() => document.activeElement?.id)).toBe(
    "supporterShowHeaderToggle",
  );

  // Open Dashboard and Review tabs update automatically without reload
  await expect(dashPage.locator("#supporterBadge")).toBeHidden();
  await expect(reviewPage.locator("#reviewSupporterSeal")).toBeHidden();

  // Re-enable header badge and check mid-width / phone header geometry + degraded alert link
  await settingsPage.keyboard.press("Space");
  await expect(toggleBtn).toHaveAttribute("aria-checked", "true");
  await expect(dashPage.locator("#supporterBadge")).toBeVisible();

  await dashPage.route("**/api/stats/collection-status*", (route) =>
    route.fulfill({ json: { status: "degraded", mixed_collection: true } }),
  );

  async function assertHeaderGeometry(pageUnderTest, label) {
    const geom = await pageUnderTest.evaluate(() => {
      const triggers = [...document.querySelectorAll(".dashboard-filters .filter-trigger")];
      const rects = triggers.map((el) => el.getBoundingClientRect());
      let overlaps = 0;
      for (let i = 0; i < rects.length; i++) {
        for (let j = i + 1; j < rects.length; j++) {
          const a = rects[i];
          const b = rects[j];
          const xOverlap = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
          const yOverlap = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
          if (xOverlap > 1 && yOverlap > 1) overlaps += 1;
        }
      }
      const clipped = [...document.querySelectorAll(".filter-trigger-value")].filter(
        (el) => el.scrollWidth > el.clientWidth + 1,
      );
      return {
        overlaps,
        clipped: clipped.map((el) => el.textContent.trim()),
        overflow: document.documentElement.scrollWidth - window.innerWidth,
      };
    });
    expect(geom, label).toEqual({ overlaps: 0, clipped: [], overflow: 0 });
  }

  for (const vp of [
    { width: 900, height: 800 },
    { width: 360, height: 780 },
  ]) {
    await dashPage.setViewportSize(vp);
    await dashPage.locator("#refreshBtn").click();
    await expect(dashPage.locator("#statusBadge")).toBeVisible();
    await expect(dashPage.locator("#refreshStatusPip")).toHaveClass(/is-error/);
    await assertHeaderGeometry(dashPage, `EN ${vp.width}px degraded+mixed`);
  }

  // Clicking the visible alert badge navigates straight to Settings -> Source / Connections
  await dashPage.locator("#statusBadge").click();
  await expect(dashPage).toHaveURL(/\/settings#source$/);
  await expect(dashPage.locator("#tab-source")).toBeVisible();

  // 768px Russian header with Patron badge stays overlap-free and unclipped
  const ruPage = await context.newPage();
  await ruPage.addInitScript(() => localStorage.setItem("navidrome-language", "ru"));
  await ruPage.setViewportSize({ width: 768, height: 900 });
  await ruPage.goto(`${ORIGIN}/`);
  await expect(ruPage.locator("#supporterBadge")).toBeVisible();
  await assertHeaderGeometry(ruPage, "RU 768px");

  // 3. Custom light palette applied onto builtin-dark updates --sup-* and preserves WCAG AA contrast
  const customThemePage = await context.newPage();
  await customThemePage.addInitScript(() => {
    localStorage.setItem("navidrome-language", "en");
    localStorage.setItem("navidrome-theme-mode", "dark");
    localStorage.setItem("navidrome-theme-palette", "default");
    localStorage.setItem(
      "navidrome-theme-customizations",
      JSON.stringify({
        schemaVersion: 1,
        overrides: {
          "builtin-dark": {
            accent: "#75152a",
            background: "#f7f5f6",
            field: "#ebe4e6",
            muted: "#574349",
            surface: "#ffffff",
            text: "#1f1418",
          },
        },
      }),
    );
  });
  await customThemePage.goto(`${ORIGIN}/settings#supporter`);
  await expect(customThemePage.locator(".supporter-plaque.is-activated")).toBeVisible();
  const customCheck = await customThemePage.evaluate(() => {
    function parseRgba(str) {
      const m = str.match(/rgba?\(([^)]+)\)/);
      if (!m) return [0, 0, 0, 0];
      const p = m[1].split(",").map((s) => Number.parseFloat(s.trim()));
      return [p[0] || 0, p[1] || 0, p[2] || 0, p[3] === undefined ? 1 : p[3]];
    }
    function lum([r, g, b]) {
      const ch = [r, g, b].map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
    }
    function ratio(a, b) {
      const l1 = lum(a);
      const l2 = lum(b);
      return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    }
    const supMain = getComputedStyle(document.documentElement).getPropertyValue("--sup-main").trim();
    const white = [255, 255, 255, 1];
    const minContrast = Math.min(
      ...[
        ".plaque-since",
        ".plaque-eyebrow",
        ".plaque-tier-tag",
        ".supporter-receipt .rv",
        "[data-supporter-inline-badge-label]",
      ].map((sel) => ratio(parseRgba(getComputedStyle(document.querySelector(sel)).color), white)),
    );
    return { supMain, minContrast: Number(minContrast.toFixed(2)) };
  });
  expect(customCheck.supMain).toBe("#75152a");
  expect(customCheck.minContrast).toBeGreaterThanOrEqual(4.5);

  // Reverse customization: dark surface applied onto builtin-light on /review
  const reverseReviewPage = await context.newPage();
  await reverseReviewPage.addInitScript(() => {
    localStorage.setItem("navidrome-language", "en");
    localStorage.setItem("navidrome-theme-mode", "light");
    localStorage.setItem("navidrome-theme-palette", "default");
    localStorage.setItem(
      "navidrome-theme-customizations",
      JSON.stringify({
        schemaVersion: 1,
        overrides: {
          "builtin-light": {
            accent: "#f59e0b",
            background: "#0b1220",
            field: "#1e293b",
            muted: "#cbd5e1",
            surface: "#111827",
            text: "#f8fafc",
          },
        },
      }),
    );
  });
  await reverseReviewPage.goto(`${ORIGIN}/review`);
  await expect(reverseReviewPage.locator("#reviewSupporterSeal")).toBeVisible();
  const reverseSealContrast = await reverseReviewPage.evaluate(() => {
    function parseRgba(str) {
      const m = str.match(/rgba?\(([^)]+)\)/);
      if (!m) return [0, 0, 0, 0];
      const p = m[1].split(",").map((s) => Number.parseFloat(s.trim()));
      return [p[0] || 0, p[1] || 0, p[2] || 0, p[3] === undefined ? 1 : p[3]];
    }
    function lum([r, g, b]) {
      const ch = [r, g, b].map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
    }
    const fg = parseRgba(getComputedStyle(document.querySelector(".review-supporter-seal-badge")).color);
    const darkSurface = [17, 24, 39, 1];
    const l1 = lum(fg);
    const l2 = lum(darkSurface);
    return Number(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)).toFixed(2));
  });
  expect(reverseSealContrast).toBeGreaterThanOrEqual(4.5);
  await reverseReviewPage.close();

  // 4. Failed key submission (400) before initial GET finishes must NOT discard the valid active GET response
  const failedBeforeLoadPage = await context.newPage();
  await failedBeforeLoadPage.addInitScript(() => localStorage.setItem("navidrome-language", "en"));
  let releaseActiveGet;
  const activeGetGate = new Promise((resolve) => {
    releaseActiveGet = resolve;
  });
  let delayedFirstGet = false;
  await failedBeforeLoadPage.route("**/api/supporter", async (route) => {
    if (!delayedFirstGet && route.request().method() === "GET") {
      delayedFirstGet = true;
      await activeGetGate;
    }
    await route.continue();
  });
  await failedBeforeLoadPage.goto(`${ORIGIN}/settings#supporter`);
  await failedBeforeLoadPage.locator("#supporterKeyInput").fill("bad-key");
  await failedBeforeLoadPage.locator("[data-supporter-activate]").click();
  await expect(failedBeforeLoadPage.locator("#supporterActionStatus")).toBeVisible();
  releaseActiveGet();
  await expect(failedBeforeLoadPage.locator(".plaque-title")).toHaveText("Patron Supporter");
  await failedBeforeLoadPage.close();

  await request.delete(`${ORIGIN}/api/supporter-key`);
  await settingsPage.close();
  await dashPage.close();
  await reviewPage.close();
  await ruPage.close();
  await customThemePage.close();
});
