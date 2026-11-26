/**
 * Application metadata from `/api/about`.
 *
 * The backend serves the released version and non-sensitive supporter summary
 * so frontend files never hardcode one. Failed lookups stay silent and are
 * retried on the next call.
 */

import { apiFetch } from './http.js';

export const SUPPORTER_SYNC_STORAGE_KEY = 'navidrome-supporter-sync';

let appInfoPromise = null;
let cachedAppInfo = null;
let appInfoGeneration = 0;

function fetchAppInfo({ force = false } = {}) {
    if (force) {
        appInfoGeneration += 1;
        appInfoPromise = null;
    }
    if (!appInfoPromise) {
        const reqGen = ++appInfoGeneration;
        appInfoPromise = apiFetch('/api/about')
            .then((response) => {
                if (!response.ok) {
                    if (reqGen === appInfoGeneration) appInfoPromise = null;
                    return cachedAppInfo;
                }
                return response.json();
            })
            .then((info) => {
                if (reqGen !== appInfoGeneration) {
                    return cachedAppInfo;
                }
                if (info) cachedAppInfo = info;
                return info;
            })
            .catch(() => {
                if (reqGen === appInfoGeneration) appInfoPromise = null;
                return cachedAppInfo;
            });
    }
    return appInfoPromise;
}

function invalidateAppInfo() {
    appInfoGeneration += 1;
    appInfoPromise = null;
    cachedAppInfo = null;
}

function updateCachedSupporter(summary) {
    if (!summary || typeof summary !== 'object') return;
    appInfoGeneration += 1;
    const nextSupporter = {
        active: Boolean(summary.active),
        tier: summary.tier || null,
        issued_at: summary.issued_at || null,
        show_in_header: summary.show_in_header !== false,
    };
    if (cachedAppInfo) {
        cachedAppInfo = {
            ...cachedAppInfo,
            supporter: nextSupporter,
        };
        appInfoPromise = Promise.resolve(cachedAppInfo);
    } else {
        appInfoPromise = null;
    }
    try {
        localStorage.setItem(
            SUPPORTER_SYNC_STORAGE_KEY,
            JSON.stringify({ ...nextSupporter, ts: Date.now() }),
        );
    } catch (_error) {
        // Ignore storage quota / private-mode restrictions.
    }
}

async function applyAppVersion({ force = false } = {}) {
    const info = await fetchAppInfo({ force });
    if (!info) return null;
    if (info.version) {
        document.querySelectorAll('[data-app-version]').forEach((element) => {
            element.textContent = `v${info.version}`;
        });
    }
    return info;
}

export {
    fetchAppInfo,
    applyAppVersion,
    invalidateAppInfo,
    updateCachedSupporter,
};
