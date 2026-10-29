import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";

import { LOCALE_CODES } from "../../src/static/js/locales.js";
import { pageMessages } from "../../src/static/js/i18n/index.js";

const DOMAINS = ["dashboard", "review", "settings"];

const localesDir = new URL("../../src/static/js/i18n/locales/", import.meta.url);
const catalogs = {};
for (const entry of readdirSync(localesDir).filter((name) => name.endsWith(".js")).sort()) {
  const code = entry.replace(/\.js$/, "");
  catalogs[code] = (await import(new URL(entry, localesDir).href)).default;
}

const runtimeSource = readFileSync(new URL("../../src/static/localization.js", import.meta.url), "utf8");
const { createI18n } = await import(`data:text/javascript,${encodeURIComponent(runtimeSource)}`);

function keySet(locale, entries) {
  const seen = new Set();
  for (const entry of entries) {
    assert.ok(Array.isArray(entry) && entry.length === 2, `${locale}: expected a [key, value] pair`);
    const [key, value] = entry;
    assert.equal(typeof key, "string", `${locale}: message keys must be strings`);
    assert.ok(key.trim().length > 0, `${locale}: message keys must not be empty`);
    assert.equal(typeof value, "string", `${locale}:${key} must be a string`);
    assert.ok(value.trim().length > 0, `${locale}:${key} must not be empty`);
    assert.ok(!seen.has(key), `${locale}: duplicate message key ${key}`);
    seen.add(key);
  }
  return seen;
}

function placeholders(message) {
  return [...new Set([...message.matchAll(/\{([^{}]+)\}/g)].map((match) => match[1]))].sort();
}

test("supported locales, catalog modules, and page registrations match", () => {
  assert.equal(new Set(LOCALE_CODES).size, LOCALE_CODES.length, "duplicate supported locale");
  assert.deepEqual([...LOCALE_CODES].sort(), Object.keys(catalogs).sort());
  assert.deepEqual([...LOCALE_CODES].sort(), Object.keys(pageMessages(...DOMAINS)).sort());
});

for (const domain of DOMAINS) {
  test(`${domain} tables exist in every locale module`, () => {
    for (const [code, module] of Object.entries(catalogs)) {
      assert.ok(Array.isArray(module[domain]), `${code} does not define ${domain}`);
    }
  });

  test(`${domain} translations use English keys and preserve placeholders`, (t) => {
    const sourceKeys = keySet(`en:${domain}`, catalogs.en[domain]);
    const source = new Map(catalogs.en[domain]);
    for (const [code, module] of Object.entries(catalogs)) {
      if (code === "en") continue;
      const keys = keySet(`${code}:${domain}`, module[domain]);
      for (const [key, value] of module[domain]) {
        assert.ok(sourceKeys.has(key), `${code}:${domain}: unknown message key ${key}`);
        assert.deepEqual(
          placeholders(value), placeholders(source.get(key)),
          `${code}:${domain}:${key} must preserve the English placeholders`,
        );
      }
      const missing = [...sourceKeys].filter((key) => !keys.has(key));
      if (missing.length > 0) {
        const sample = missing.slice(0, 8).join(", ");
        t.diagnostic(`${code}:${domain}: ${missing.length} missing translations use English: ${sample}${missing.length > 8 ? ", …" : ""}`);
      }
    }
  });
}

test("English settings cover every supported locale name", () => {
  const keys = keySet("en:settings", catalogs.en.settings);
  for (const locale of LOCALE_CODES) {
    assert.ok(keys.has(`localeName.${locale}`), `en is missing localeName.${locale}`);
  }
  assert.ok(keys.has("locale.native"), "en is missing locale.native");
});

test("no-history guidance follows the configured play threshold", () => {
  const keys = [
    "history.emptyHint",
    "source.diagnostics.connected_no_plays.description",
  ];
  const messages = pageMessages("dashboard", "settings");
  for (const [code, localized] of Object.entries(messages)) {
    for (const key of keys) {
      const message = localized[key] ?? messages.en[key];
      assert.ok(message, `en is missing ${key}`);
      assert.doesNotMatch(message, /\d/, `${code}:${key} must not hard-code a threshold`);
    }
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

test("missing translations use English with interpolation and retain the selected locale", () => {
  const messages = pageMessages(...DOMAINS);
  delete messages.ru["source.diagnostics.facts"];
  delete messages.ru["localeName.ru"];
  delete messages.ru["history.emptyHint"];
  delete messages.ru["review.subtitle"];
  const i18n = createI18n({ messages, initialLocale: "ru", fallbackLocale: "en" });

  assert.equal(i18n.t("source.diagnostics.facts", { connections: 2, records: 12 }),
    "2 enabled connections · 12 playback records");
  assert.equal(i18n.t("localeName.ru"), "Russian");
  assert.equal(i18n.t("history.emptyHint"), messages.en["history.emptyHint"]);
  assert.equal(i18n.t("review.subtitle", { year: 2026 }), "2026 listening summary");
  assert.equal(i18n.t("page.heading"), "Настройки");
  assert.equal(i18n.getLocale(), "ru");
});
