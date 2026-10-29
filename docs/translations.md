# Interface translations

The interface ships eight languages: Simplified Chinese, Traditional Chinese, English, Japanese, German, Spanish, French, and Russian.

## Maintenance policy

English (`en.js`) is the source language and must include every interface message. Community translations can be updated independently of feature releases. Missing entries use the English message with the same interpolation values.

Add new messages to the appropriate English domain, then include translations that have been reviewed. Leave untranslated entries absent from the other catalogs.

Keep existing translations when an English wording change preserves the meaning. When the meaning changes, update the translations and remove outdated entries until replacements have been reviewed. Remove deleted message keys from every catalog.

Translation additions, corrections, and proofreading are welcome through pull requests.

## Adding a language

1. Create `src/static/js/i18n/locales/<code>.js` (BCP-47 code, for example `es`) exporting one object with three string tables:

   ```js
   export default {
       dashboard: [
           ['status.connecting', 'Conectando…'],
       ],
       review: [],
       settings: [
           ['locale.native', 'Español'],
       ],
   };
   ```

   Entries are `[key, value]` pairs. Use keys from the matching domain in `en.js` and include the translations you have reviewed. Each domain must exist, but its table may be incomplete. Keep every `{name}`-style placeholder unchanged. Duplicate keys, unknown keys, empty values, and mismatched placeholders fail CI.

2. Register the module in `src/static/js/i18n/index.js` (import + one entry in `localeModules`).
3. Append the code to `src/static/js/locales.js` (`SUPPORTED_LOCALES`) with its native name. Keep the existing order; the settings picker renders from this list.
4. Add `localeName.<code>` to the English settings table so the picker always has a readable secondary label. Add translated labels to the other catalogs where possible; missing labels fall back to English.
5. Update the supported languages in both READMEs, both usage guides, and this page.

## Theme key conventions

Theme copy describes two separate choices:

- `preferences.themeMode` and `preferences.themeMode.system|dark|light` label how brightness is resolved.
- `preferences.palette` and `preferences.palette.<family>` label color families. The current family keys are `builtin`, `gruvbox`, `catppuccin`, `solarized`, `nord`, `dracula`, `tokyo-night`, `macchiato`, and `mocha`.
- `preferences.themeSavedLocal` states that the choice is browser-local.

Palette labels do not append “dark” or “light”; the mode control already carries that meaning. Concrete variant IDs such as `builtin-light`, `gruvbox-dark`, `frappe`, or `latte` belong to the resolver and do not need catalog entries. Add new mode or palette keys to English first, then update available translations. Keep product names consistently capitalized.

## Verification

- `npm run test:unit` — validates registration, catalog entries, and placeholders. Missing translations are listed as diagnostics and do not fail the checks. English must cover every supported language name.
- `.venv/bin/python -m pytest -q tests/test_static_settings.py` — guards the picker wiring.
- `npm run test:e2e` — checks browser behavior, including language selection, persistence, and English fallback for missing translations.
- `python3 scripts/check_md_links.py` — checks local Markdown links after documentation changes.

Review terminology, number forms, and text layout in settings, the dashboard, Listening Review, and narrow screens.
