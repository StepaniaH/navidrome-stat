import test from "node:test";
import assert from "node:assert/strict";

import { dashboardMessages } from "../../src/static/js/messages-dashboard.js";
import { settingsMessages } from "../../src/static/js/messages-settings.js";
import { LOCALE_CODES } from "../../src/static/js/locales.js";

function keySet(locale, entries) {
  const seen = new Set();
  for (const [key] of entries) {
    assert.ok(!seen.has(key), `${locale}: duplicate message key ${key}`);
    seen.add(key);
  }
  return seen;
}

function assertCatalogConsistent(name, catalog) {
  const locales = Object.keys(catalog);
  test(`${name} catalogs contain no duplicate keys`, () => {
    for (const locale of locales) keySet(locale, catalog[locale]);
  });

  test(`${name} locales share the same key set`, () => {
    const base = [...keySet(locales[0], catalog[locales[0]])].sort();
    for (const locale of locales.slice(1)) {
      const keys = [...keySet(locale, catalog[locale])].sort();
      assert.deepEqual(keys, base);
    }
  });

  test(`${name} values are non-empty strings`, () => {
    for (const [locale, entries] of Object.entries(catalog)) {
      for (const [key, value] of entries) {
        assert.equal(typeof value, "string", `${locale}:${key} must be a string`);
        assert.ok(value.length > 0, `${locale}:${key} must not be empty`);
      }
    }
  });
}

assertCatalogConsistent("dashboard", dashboardMessages);
assertCatalogConsistent("settings", settingsMessages);

test("settings catalogs cover every supported locale name", () => {
  for (const [locale, entries] of Object.entries(settingsMessages)) {
    const keys = keySet(locale, entries);
    for (const code of LOCALE_CODES) {
      assert.ok(keys.has(`localeName.${code}`), `${locale} is missing localeName.${code}`);
    }
    assert.ok(keys.has("locale.native"), `${locale} is missing locale.native`);
  }
});

test("every message value is a non-empty string", () => {
  for (const [locale, entries] of Object.entries(dashboardMessages)) {
    for (const [key, value] of entries) {
      assert.equal(typeof value, "string", `${locale}:${key} must be a string`);
      assert.ok(value.length > 0, `${locale}:${key} must not be empty`);
    }
  }
});
