import test from "node:test";
import assert from "node:assert/strict";

// filters.js touches window/location at import time; stub the globals first.
const store = new Map();
globalThis.window = {
  location: { search: "", pathname: "/", hash: "" },
  history: { replaceState(_s, _t, url) { globalThis.__lastUrl = url; } },
  localStorage: {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k),
  },
  addEventListener() {},
};
delete globalThis.window.location.search;

const { getFilters, setFilters, subscribe } = await import("../../src/static/js/filters.js");
const { validateCustomRange } = await import("../../src/static/js/format.js");

test("defaults when URL has no filter params", () => {
  assert.deepEqual(getFilters(), {
    days: 30,
    timezone: "browser",
    metric: "plays",
    sourceId: "",
    startDate: "",
    endDate: "",
  });
});

test("setFilters sanitizes unknown metric and broken ranges", () => {
  const next = setFilters({ metric: "bogus", startDate: "2026-02-01", endDate: "2026-01-01" });
  assert.equal(next.metric, "plays");
  assert.equal(next.startDate, "");
  assert.equal(next.endDate, "");
});

test("setFilters accepts a valid range and known metric", () => {
  const okRange = validateCustomRange("2026-01-01", "2026-03-01");
  assert.equal(okRange.ok, true);
  const next = setFilters({ days: 7, metric: "listen_time", startDate: "2026-01-01", endDate: "2026-03-01" });
  assert.equal(next.days, 7);
  assert.equal(next.metric, "listen_time");
  assert.equal(next.startDate, "2026-01-01");
});

test("subscribers are notified with a frozen copy", () => {
  let seen = null;
  const unsubscribe = subscribe((f) => { seen = f; });
  setFilters({ days: 90 });
  assert.equal(seen.days, 90);
  seen.days = 1;
  assert.equal(getFilters().days, 90);
  unsubscribe();
});
