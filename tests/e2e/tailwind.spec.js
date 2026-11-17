const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const stylesheet = fs.readFileSync(
  path.join(__dirname, "../../src/static/vendor/tailwind.css"), "utf8",
);

for (const width of [390, 1440]) {
  test(`bundled utilities retain dashboard colors and focus styles at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.setContent(`
      <div id="card" class="rounded-2xl bg-ink-900/80 shadow-card p-5 border border-white/5 backdrop-blur-sm text-slate-100">Card</div>
      <button id="button" class="rounded bg-accent text-white px-4 py-2">Action</button>
      <input id="focus" class="rounded-lg bg-ink-800 border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-accent/50">
      <div id="hidden" class="hidden">Hidden</div>
      <div id="invisible" class="invisible">Invisible</div>
      <span id="text" class="text-accent">Text</span>
    `);
    await page.addStyleTag({ content: stylesheet });
    await page.locator("#focus").focus();

    await expect(page.locator("#card")).toHaveCSS("border-radius", "16px");
    await expect(page.locator("#card")).toHaveCSS("border-top-width", "1px");
    await expect(page.locator("#card")).toHaveCSS("backdrop-filter", "blur(4px)");
    await expect(page.locator("#button")).toHaveCSS("border-radius", "4px");
    await expect(page.locator("#button")).toHaveCSS("cursor", "pointer");
    await expect(page.locator("#focus")).toHaveCSS("outline-style", "solid");
    await expect(page.locator("#focus")).toHaveCSS("outline-width", "2px");
    await expect(page.locator("#focus")).toHaveCSS("outline-offset", "2px");
    await expect(page.locator("#hidden")).toHaveCSS("display", "none");
    await expect(page.locator("#invisible")).toHaveCSS("visibility", "hidden");

    const colors = await page.evaluate(() => {
      // Compare sRGB pixels, not rgb()/oklab() serialization or inert shadow layers.
      const context = document.createElement("canvas").getContext("2d");
      function rgba(color) {
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = color;
        context.fillRect(0, 0, 1, 1);
        return [...context.getImageData(0, 0, 1, 1).data];
      }
      const card = getComputedStyle(document.getElementById("card"));
      const focus = getComputedStyle(document.getElementById("focus"));
      const ring = focus.boxShadow.match(/(rgba?\([^)]*\)|oklab\([^)]*\)) 0px 0px 0px 2px/);
      return {
        card: rgba(card.backgroundColor),
        foreground: rgba(card.color),
        border: rgba(card.borderTopColor),
        accent: rgba(getComputedStyle(document.getElementById("text")).color),
        ring: ring ? rgba(ring[1]) : null,
      };
    });
    expect(colors).toEqual({
      // Canvas stores premultiplied alpha; these are the v3 sRGB pixel values.
      card: [17, 17, 26, 204],
      foreground: [241, 245, 249, 255],
      border: [255, 255, 255, 13],
      accent: [167, 139, 250, 255],
      ring: [167, 139, 249, 128],
    });
  });
}
