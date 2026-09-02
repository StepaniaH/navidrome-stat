/**
 * Dashboard filter state with URL persistence.
 *
 * Filters survive reloads and are shareable through query parameters whose
 * names match the statistics API. Unknown values fall back to defaults.
 */

import { validateCustomRange } from './format.js';
import { readPreference } from './prefs.js';

const KEYS = [
    'days', 'timezone', 'metric', 'sourceId', 'username', 'startDate', 'endDate',
    'relationDimension', 'artistMode',
    'entityType', 'entityName', 'entityId', 'entitySourceId', 'entityArtist',
];
const PARAM_ALIASES = {
    days: 'days',
    timezone: 'timezone',
    metric: 'metric',
    sourceId: 'source_id',
    username: 'username',
    startDate: 'start_date',
    endDate: 'end_date',
    relationDimension: 'relation',
    artistMode: 'artist_mode',
    entityType: 'entity_type',
    entityName: 'entity_name',
    entityId: 'entity_id',
    entitySourceId: 'entity_source_id',
    entityArtist: 'entity_artist',
};

const DEFAULTS = Object.freeze({
    days: 30,
    timezone: 'browser',
    metric: 'plays',
    sourceId: '',
    username: '',
    startDate: '',
    endDate: '',
    relationDimension: 'artist',
    artistMode: 'combined',
    entityType: '',
    entityName: '',
    entityId: '',
    entitySourceId: '',
    entityArtist: '',
});

const listeners = new Set();

export const allowedTimezones = Object.freeze(['browser', 'UTC']);

function sanitize(candidate) {
    const filters = { ...DEFAULTS };
    if (candidate.artistMode === 'separate') filters.artistMode = 'separate';

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
    if (
        candidate.relationDimension === 'artist'
        || candidate.relationDimension === 'album'
        || candidate.relationDimension === 'client'
    ) {
        filters.relationDimension = candidate.relationDimension;
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
    const hasValidEntitySource = (
        typeof candidate.entitySourceId === 'string'
        && candidate.entitySourceId.length > 0
        && candidate.entitySourceId.length <= 128
    );
    if (
        (
            candidate.entityType === 'artist'
            || candidate.entityType === 'album'
        )
        && typeof candidate.entityName === 'string'
        && candidate.entityName.length > 0
        && candidate.entityName.length <= 512
        && (candidate.entityType !== 'album' || hasValidEntitySource)
    ) {
        filters.entityType = candidate.entityType;
        filters.entityName = candidate.entityName;
        if (typeof candidate.entityId === 'string' && candidate.entityId.length <= 128) {
            filters.entityId = candidate.entityId;
        }
        if (hasValidEntitySource) {
            filters.entitySourceId = candidate.entitySourceId;
        }
        if (
            typeof candidate.entityArtist === 'string'
            && candidate.entityArtist.length <= 512
        ) {
            filters.entityArtist = candidate.entityArtist;
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
    if (!params.has('artist_mode')) {
        candidate.artistMode = readPreference('navidrome-artist-mode', 'combined');
    }
    return sanitize(candidate);
}

let current = fromUrl();

function toUrl(filters) {
    const params = new URLSearchParams();
    for (const [key, param] of Object.entries(PARAM_ALIASES)) {
        const value = String(filters[key]);
        const isDefault = (
            (key === 'days' && value === String(DEFAULTS.days))
            || (key === 'relationDimension' && value === DEFAULTS.relationDimension)
        );
        if (value && !isDefault) {
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
    window.history.replaceState(window.history.state ?? null, '', toUrl(current));
    listeners.forEach((listener) => listener(getFilters()));
    return getFilters();
}

export function pushFilters(patch) {
    current = sanitize({ ...current, ...patch });
    window.history.pushState(
        { ...(window.history.state || {}), navidromeEntityDetail: true },
        '',
        toUrl(current),
    );
    listeners.forEach((listener) => listener(getFilters()));
    return getFilters();
}

export function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

window.addEventListener('popstate', () => {
    current = fromUrl();
    listeners.forEach((listener) => listener(getFilters()));
});
