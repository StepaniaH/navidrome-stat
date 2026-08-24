import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStatsQuery,
  escapeHtml,
  formatChangeText,
  validateCustomRange,
} from "../../src/static/js/format.js";

test("escapeHtml neutralizes markup characters", () => {
  assert.equal(
    escapeHtml(`<img src=x onerror="alert('1')">&`),
    "&lt;img src=x onerror=&quot;alert(&#39;1&#39;)&quot;&gt;&amp;",
  );
});

test("formatChangeText renders sign, one decimal and the compare label", () => {
  const t = { compareLabel: "vs previous" };
  assert.equal(formatChangeText(4.25, t), "↑ 4.3% vs previous");
  assert.equal(formatChangeText(-12, t), "↓ 12% vs previous");
  assert.equal(formatChangeText(0.0, t), "· 0% vs previous");
});

test("formatChangeText is empty for non-finite input", () => {
  assert.equal(formatChangeText(null, { compareLabel: "x" }), "");
  assert.equal(formatChangeText(Number.NaN, { compareLabel: "x" }), "");
});

test("buildStatsQuery omits empty source and custom ranges", () => {
  assert.equal(
    buildStatsQuery({ days: 7, timezone: "UTC", metric: "plays" }),
    "days=7&timezone=UTC&metric=plays",
  );
  const full = buildStatsQuery({
    days: 30,
    timezone: "Europe/Berlin",
    metric: "listen_time",
    sourceId: "abc",
    startDate: "2026-01-01",
    endDate: "2026-01-31",
  });
  assert.ok(full.includes("source_id=abc"));
  assert.ok(full.includes("start_date=2026-01-01"));
  assert.ok(full.includes("end_date=2026-01-31"));
});

test("validateCustomRange rejects missing, inverted and oversized ranges", () => {
  assert.deepEqual(validateCustomRange("", ""), { ok: false, reason: "range.missing" });
  assert.deepEqual(validateCustomRange("2026-02-01", "2026-01-01"), {
    ok: false,
    reason: "range.order",
  });
  assert.deepEqual(validateCustomRange("2025-01-01", "2026-03-01"), {
    ok: false,
    reason: "range.tooLong",
  });
  assert.equal(validateCustomRange("2026-01-01", "2026-12-31").ok, true);
});
