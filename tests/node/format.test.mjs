import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStatsQuery,
  buildStatsScopeQuery,
  escapeHtml,
  formatChangeText,
  formatPreciseDuration,
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

test("formatPreciseDuration keeps seconds and rounds once", () => {
  const messages = {
    "duration.hoursMinutesSeconds": "{hours}h {minutes}m {seconds}s",
    "duration.minutesSeconds": "{minutes}m {seconds}s",
    "duration.seconds": "{seconds}s",
  };
  const t = (key, values) => Object.entries(values).reduce(
    (text, [name, value]) => text.replace(`{${name}}`, value),
    messages[key],
  );

  assert.equal(formatPreciseDuration(219.2, t), "3m 39s");
  assert.equal(formatPreciseDuration(3599.6, t), "1h 0m 0s");
  assert.equal(formatPreciseDuration(-5, t), "0s");
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
    username: "alice",
    startDate: "2026-01-01",
    endDate: "2026-01-31",
  });
  assert.ok(full.includes("source_id=abc"));
  assert.ok(full.includes("username=alice"));
  assert.ok(full.includes("start_date=2026-01-01"));
  assert.ok(full.includes("end_date=2026-01-31"));
});

test("buildStatsScopeQuery follows dashboard filters without ranking metric", () => {
  assert.equal(
    buildStatsScopeQuery({
      days: 30,
      timezone: "Europe/Berlin",
      metric: "listen_time",
      sourceId: "server-1",
      username: "alice",
      startDate: "2026-01-01",
      endDate: "2026-01-31",
    }),
    "days=30&timezone=Europe%2FBerlin&source_id=server-1&username=alice&start_date=2026-01-01&end_date=2026-01-31",
  );
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
