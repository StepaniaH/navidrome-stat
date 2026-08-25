/**
 * Application metadata from `/api/about`.
 *
 * The backend serves the released version so frontend files never hardcode
 * one. Failed lookups stay silent and are retried on the next call.
 */

import { apiFetch } from './http.js';

let appInfoPromise = null;

function fetchAppInfo() {
    if (!appInfoPromise) {
        appInfoPromise = apiFetch('/api/about')
            .then((response) => {
                if (!response.ok) {
                    appInfoPromise = null;
                    return null;
                }
                return response.json();
            })
            .catch(() => {
                appInfoPromise = null;
                return null;
            });
    }
    return appInfoPromise;
}

async function applyAppVersion() {
    const info = await fetchAppInfo();
    if (!info || !info.version) return;
    document.querySelectorAll('[data-app-version]').forEach((element) => {
        element.textContent = `v${info.version}`;
    });
}

export { fetchAppInfo, applyAppVersion };
