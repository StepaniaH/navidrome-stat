import test from "node:test";
import assert from "node:assert/strict";

import { dashboardMessages } from "../../src/static/js/messages-dashboard.js";

function keySet(locale, entries) {
  const seen = new Set();
  for (const [key] of entries) {
    assert.ok(!seen.has(key), `${locale}: duplicate message key ${key}`);
    seen.add(key);
  }
  return seen;
}

test("dashboard catalogs contain no duplicate keys", () => {
  keySet("zh-CN", dashboardMessages.zhCN);
  keySet("en", dashboardMessages.en);
});

test("dashboard locales share the same key set", () => {
  const zhKeys = [...keySet("zh-CN", dashboardMessages.zhCN)].sort();
  const enKeys = [...keySet("en", dashboardMessages.en)].sort();
  assert.deepEqual(zhKeys, enKeys);
});

test("every message value is a non-empty string", () => {
  for (const [locale, entries] of Object.entries(dashboardMessages)) {
    for (const [key, value] of entries) {
      assert.equal(typeof value, "string", `${locale}:${key} must be a string`);
      assert.ok(value.length > 0, `${locale}:${key} must not be empty`);
    }
  }
});
