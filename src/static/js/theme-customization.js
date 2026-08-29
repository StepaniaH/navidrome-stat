import { readPreference, writePreference } from './prefs.js';
import { APPEARANCE_PREFERENCE_KEYS, isKnownTheme } from './themes.js';

export const THEME_CUSTOMIZATION_SCHEMA_VERSION = 1;
export const THEME_DOCUMENT_SCHEMA_VERSION = 1;

export const CUSTOM_THEME_FIELDS = Object.freeze([
    Object.freeze({ key: 'background', property: '--page-bg' }),
    Object.freeze({ key: 'surface', property: '--surface' }),
    Object.freeze({ key: 'field', property: '--field-bg' }),
    Object.freeze({ key: 'text', property: '--text' }),
    Object.freeze({ key: 'muted', property: '--text-muted' }),
    Object.freeze({ key: 'accent', property: '--accent' }),
]);

const DERIVED_PROPERTIES = Object.freeze([
    '--accent-contrast',
    '--accent-strong',
    '--chart-1',
]);

const OWNED_PROPERTIES = Object.freeze([
    ...CUSTOM_THEME_FIELDS.map(({ property }) => property),
    ...DERIVED_PROPERTIES,
]);

function emptyDocument() {
    return { schemaVersion: THEME_CUSTOMIZATION_SCHEMA_VERSION, overrides: {} };
}

