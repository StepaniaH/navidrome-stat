import assert from 'node:assert/strict';
import test from 'node:test';

import { colorWithAlpha, createThemeTokens } from '../../src/static/js/charts.js';

test('colorWithAlpha normalizes hex and rgb theme colors', () => {
    assert.equal(colorWithAlpha('#fff', 0.52), 'rgba(255, 255, 255, 0.52)');
    assert.equal(
        colorWithAlpha('rgba(24, 34, 48, 0.42)', 0.32),
        'rgba(24, 34, 48, 0.32)',
    );
    assert.equal(colorWithAlpha('rgb(129, 145, 170)', 0.46), 'rgba(129, 145, 170, 0.46)');
});

test('chart tokens use theme surfaces for pie seams and tooltip elevation', () => {
    const previousDocument = globalThis.document;
    const previousGetComputedStyle = globalThis.getComputedStyle;
    const values = new Map([
        ['--surface', '#2e3440'],
        ['--surface-raised', '#374050'],
        ['--border', '#8191aa'],
        ['--overlay', 'rgba(14, 18, 25, 0.7)'],
        ['--text', '#f5f7fb'],
        ['--text-muted', '#d8dee9'],
        ['--text-dim', '#b9c4d4'],
        ...Array.from({ length: 8 }, (_, index) => [
            `--chart-${index + 1}`,
            `#${String(index + 1).repeat(6)}`,
        ]),
    ]);

    globalThis.document = { documentElement: {} };
    globalThis.getComputedStyle = () => ({
        getPropertyValue: (name) => values.get(name) || '',
    });

    try {
        const tokens = createThemeTokens();
        assert.equal(tokens.pieSeparator, 'rgba(46, 52, 64, 0.52)');
        assert.equal(tokens.base.tooltip.borderColor, 'rgba(129, 145, 170, 0.46)');
        assert.equal(tokens.base.tooltip.borderWidth, 1);
        assert.equal(
            tokens.base.tooltip.extraCssText,
            'box-shadow: 0 12px 30px -12px rgba(14, 18, 25, 0.32); border-radius: 8px;',
        );
        assert.equal(tokens.shadow, 'rgba(14, 18, 25, 0.28)');
    } finally {
        if (previousDocument === undefined) delete globalThis.document;
        else globalThis.document = previousDocument;
        if (previousGetComputedStyle === undefined) delete globalThis.getComputedStyle;
        else globalThis.getComputedStyle = previousGetComputedStyle;
    }
});
