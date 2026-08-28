/**
 * Theme registry and pure appearance resolver.
 *
 * Preferences keep appearance mode and palette family independent. The rest
 * of the application continues to consume a concrete `data-theme` plus the
 * resolved `data-scheme`, so existing page styles have one stable contract.
 */

export const THEME_MODES = Object.freeze(['system', 'dark', 'light']);

export const THEMES = Object.freeze([
    { id: 'builtin-dark', scheme: 'dark', palette: 'builtin' },
    { id: 'builtin-light', scheme: 'light', palette: 'builtin' },
    { id: 'gruvbox-dark', scheme: 'dark', palette: 'gruvbox' },
    { id: 'gruvbox-light', scheme: 'light', palette: 'gruvbox' },
    { id: 'frappe', scheme: 'dark', palette: 'catppuccin' },
    { id: 'latte', scheme: 'light', palette: 'catppuccin' },
    { id: 'solarized-dark', scheme: 'dark', palette: 'solarized' },
    { id: 'solarized-light', scheme: 'light', palette: 'solarized' },
    { id: 'nord', scheme: 'dark', palette: 'nord' },
    { id: 'dracula', scheme: 'dark', palette: 'dracula' },
    { id: 'tokyo-night', scheme: 'dark', palette: 'tokyo-night' },
    { id: 'macchiato', scheme: 'dark', palette: 'macchiato' },
    { id: 'mocha', scheme: 'dark', palette: 'mocha' },
]);

export const PALETTES = Object.freeze([
    { id: 'builtin', variants: Object.freeze({ dark: 'builtin-dark', light: 'builtin-light' }) },
    { id: 'gruvbox', variants: Object.freeze({ dark: 'gruvbox-dark', light: 'gruvbox-light' }) },
    { id: 'catppuccin', variants: Object.freeze({ dark: 'frappe', light: 'latte' }) },
    { id: 'solarized', variants: Object.freeze({ dark: 'solarized-dark', light: 'solarized-light' }) },
    { id: 'nord', variants: Object.freeze({ dark: 'nord' }) },
    { id: 'dracula', variants: Object.freeze({ dark: 'dracula' }) },
    { id: 'tokyo-night', variants: Object.freeze({ dark: 'tokyo-night' }) },
    { id: 'macchiato', variants: Object.freeze({ dark: 'macchiato' }) },
    { id: 'mocha', variants: Object.freeze({ dark: 'mocha' }) },
]);

export const APPEARANCE_PREFERENCE_KEYS = Object.freeze({
    legacyTheme: 'navidrome-theme',
    mode: 'navidrome-theme-mode',
    palette: 'navidrome-theme-palette',
});

export const DEFAULT_MODE = 'system';
export const DEFAULT_PALETTE = 'builtin';
export const DEFAULT_THEME = 'builtin-dark';

const THEMES_BY_ID = new Map(THEMES.map((theme) => [theme.id, theme]));
const PALETTES_BY_ID = new Map(PALETTES.map((palette) => [palette.id, palette]));
const MODES = new Set(THEME_MODES);

export function isKnownTheme(id) {
    return THEMES_BY_ID.has(id);
}

export function isKnownPalette(id) {
    return PALETTES_BY_ID.has(id);
}

export function normalizeMode(mode, fallback = DEFAULT_MODE) {
    return MODES.has(mode) ? mode : fallback;
}

export function themeScheme(id) {
    return THEMES_BY_ID.get(id)?.scheme || THEMES_BY_ID.get(DEFAULT_THEME).scheme;
}

export function themePalette(id) {
    return THEMES_BY_ID.get(id)?.palette || DEFAULT_PALETTE;
}

export function paletteSupportsScheme(paletteId, scheme) {
    return Boolean(PALETTES_BY_ID.get(paletteId)?.variants?.[scheme]);
}

export function paletteTheme(paletteId, scheme) {
    return PALETTES_BY_ID.get(paletteId)?.variants?.[scheme] || null;
}

export function resolveScheme(mode, prefersLight = false) {
    const normalized = normalizeMode(mode);
    if (normalized === 'light' || normalized === 'dark') return normalized;
    return prefersLight ? 'light' : 'dark';
}

export function resolveTheme(id, fallback = DEFAULT_THEME) {
    if (isKnownTheme(id)) return id;
    return isKnownTheme(fallback) ? fallback : DEFAULT_THEME;
}

/**
 * Resolve stored values into the concrete theme consumed by every page.
 *
 * An existing single-value preference is preserved until the user saves the
 * new controls. A palette without a variant for the active scheme remains the
 * selected palette, while the rendered theme temporarily falls back to the
 * built-in palette for that scheme.
 */
export function resolveAppearance({
    mode = null,
    palette = null,
    legacyTheme = null,
} = {}, prefersLight = false) {
    const legacy = isKnownTheme(legacyTheme) ? THEMES_BY_ID.get(legacyTheme) : null;
    const hasModernPreference = MODES.has(mode) || PALETTES_BY_ID.has(palette);
    const resolvedMode = MODES.has(mode)
        ? mode
        : (!hasModernPreference && legacy ? legacy.scheme : DEFAULT_MODE);
    const selectedPalette = PALETTES_BY_ID.has(palette)
        ? palette
        : (!hasModernPreference && legacy ? legacy.palette : DEFAULT_PALETTE);
    const scheme = resolveScheme(resolvedMode, prefersLight);
    const compatible = paletteSupportsScheme(selectedPalette, scheme);
    const appliedPalette = compatible ? selectedPalette : DEFAULT_PALETTE;
    const theme = paletteTheme(appliedPalette, scheme)
        || paletteTheme(DEFAULT_PALETTE, scheme)
        || DEFAULT_THEME;

    return Object.freeze({
        appliedPalette,
        compatible,
        mode: resolvedMode,
        palette: selectedPalette,
        scheme,
        theme,
    });
}
