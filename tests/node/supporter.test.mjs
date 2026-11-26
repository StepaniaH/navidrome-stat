import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import { LOCALE_CODES } from '../../src/static/js/locales.js';
import {
    SUPPORT_URL,
    supportUrl,
} from '../../src/static/js/supporter-ui.js';

const THEMES_CSS_PATH = path.resolve('src/static/themes.css');
const REQUIRED_SUPPORTER_TOKENS = [
    '--sup-hi',
    '--sup-main',
    '--sup-sec',
    '--sup-glow',
    '--sup-ink',
    '--sup-since',
];

function extractThemeBlocks(css) {
    const blocks = [];
    const headerRe = /\[data-theme="([^"]+)"\]\s*\{([^}]+)\}/g;
    let match;
    while ((match = headerRe.exec(css)) !== null) {
        blocks.push({ theme: match[1], body: match[2] });
    }
    return blocks;
}

test('supportUrl localizes valid UI locales and sanitizes untrusted values', () => {
    for (const code of LOCALE_CODES) {
        const expected = `https://navidrome-stat.stepaniah.me/?lang=${encodeURIComponent(code)}#support`;
        assert.equal(supportUrl(code), expected);
    }

    for (const fallbackInput of ['', 'auto', null, undefined, 'en-GB', 'xx-unknown', '../x', 'zh-CN#foo']) {
        assert.equal(supportUrl(fallbackInput), SUPPORT_URL);
    }
});

test('all 18 theme blocks define valid six-digit hex --sup-* palette tokens', () => {
    const css = fs.readFileSync(THEMES_CSS_PATH, 'utf8');
    const blocks = extractThemeBlocks(css);
    assert.equal(blocks.length, 18, `expected 18 [data-theme] blocks, found ${blocks.length}`);

    for (const { theme, body } of blocks) {
        for (const token of REQUIRED_SUPPORTER_TOKENS) {
            const match = body.match(new RegExp(`${token}:\\s*([^;]+);`));
            assert.ok(match, `Theme "${theme}" is missing ${token}`);
            assert.match(
                match[1].trim(),
                /^#[0-9a-fA-F]{6}$/,
                `Theme "${theme}" token ${token} must be a 6-digit hex color, got "${match[1].trim()}"`,
            );
        }
    }
});
