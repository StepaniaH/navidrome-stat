# Adding an interface language

The interface ships five languages (Simplified Chinese, Traditional Chinese, English, Japanese, German). New languages are one module plus two registrations; tests catch anything missed.

## Steps

1. Create `src/static/js/i18n/locales/<code>.js` (BCP-47 code, for example `es`) exporting one object with three string tables:

   ```js
   export default {
       dashboard: [
           ['status.connecting', 'Conectando…'],
           // ...
       ],
       review: [
           // ...
       ],
       settings: [
           // ...
       ],
   };
   ```

   Entries are `[key, value]` pairs. Copy the key set from `en.js` — every locale must define the same keys inside each domain. `{name}`-style placeholders are interpolation slots and must be kept in the translated string.

2. Register the module in `src/static/js/i18n/index.js` (import + one entry in `localeModules`).
3. Register the code in `src/static/js/locales.js` (`SUPPORTED_LOCALES`) with its native name; the settings page picker renders from this list.

## Verification

- `npm run test:unit` — the parity test scans the locales directory automatically: it checks key-set equality across languages, non-empty values, and that every locale name is covered by the settings tables.
- `.venv/bin/python -m pytest -q tests/test_static_settings.py` — guards the picker wiring.

Open a pull request with the new module; untranslated keys fail CI rather than shipping silently.
