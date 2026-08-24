/**
 * Supported interface languages.
 *
 * `native` is the language's own name (primary line in the picker); the
 * secondary line comes from the `localeName.<code>` key of whichever locale
 * is currently active, mirroring how system language pickers label entries.
 */

export const SUPPORTED_LOCALES = Object.freeze([
    { code: 'zh-CN', native: '简体中文' },
    { code: 'zh-TW', native: '繁體中文' },
    { code: 'en', native: 'English' },
    { code: 'ja', native: '日本語' },
]);

export const LOCALE_CODES = Object.freeze(SUPPORTED_LOCALES.map((locale) => locale.code));

export function nativeName(code) {
    return SUPPORTED_LOCALES.find((locale) => locale.code === code)?.native || code;
}
