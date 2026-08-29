import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
    APPEARANCE_PREFERENCE_KEYS,
    DEFAULT_MODE,
    DEFAULT_PALETTE,
    DEFAULT_THEME,
    PALETTES,
    THEMES,
    THEME_MODES,
    isKnownPalette,
    isKnownTheme,
    normalizeMode,
    paletteTheme,
    resolveAppearance,
    resolveScheme,
    resolveTheme,
    themePalette,
    themeScheme,
} from '../../src/static/js/themes.js';

const themeCss = readFileSync(new URL('../../src/static/themes.css', import.meta.url), 'utf8');

function themeTokenBlock(id) {
    const selectorStart = themeCss.indexOf(`[data-theme="${id}"]`);
    const blockStart = themeCss.indexOf('{', selectorStart);
    return themeCss.slice(blockStart + 1, themeCss.indexOf('}', blockStart));
}

function hexToken(block, token) {
    const value = block.match(new RegExp(`${token}:\\s*(#[\\da-f]{6})`, 'i'))?.[1];
    assert.ok(value, `${token} must be a six-digit hex color for contrast checks`);
    return value;
}

function relativeLuminance(hex) {
    const channels = [1, 3, 5].map((start) => (
        Number.parseInt(hex.slice(start, start + 2), 16) / 255
    ));
    const linear = channels.map((value) => (
        value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
    ));
    return (0.2126 * linear[0]) + (0.7152 * linear[1]) + (0.0722 * linear[2]);
}

function contrastRatio(first, second) {
    const luminances = [relativeLuminance(first), relativeLuminance(second)]
        .sort((left, right) => right - left);
    return (luminances[0] + 0.05) / (luminances[1] + 0.05);
}

test('theme registry has unique ids and valid palette variants', () => {
    const themeIds = THEMES.map(({ id }) => id);
    const paletteIds = PALETTES.map(({ id }) => id);
    const variantIds = new Set();

    assert.equal(new Set(THEME_MODES).size, THEME_MODES.length);
    assert.equal(new Set(themeIds).size, themeIds.length);
    assert.equal(new Set(paletteIds).size, paletteIds.length);
    assert.equal(new Set(Object.values(APPEARANCE_PREFERENCE_KEYS)).size, 4);
    assert.ok(THEME_MODES.includes(DEFAULT_MODE));
    assert.ok(isKnownPalette(DEFAULT_PALETTE));
    assert.ok(isKnownTheme(DEFAULT_THEME));

    for (const theme of THEMES) {
        assert.ok(['dark', 'light'].includes(theme.scheme), `${theme.id} has an invalid scheme`);
        assert.ok(isKnownPalette(theme.palette), `${theme.id} references an unknown palette`);
    }

    for (const palette of PALETTES) {
        const variants = Object.entries(palette.variants);
        assert.ok(variants.length > 0, `${palette.id} has no variants`);
        for (const [scheme, themeId] of variants) {
            assert.ok(['dark', 'light'].includes(scheme), `${palette.id} has an invalid variant scheme`);
            assert.ok(isKnownTheme(themeId), `${palette.id}/${scheme} references an unknown theme`);
            assert.equal(themeScheme(themeId), scheme);
            assert.equal(themePalette(themeId), palette.id);
            assert.equal(variantIds.has(themeId), false, `${themeId} is registered more than once`);
            variantIds.add(themeId);
        }
    }

    assert.deepEqual([...variantIds].sort(), [...themeIds].sort());
});

test('system and builtin are the defaults and follow the system scheme', () => {
    assert.deepEqual(resolveAppearance({}, false), {
        mode: 'system',
        palette: 'builtin',
        scheme: 'dark',
        theme: 'builtin-dark',
    });
    assert.deepEqual(resolveAppearance({}, true), {
        mode: 'system',
        palette: 'builtin',
        scheme: 'light',
        theme: 'builtin-light',
    });
});

test('legacy theme values keep their exact concrete appearance', () => {
    const legacyCases = [
        ['frappe', 'dark', 'catppuccin'],
        ['latte', 'light', 'catppuccin'],
        ['macchiato', 'dark', 'macchiato'],
        ['mocha', 'dark', 'mocha'],
        ['nord', 'dark', 'nord'],
        ['dracula', 'dark', 'dracula'],
        ['tokyo-night', 'dark', 'tokyo-night'],
        ['gruvbox-dark', 'dark', 'gruvbox'],
        ['solarized-dark', 'dark', 'solarized'],
        ['solarized-light', 'light', 'solarized'],
    ];

    for (const [legacyTheme, scheme, palette] of legacyCases) {
        const appearance = resolveAppearance({ legacyTheme }, scheme !== 'light');
        assert.deepEqual(appearance, {
            mode: scheme,
            palette,
            scheme,
            theme: legacyTheme,
        });
    }
});