export function normalizeHexColor(value) {
    const normalized = String(value || '').trim().toLowerCase();
    if (/^#[\da-f]{6}$/.test(normalized)) return normalized;
    if (/^#[\da-f]{3}$/.test(normalized)) {
        return `#${[...normalized.slice(1)].map((digit) => `${digit}${digit}`).join('')}`;
    }
    return null;
}

function normalizeColors(input) {
    if (!input || typeof input !== 'object' || Array.isArray(input)) return null;
    const colors = {};
    for (const { key } of CUSTOM_THEME_FIELDS) {
        const color = normalizeHexColor(input[key]);
        if (!color) return null;
        colors[key] = color;
    }
    return colors;
}

export function parseThemeCustomizations(raw) {
    let parsed = raw;
    if (typeof raw === 'string') {
        try {
            parsed = JSON.parse(raw);
        } catch (_error) {
            return emptyDocument();
        }
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return emptyDocument();
    if (parsed.schemaVersion !== THEME_CUSTOMIZATION_SCHEMA_VERSION) return emptyDocument();
    if (!parsed.overrides || typeof parsed.overrides !== 'object' || Array.isArray(parsed.overrides)) {
        return emptyDocument();
    }

    const overrides = {};
    for (const [themeId, input] of Object.entries(parsed.overrides)) {
        if (!isKnownTheme(themeId)) continue;
        const validation = validateThemeCustomization(input);
        if (validation.valid) overrides[themeId] = validation.colors;
    }
    return { schemaVersion: THEME_CUSTOMIZATION_SCHEMA_VERSION, overrides };
}

export function readThemeCustomizations(raw = readPreference(APPEARANCE_PREFERENCE_KEYS.customization)) {
    return parseThemeCustomizations(raw);
}

export function themeCustomizationFor(themeId, customizations = readThemeCustomizations()) {
    return customizations.overrides[themeId] || null;
}

function withThemeCustomization(themeId, colors, customizations = readThemeCustomizations()) {
    const overrides = { ...customizations.overrides };
    const normalized = normalizeColors(colors);
    if (normalized) overrides[themeId] = normalized;
    else delete overrides[themeId];
    return { schemaVersion: THEME_CUSTOMIZATION_SCHEMA_VERSION, overrides };
}

export function saveThemeCustomization(themeId, colors) {
    if (!isKnownTheme(themeId) || !validateThemeCustomization(colors).valid) return false;
    return writePreference(
        APPEARANCE_PREFERENCE_KEYS.customization,
        JSON.stringify(withThemeCustomization(themeId, colors)),
    );
}

export function removeThemeCustomization(themeId) {
    if (!isKnownTheme(themeId)) return false;
    return writePreference(
        APPEARANCE_PREFERENCE_KEYS.customization,
        JSON.stringify(withThemeCustomization(themeId, null)),
    );
}

function colorChannels(hex) {
    return [1, 3, 5].map((start) => Number.parseInt(hex.slice(start, start + 2), 16));
}

function relativeLuminance(hex) {
    const linear = colorChannels(hex).map((channel) => {
        const value = channel / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return (0.2126 * linear[0]) + (0.7152 * linear[1]) + (0.0722 * linear[2]);
}

export function contrastRatio(first, second) {
    const values = [relativeLuminance(first), relativeLuminance(second)]
        .sort((left, right) => right - left);
    return (values[0] + 0.05) / (values[1] + 0.05);
}

function mixHex(first, second, secondWeight) {
    const mixed = colorChannels(first).map((channel, index) => (
        Math.round((channel * (1 - secondWeight)) + (colorChannels(second)[index] * secondWeight))
    ));
    return `#${mixed.map((channel) => channel.toString(16).padStart(2, '0')).join('')}`;
}

function accentContrast(accent) {
    const dark = '#111827';
    const light = '#ffffff';
    return contrastRatio(accent, dark) >= contrastRatio(accent, light) ? dark : light;
}

export function validateThemeCustomization(input) {
    const colors = normalizeColors(input);
    if (!colors) return { checks: [], colors: null, issues: ['format'], valid: false };

    const issues = [];
    const checks = [];
    for (const foreground of ['text', 'muted', 'accent']) {
        for (const background of ['background', 'surface', 'field']) {
            const ratio = contrastRatio(colors[foreground], colors[background]);
            const pass = ratio >= 4.5;
            checks.push({ background, foreground, minimum: 4.5, pass, ratio });
            if (!pass) {
                issues.push(`${foreground}:${background}`);
            }
        }
    }
    return { checks, colors, issues, valid: issues.length === 0 };
}

export function encodeThemeDocument(themeId, colors) {
    const validation = validateThemeCustomization(colors);
    if (!isKnownTheme(themeId) || !validation.valid) return null;
    return JSON.stringify({
        schemaVersion: THEME_DOCUMENT_SCHEMA_VERSION,
        theme: themeId,
        colors: validation.colors,
    }, null, 2);
}

export function decodeThemeDocument(raw, expectedThemeId) {
    let parsed;
    try {
        parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    } catch (_error) {
        return { error: 'invalid_json', valid: false };
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return { error: 'invalid_document', valid: false };
    }
    const rootKeys = Object.keys(parsed).sort();
    if (rootKeys.join(',') !== 'colors,schemaVersion,theme') {
        return { error: 'invalid_document', valid: false };
    }
    if (parsed.schemaVersion !== THEME_DOCUMENT_SCHEMA_VERSION) {
        return { error: 'unsupported_version', valid: false };
    }
    if (!isKnownTheme(parsed.theme) || parsed.theme !== expectedThemeId) {
        return { error: 'theme_mismatch', valid: false };
    }
    const colorKeys = parsed.colors && typeof parsed.colors === 'object'
        ? Object.keys(parsed.colors).sort()
        : [];
    const expectedColorKeys = CUSTOM_THEME_FIELDS.map(({ key }) => key).sort();
    if (colorKeys.join(',') !== expectedColorKeys.join(',')) {
        return { error: 'invalid_colors', valid: false };
    }
    const validation = validateThemeCustomization(parsed.colors);
    if (!validation.colors) return { error: 'invalid_colors', ...validation };
    if (!validation.valid) return { error: 'low_contrast', ...validation };
    return { error: null, theme: parsed.theme, ...validation };
}

function fingerprint(themeId, colors) {
    const source = `${themeId}:${CUSTOM_THEME_FIELDS.map(({ key }) => colors[key]).join(':')}`;
    let hash = 5381;
    for (const character of source) hash = ((hash * 33) ^ character.charCodeAt(0)) >>> 0;
    return `${themeId}:${hash.toString(36)}`;
}

export function clearThemeCustomization(root = document.documentElement) {
    if (root?.style?.removeProperty) {
        for (const property of OWNED_PROPERTIES) root.style.removeProperty(property);
    }
    if (root?.dataset) delete root.dataset.themeCustomization;
}

export function applyThemeCustomization(root, themeId, input) {
    clearThemeCustomization(root);
    const colors = normalizeColors(input);
    if (!colors || !root?.style?.setProperty) return { applied: false, colors: null };

    for (const { key, property } of CUSTOM_THEME_FIELDS) {
        root.style.setProperty(property, colors[key]);
    }
    root.style.setProperty('--accent-contrast', accentContrast(colors.accent));
    root.style.setProperty('--accent-strong', mixHex(colors.accent, colors.text, 0.2));
    root.style.setProperty('--chart-1', colors.accent);
    if (root.dataset) root.dataset.themeCustomization = fingerprint(themeId, colors);
    return { applied: true, colors };
}

export function applyStoredThemeCustomization(
    root,
    themeId,
    customizations = readThemeCustomizations(),
) {
    return applyThemeCustomization(root, themeId, themeCustomizationFor(themeId, customizations));
}
