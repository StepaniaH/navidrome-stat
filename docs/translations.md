# Adding an interface language

The interface ships seven languages (Simplified Chinese, Traditional Chinese, English, Japanese, German, Spanish, French). New languages are one module plus two registrations; tests catch anything missed.

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

## Theme key conventions

Theme copy describes two separate choices:

- `preferences.themeMode` and `preferences.themeMode.system|dark|light` label how brightness is resolved.
- `preferences.palette` and `preferences.palette.<family>` label color families. The current family keys are `builtin`, `gruvbox`, `catppuccin`, `solarized`, `nord`, `dracula`, `tokyo-night`, `macchiato`, and `mocha`.
- `preferences.paletteUnavailable` explains that a family has no variant for the selected mode; `preferences.themeSavedLocal` states that the choice is browser-local.

Palette labels do not append “dark” or “light”; the mode control already carries that meaning. Concrete variant IDs such as `builtin-light`, `gruvbox-dark`, `frappe`, or `latte` belong to the resolver rather than the new controls. Existing `preferences.theme.<variant>` entries remain in the catalogs for compatibility, but the card picker reads the mode and family keys above. When adding a mode or palette family, add the same keys to every locale in the same change and keep product names consistently capitalized.

## Verification

- `npm run test:unit` — the parity test scans the locales directory automatically: it checks key-set equality across languages, non-empty values, and that every locale name is covered by the settings tables.
- `.venv/bin/python -m pytest -q tests/test_static_settings.py` — guards the picker wiring.

Open a pull request with the new module; untranslated keys fail CI rather than shipping silently.
