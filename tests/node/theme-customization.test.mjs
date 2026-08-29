import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
    CUSTOM_THEME_FIELDS,
    applyStoredThemeCustomization,
    applyThemeCustomization,
    clearThemeCustomization,
    decodeThemeDocument,
    encodeThemeDocument,
    normalizeHexColor,
    parseThemeCustomizations,
    themeCustomizationFor,
    validateThemeCustomization,
} from '../../src/static/js/theme-customization.js';
import { THEMES } from '../../src/static/js/themes.js';

const themeCss = readFileSync(new URL('../../src/static/themes.css', import.meta.url), 'utf8');

const ACCESSIBLE_COLORS = Object.freeze({
    accent: '#245bb5',
    background: '#f5f7fa',
    field: '#e1e5ef',
    muted: '#465568',
    surface: '#ffffff',
    text: '#182230',
});

function createRoot() {
    const values = new Map();
    return {
        dataset: {},
        style: {
            getPropertyValue(property) {
                return values.get(property) || '';
            },
            removeProperty(property) {
                values.delete(property);
            },
            setProperty(property, value) {
                values.set(property, value);
            },
        },
        values,
    };
}

test('custom theme documents keep only complete known-theme color sets', () => {
    const customizations = parseThemeCustomizations(JSON.stringify({
        schemaVersion: 1,
        overrides: {
            'nord-light': ACCESSIBLE_COLORS,
            unknown: ACCESSIBLE_COLORS,
            mocha: { ...ACCESSIBLE_COLORS, accent: 'red' },
            nord: { ...ACCESSIBLE_COLORS, text: '#ffffff' },
        },
    }));

    assert.deepEqual(Object.keys(customizations.overrides), ['nord-light']);
    assert.deepEqual(themeCustomizationFor('nord-light', customizations), ACCESSIBLE_COLORS);
    assert.equal(themeCustomizationFor('mocha', customizations), null);
    assert.deepEqual(parseThemeCustomizations('{broken'), { schemaVersion: 1, overrides: {} });
    assert.deepEqual(parseThemeCustomizations({ schemaVersion: 99, overrides: {} }), {
        schemaVersion: 1,
        overrides: {},
    });
});

test('hex values normalize to a strict six-digit contract', () => {
    assert.equal(normalizeHexColor('#ABC'), '#aabbcc');
    assert.equal(normalizeHexColor(' #A1b2C3 '), '#a1b2c3');
    assert.equal(normalizeHexColor('rgb(1, 2, 3)'), null);
    assert.equal(normalizeHexColor('url(https://example.invalid)'), null);
});

test('custom theme contrast validation rejects unreadable critical colors', () => {
    const accessible = validateThemeCustomization(ACCESSIBLE_COLORS);
    assert.deepEqual(accessible.colors, ACCESSIBLE_COLORS);
    assert.deepEqual(accessible.issues, []);
    assert.equal(accessible.valid, true);
    assert.equal(accessible.checks.length, 9);
    assert.ok(accessible.checks.every((check) => check.pass && check.minimum === 4.5));
    const invalid = validateThemeCustomization({
        ...ACCESSIBLE_COLORS,
        text: '#f4f4f4',
    });
    assert.equal(invalid.valid, false);
    assert.ok(invalid.issues.includes('text:surface'));
});

test('single-theme documents round-trip through a strict versioned format', () => {
    const encoded = encodeThemeDocument('nord-light', ACCESSIBLE_COLORS);
    const decoded = decodeThemeDocument(encoded, 'nord-light');
    assert.equal(decoded.valid, true);
    assert.equal(decoded.theme, 'nord-light');
    assert.deepEqual(decoded.colors, ACCESSIBLE_COLORS);
});

test('theme document imports reject mismatches and unknown fields', () => {
    const encoded = encodeThemeDocument('nord-light', ACCESSIBLE_COLORS);
    assert.equal(decodeThemeDocument(encoded, 'builtin-light').error, 'theme_mismatch');
    const document = JSON.parse(encoded);
    document.unexpected = true;
    assert.equal(decodeThemeDocument(document, 'nord-light').error, 'invalid_document');
    const nestedDocument = JSON.parse(encoded);
    nestedDocument.colors.unexpected = '#000000';
    assert.equal(decodeThemeDocument(nestedDocument, 'nord-light').error, 'invalid_colors');
    assert.equal(decodeThemeDocument('{broken', 'nord-light').error, 'invalid_json');
});

test('every preset can seed a valid advanced-editor draft', () => {
    const tokenByField = {
        accent: '--accent',
        background: '--page-bg',
        field: '--field-bg',
        muted: '--text-muted',
        surface: '--surface',
        text: '--text',
    };
    for (const { id } of THEMES) {
        const selectorStart = themeCss.indexOf(`[data-theme="${id}"]`);
        const blockStart = themeCss.indexOf('{', selectorStart);
        const block = themeCss.slice(blockStart + 1, themeCss.indexOf('}', blockStart));
        const colors = Object.fromEntries(Object.entries(tokenByField).map(([field, token]) => [
            field,
            block.match(new RegExp(`${token}:\\s*(#[\\da-f]{6})`, 'i'))?.[1],
        ]));
        const validation = validateThemeCustomization(colors);
        assert.equal(validation.valid, true, `${id}: ${validation.issues.join(', ')}`);
    }
});

test('applying a customization owns only its declared semantic properties', () => {
    const root = createRoot();
    root.style.setProperty('--unrelated', '#123456');
    const result = applyThemeCustomization(root, 'nord-light', ACCESSIBLE_COLORS);

    assert.equal(result.applied, true);
    for (const { key, property } of CUSTOM_THEME_FIELDS) {
        assert.equal(root.style.getPropertyValue(property), ACCESSIBLE_COLORS[key]);
    }
    assert.equal(root.style.getPropertyValue('--chart-1'), ACCESSIBLE_COLORS.accent);
    assert.equal(root.style.getPropertyValue('--accent-contrast'), '#ffffff');
    assert.match(root.dataset.themeCustomization, /^nord-light:/);

    clearThemeCustomization(root);
    assert.equal(root.style.getPropertyValue('--page-bg'), '');
    assert.equal(root.style.getPropertyValue('--unrelated'), '#123456');
    assert.equal('themeCustomization' in root.dataset, false);
});

test('stored customization applies only to the requested concrete theme', () => {
    const customizations = parseThemeCustomizations({
        schemaVersion: 1,
        overrides: { 'nord-light': ACCESSIBLE_COLORS },
    });
    const root = createRoot();

    assert.equal(applyStoredThemeCustomization(root, 'nord', customizations).applied, false);
    assert.equal(applyStoredThemeCustomization(root, 'nord-light', customizations).applied, true);
});