test('modern mode and palette preferences take precedence over legacy values', () => {
    assert.deepEqual(
        resolveAppearance({ mode: 'dark', palette: 'solarized', legacyTheme: 'latte' }, true),
        {
            mode: 'dark',
            palette: 'solarized',
            scheme: 'dark',
            theme: 'solarized-dark',
        },
    );
    assert.equal(resolveAppearance({ mode: 'light', palette: 'gruvbox' }).theme, 'gruvbox-light');
    assert.equal(resolveAppearance({ mode: 'system', palette: 'catppuccin' }, false).theme, 'frappe');
    assert.equal(resolveAppearance({ mode: 'system', palette: 'catppuccin' }, true).theme, 'latte');
    assert.equal(resolveAppearance({ mode: 'light' }).theme, 'builtin-light');
    assert.equal(resolveAppearance({ palette: 'solarized' }, true).theme, 'solarized-light');
});

test('every palette resolves to a concrete light and dark variant', () => {
    assert.deepEqual(resolveAppearance({ mode: 'light', palette: 'nord' }), {
        mode: 'light',
        palette: 'nord',
        scheme: 'light',
        theme: 'nord-light',
    });
    for (const { id, variants } of PALETTES) {
        assert.ok(variants.dark, `${id} lacks a dark variant`);
        assert.ok(variants.light, `${id} lacks a light variant`);
    }
});

test('invalid values fall back through the public helpers', () => {
    assert.equal(isKnownTheme('unknown'), false);
    assert.equal(isKnownPalette('unknown'), false);
    assert.equal(normalizeMode('unknown'), DEFAULT_MODE);
    assert.equal(normalizeMode('unknown', 'light'), 'light');
    assert.equal(resolveScheme('unknown', true), 'light');
    assert.equal(resolveTheme('unknown'), DEFAULT_THEME);
    assert.equal(resolveTheme('unknown', 'latte'), 'latte');
    assert.equal(themeScheme('unknown'), 'dark');
    assert.equal(themePalette('unknown'), DEFAULT_PALETTE);
    assert.equal(paletteTheme('nord', 'light'), 'nord-light');
    assert.deepEqual(resolveAppearance({
        mode: 'unknown',
        palette: 'unknown',
        legacyTheme: 'unknown',
    }, true), {
        mode: 'system',
        palette: 'builtin',
        scheme: 'light',
        theme: 'builtin-light',
    });
});

test('theme bootstrap reads, applies, and announces the resolved appearance', async () => {
    const stored = new Map([
        [APPEARANCE_PREFERENCE_KEYS.mode, 'system'],
        [APPEARANCE_PREFERENCE_KEYS.palette, 'builtin'],
        ['navidrome-motion', 'reduced'],
    ]);
    const windowListeners = new Map();
    const mediaListeners = new Map();
    const dispatched = [];
    const root = { dataset: {} };
    const mediaQuery = {
        matches: true,
        addEventListener(type, listener) {
            mediaListeners.set(type, listener);
        },
    };
    const previousGlobals = {
        CustomEvent: globalThis.CustomEvent,
        document: globalThis.document,
        window: globalThis.window,
    };

    globalThis.document = { documentElement: root };
    globalThis.CustomEvent = class CustomEvent {
        constructor(type, options = {}) {
            this.type = type;
            this.detail = options.detail;
        }
    };
    globalThis.window = {
        localStorage: {
            getItem(key) {
                return stored.has(key) ? stored.get(key) : null;
            },
        },
        matchMedia(query) {
            assert.equal(query, '(prefers-color-scheme: light)');
            return mediaQuery;
        },
        addEventListener(type, listener) {
            windowListeners.set(type, listener);
        },
        dispatchEvent(event) {
            dispatched.push(event);
            return true;
        },
    };

    try {
        const prefsUrl = new URL('../../src/static/js/prefs.js', import.meta.url).href;
        const themesUrl = new URL('../../src/static/js/themes.js', import.meta.url).href;
        const customizationUrl = new URL(
            '../../src/static/js/theme-customization.js',
            import.meta.url,
        ).href;
        const bootstrapSource = readFileSync(
            new URL('../../src/static/theme-bootstrap.js', import.meta.url),
            'utf8',
        )
            .replace("'./js/prefs.js'", `'${prefsUrl}'`)
            .replace("'./js/themes.js'", `'${themesUrl}'`)
            .replace("'./js/theme-customization.js'", `'${customizationUrl}'`);
        const bootstrap = await import(`data:text/javascript,${encodeURIComponent(bootstrapSource)}`);
        assert.equal(bootstrap.THEME_CHANGE_EVENT, 'navidrome:themechange');
        assert.equal(typeof bootstrap.readStoredAppearance, 'function');
        assert.equal(typeof bootstrap.applyStoredAppearance, 'function');
        assert.deepEqual(root.dataset, {
            motion: 'reduced',
            palette: 'builtin',
            scheme: 'light',
            theme: 'builtin-light',
            themeMode: 'system',
        });
        assert.equal(windowListeners.has('storage'), true);
        assert.equal(mediaListeners.has('change'), true);

        stored.set(APPEARANCE_PREFERENCE_KEYS.mode, 'light');
        stored.set(APPEARANCE_PREFERENCE_KEYS.palette, 'nord');
        const appearance = bootstrap.applyStoredAppearance();
        assert.equal(appearance.palette, 'nord');
        assert.equal(root.dataset.theme, 'nord-light');
        assert.equal(root.dataset.palette, 'nord');
        assert.equal(dispatched.length, 1);
        assert.equal(dispatched[0].type, bootstrap.THEME_CHANGE_EVENT);
        assert.deepEqual(dispatched[0].detail, appearance);
    } finally {
        for (const [name, value] of Object.entries(previousGlobals)) {
            if (value === undefined) delete globalThis[name];
            else globalThis[name] = value;
        }
    }
});

