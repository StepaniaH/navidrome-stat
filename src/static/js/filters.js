/**
 * Dashboard filter state with URL persistence.
 *
 * Filters survive reloads and are shareable through query parameters whose
 * names match the statistics API. Unknown values fall back to defaults.
 */

import { validateCustomRange } from './format.js';

const KEYS = ['days', 'timezone', 'metric', 'sourceId', 'username', 'startDate', 'endDate'];
const PARAM_ALIASES = {
    days: 'days',
    timezone: 'timezone',
    metric: 'metric',
    sourceId: 'source_id',
    username: 'username',
    startDate: 'start_date',
    endDate: 'end_date',
};

const DEFAULTS = Object.freeze({
    days: 30,
    timezone: 'browser',
    metric: 'plays',
    sourceId: '',
    username: '',
    startDate: '',
    endDate: '',
});

const listeners = new Set();

export const allowedTimezones = Object.freeze(['browser', 'UTC']);

function sanitize(candidate) {
    const filters = { ...DEFAULTS };

    if (Number.isFinite(Number(candidate.days))) {
        const days = Number(candidate.days);
        if (days >= 0 && days <= 3650) filters.days = days;
    }
    if (allowedTimezones.includes(candidate.timezone)) {
        filters.timezone = candidate.timezone;
    } else if (candidate.timezone) {
        filters.timezone = candidate.timezone; // IANA names pass through
    }
    if (candidate.metric === 'plays' || candidate.metric === 'listen_time') {
        filters.metric = candidate.metric;
    }
    if (typeof candidate.sourceId === 'string' && candidate.sourceId.length <= 128) {
        filters.sourceId = candidate.sourceId;
    }
    if (typeof candidate.username === 'string' && candidate.username.length <= 128) {
        filters.username = candidate.username;
    }
    if (candidate.startDate && candidate.endDate) {
        const range = validateCustomRange(candidate.startDate, candidate.endDate);
        if (range.ok) {
            filters.startDate = candidate.startDate;
            filters.endDate = candidate.endDate;
        }
    }
    return filters;
}

function fromUrl() {
    const params = new URLSearchParams(window.location.search);
    const candidate = {};
    for (const [key, param] of Object.entries(PARAM_ALIASES)) {
        candidate[key] = params.get(param) ?? '';
    }
    if (params.has('days')) candidate.days = Number(params.get('days'));
    else delete candidate.days;
    return sanitize(candidate);
}

let current = fromUrl();

function toUrl(filters) {
    const params = new URLSearchParams();
    for (const [key, param] of Object.entries(PARAM_ALIASES)) {
        const value = String(filters[key]);
        if (value && !(key === 'days' && value === String(DEFAULTS.days))) {
            params.set(param, value);
        }
    }
    const query = params.toString();
    return `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`;
}

export function getFilters() {
    return { ...current };
}

export function setFilters(patch) {
    current = sanitize({ ...current, ...patch });
    window.history.replaceState(null, '', toUrl(current));
    listeners.forEach((listener) => listener(getFilters()));
    return getFilters();
}

export function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
}
