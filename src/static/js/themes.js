/**
 * Theme registry shared by the pre-paint bootstrap, settings, and charts.
 *
 * `scheme` drives `data-scheme` on the root element, which light-specific
 * component rules key off instead of listing every light theme by id.
 */

export const THEMES = Object.freeze([
    { id: 'frappe', scheme: 'dark' },
    { id: 'latte', scheme: 'light' },
    { id: 'macchiato', scheme: 'dark' },
    { id: 'mocha', scheme: 'dark' },
    { id: 'nord', scheme: 'dark' },
    { id: 'dracula', scheme: 'dark' },
    { id: 'tokyo-night', scheme: 'dark' },
    { id: 'gruvbox-dark', scheme: 'dark' },
    { id: 'solarized-dark', scheme: 'dark' },
    { id: 'solarized-light', scheme: 'light' },
]);

export const DEFAULT_THEME = 'frappe';

const SCHEMES = new Map(THEMES.map((theme) => [theme.id, theme.scheme]));

export function isKnownTheme(id) {
    return SCHEMES.has(id);
}

export function themeScheme(id) {
    return SCHEMES.get(id) || SCHEMES.get(DEFAULT_THEME);
}

export function resolveTheme(id) {
    return isKnownTheme(id) ? id : DEFAULT_THEME;
}
