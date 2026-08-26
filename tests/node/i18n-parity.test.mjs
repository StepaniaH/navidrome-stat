import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";

import { LOCALE_CODES } from "../../src/static/js/locales.js";
import { pageMessages } from "../../src/static/js/i18n/index.js";

const DOMAINS = ["dashboard", "review", "settings"];

const localesDir = new URL("../../src/static/js/i18n/locales/", import.meta.url);
const catalogs = {};
for (const entry of readdirSync(localesDir).filter((name) => name.endsWith(".js")).sort()) {
  const code = entry.replace(/\.js$/, "");
  catalogs[code] = (await import(new URL(entry, localesDir).href)).default;
}

function keySet(locale, entries) {
  const seen = new Set();
  for (const [key] of entries) {
    assert.ok(!seen.has(key), `${locale}: duplicate message key ${key}`);
    seen.add(key);
  }
  return seen;
}

test("every supported locale ships a catalog module", () => {
  for (const code of LOCALE_CODES) {
    assert.ok(catalogs[code], `missing locale module for ${code}`);
  }
});

for (const domain of DOMAINS) {
  test(`${domain} tables exist in every locale module`, () => {
    for (const [code, module] of Object.entries(catalogs)) {
      assert.ok(Array.isArray(module[domain]), `${code} does not define ${domain}`);
    }
  });

  test(`${domain} keys match across locales`, () => {
    const base = [...keySet("en", catalogs.en[domain])].sort();
    for (const [code, module] of Object.entries(catalogs)) {
      if (code === "en") continue;
      const keys = [...keySet(code, module[domain])].sort();
      assert.deepEqual(keys, base);
    }
  });
}

test("catalog values are non-empty strings", () => {
  for (const [code, module] of Object.entries(catalogs)) {
    for (const domain of DOMAINS) {
      for (const [key, value] of module[domain]) {
        assert.equal(typeof value, "string", `${code}:${domain}:${key} must be a string`);
        assert.ok(value.length > 0, `${code}:${domain}:${key} must not be empty`);
      }
    }
  }
});

test("settings tables cover every supported locale name", () => {
  for (const [code, module] of Object.entries(catalogs)) {
    const keys = keySet(code, module.settings);
    for (const locale of LOCALE_CODES) {
      assert.ok(keys.has(`localeName.${locale}`), `${code} is missing localeName.${locale}`);
    }
    assert.ok(keys.has("locale.native"), `${code} is missing locale.native`);
  }
});

test("pageMessages merges requested domains for every locale", () => {
  const messages = pageMessages(...DOMAINS);
  assert.deepEqual(Object.keys(messages).sort(), Object.keys(catalogs).sort());
  for (const [code, module] of Object.entries(catalogs)) {
    const expected = new Set(DOMAINS.flatMap((domain) => module[domain].map(([key]) => key)));
    assert.deepEqual(Object.keys(messages[code]).sort(), [...expected].sort());
  }
});