test('every concrete theme exposes the shared semantic and chart token contract', () => {
    const requiredTokens = [
        '--page-bg',
        '--surface',
        '--surface-raised',
        '--field-bg',
        '--field-hover',
        '--border',
        '--border-soft',
        '--text',
        '--text-muted',
        '--text-dim',
        '--accent',
        '--accent-strong',
        '--accent-contrast',
        '--success',
        '--warning',
        '--danger',
        '--shadow',
        '--overlay',
        ...Array.from({ length: 8 }, (_, index) => `--chart-${index + 1}`),
    ];

    for (const { id } of THEMES) {
        const selector = `[data-theme="${id}"]`;
        const selectorStart = themeCss.indexOf(selector);
        assert.notEqual(selectorStart, -1, `${selector} is missing`);
        const blockStart = themeCss.indexOf('{', selectorStart);
        const blockEnd = themeCss.indexOf('}', blockStart);
        const block = themeCss.slice(blockStart, blockEnd);
        for (const token of requiredTokens) {
            assert.ok(block.includes(`${token}:`), `${selector} is missing ${token}`);
        }
    }

    for (const alias of [
        '--accent-soft:',
        '--focus:',
        '--app-bg:',
        '--app-panel:',
        '--app-field:',
        '--app-border:',
        '--app-border-soft:',
        '--app-text:',
        '--app-muted:',
        '--app-dim:',
        '--app-accent:',
        '--app-success:',
        '--app-error:',
        '--page:',
        '--panel:',
        '--field:',
        '--muted:',
        '--dim:',
    ]) {
        assert.ok(themeCss.includes(alias), `${alias} alias is missing`);
    }
    assert.ok(themeCss.includes('--app-on-accent: var(--accent-contrast)'));
});

test('theme text, status, controls, and chart colors keep usable contrast', () => {
    const foregroundTokens = [
        '--text',
        '--text-muted',
        '--text-dim',
        '--accent',
        '--success',
        '--warning',
        '--danger',
    ];
    const backgroundTokens = ['--surface', '--surface-raised', '--field-bg'];

    for (const { id } of THEMES) {
        const block = themeTokenBlock(id);
        for (const foregroundToken of foregroundTokens) {
            for (const backgroundToken of backgroundTokens) {
                const ratio = contrastRatio(
                    hexToken(block, foregroundToken),
                    hexToken(block, backgroundToken),
                );
                assert.ok(
                    ratio >= 4.5,
                    `${id} ${foregroundToken}/${backgroundToken} contrast is ${ratio.toFixed(2)}`,
                );
            }
        }

        const onAccent = contrastRatio(
            hexToken(block, '--accent-contrast'),
            hexToken(block, '--accent'),
        );
        assert.ok(onAccent >= 4.5, `${id} on-accent contrast is ${onAccent.toFixed(2)}`);

        const border = contrastRatio(hexToken(block, '--border'), hexToken(block, '--surface'));
        assert.ok(border >= 3, `${id} border contrast is ${border.toFixed(2)}`);

        for (let index = 1; index <= 8; index += 1) {
            const ratio = contrastRatio(
                hexToken(block, `--chart-${index}`),
                hexToken(block, '--surface'),
            );
            assert.ok(ratio >= 3, `${id} chart-${index} contrast is ${ratio.toFixed(2)}`);
        }
    }
});
