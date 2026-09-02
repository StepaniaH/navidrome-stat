import test from "node:test";
import assert from "node:assert/strict";

// filters.js touches window/location at import time; stub the globals first.
const store = new Map();
globalThis.window = {
  location: { search: "", pathname: "/", hash: "" },
  history: {
    state: null,
    replaceState(state, _t, url) {
      this.state = state;
      globalThis.__lastUrl = url;
    },
    pushState(state, _t, url) {
      this.state = state;
      globalThis.__lastUrl = url;
      globalThis.__pushedUrl = url;
    },
  },
  localStorage: {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k),
  },
  addEventListener() {},
};
delete globalThis.window.location.search;

const {
  getFilters,
  pushFilters,
  setFilters,
  subscribe,
} = await import("../../src/static/js/filters.js");
const { validateCustomRange } = await import("../../src/static/js/format.js");

test("defaults when URL has no filter params", () => {
  assert.deepEqual(getFilters(), {
    days: 30,
    timezone: "browser",
    metric: "plays",
    sourceId: "",
    username: "",
    startDate: "",
    endDate: "",
    relationDimension: "artist",
    artistMode: "combined",
    entityType: "",
    entityName: "",
    entityId: "",
    entitySourceId: "",
    entityArtist: "",
  });
});

test("relation dimension is sanitized and persisted when non-default", () => {
  const next = setFilters({ relationDimension: "client" });
  assert.equal(next.relationDimension, "client");
  let url = new URL(globalThis.__lastUrl, "https://example.test");
  assert.equal(url.searchParams.get("relation"), "client");

  const fallback = setFilters({ relationDimension: "track" });
  assert.equal(fallback.relationDimension, "artist");
  url = new URL(globalThis.__lastUrl, "https://example.test");
  assert.equal(url.searchParams.has("relation"), false);
});

test("entity identity is pushed into a shareable URL", () => {
  const next = pushFilters({
    entityType: "album",
    entityName: "Live & Loud",
    entityId: "album-1",
    entitySourceId: "source-1",
    entityArtist: "Artist A",
  });
  assert.equal(next.entityType, "album");
  const url = new URL(globalThis.__pushedUrl, "https://example.test");
  assert.equal(url.searchParams.get("entity_type"), "album");
  assert.equal(url.searchParams.get("entity_name"), "Live & Loud");
  assert.equal(url.searchParams.get("entity_id"), "album-1");
  assert.equal(url.searchParams.get("entity_source_id"), "source-1");
  assert.equal(url.searchParams.get("entity_artist"), "Artist A");
  assert.equal(globalThis.window.history.state.navidromeEntityDetail, true);
});

test("album detail URLs require a stable source identity", () => {
  const next = setFilters({
    entityType: "album",
    entityName: "Live",
    entityId: "album-1",
    entitySourceId: "",
    entityArtist: "Artist A",
  });
  assert.equal(next.entityType, "");
  assert.equal(next.entityName, "");
});

test("client detail identity is excluded from shareable URL state", () => {
  const next = setFilters({
    entityType: "client",
    entityName: "Symfonium",
    entityId: "ignored-id",
    entitySourceId: "ignored-source",
    entityArtist: "ignored-artist",
  });
  assert.equal(next.entityType, "");
  assert.equal(next.entityName, "");
  const url = new URL(globalThis.__lastUrl, "https://example.test");
  assert.equal(url.searchParams.has("entity_type"), false);
  assert.equal(url.searchParams.has("entity_name"), false);
  assert.equal(url.searchParams.has("entity_id"), false);
  assert.equal(url.searchParams.has("entity_source_id"), false);
  assert.equal(url.searchParams.has("entity_artist"), false);
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

test("subscribers receive a copy isolated from stored state", () => {
  let seen = null;
  const unsubscribe = subscribe((f) => { seen = f; });
  setFilters({ days: 90 });
  assert.equal(seen.days, 90);
  seen.days = 1;
  assert.equal(getFilters().days, 90);
  unsubscribe();
});
