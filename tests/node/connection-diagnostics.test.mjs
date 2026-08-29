import assert from 'node:assert/strict';
import test from 'node:test';

import {
    connectionTestMessageKey,
} from '../../src/static/js/settings/connection-diagnostics.js';

test('connection tests translate stable categories without raw server text', () => {
    assert.equal(connectionTestMessageKey('ok', true), 'source.testSuccess');
    assert.equal(
        connectionTestMessageKey('auth_failed'),
        'source.diagnostics.auth_failed.title',
    );
    assert.equal(
        connectionTestMessageKey('incomplete'),
        'source.diagnostics.unconfigured.title',
    );
    assert.equal(
        connectionTestMessageKey('synthetic secret detail'),
        'source.diagnostics.unknown.title',
    );
});
