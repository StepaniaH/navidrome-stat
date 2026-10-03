/**
 * Pure formatting, query-building and validation helpers.
 *
 * Everything here is side-effect free so node --test can exercise it
 * directly; locale strings arrive via an injectable translate function.
 */

export function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function formatChangeText(pct, { compareLabel }) {
    if (pct === null || pct === undefined || !Number.isFinite(pct)) {
        return '';
    }
    const sign = pct > 0 ? '↑' : (pct < 0 ? '↓' : '·');
    const absVal = Math.abs(pct).toFixed(1).replace(/\.0$/, '');
    return `${sign} ${absVal}% ${compareLabel}`;
}

function statsScopeParams(filters) {
    const params = new URLSearchParams();
    params.set('days', String(filters.days));
    params.set('timezone', filters.timezone);
    if (filters.sourceId) params.set('source_id', filters.sourceId);
    if (filters.username) params.set('username', filters.username);
    if (filters.startDate && filters.endDate) {
        params.set('start_date', filters.startDate);
        params.set('end_date', filters.endDate);
    }
    return params;
}

/** Build a query for endpoints that share the dashboard's current scope. */
export function buildStatsScopeQuery(filters) {
    return statsScopeParams(filters).toString();
}

/**
 * Build the dashboard statistics query string. `filters` uses camelCase keys;
 * empty source ids and missing custom ranges are omitted.
 */
export function buildStatsQuery(filters) {
    const params = statsScopeParams(filters);
    params.set('metric', filters.metric);
    if (filters.artistMode) params.set('artist_mode', filters.artistMode);
    return params.toString();
}

/** Validate a custom local-date range; returns a message key on failure. */
export function validateCustomRange(start, end) {
    if (!start || !end) return { ok: false, reason: 'range.missing' };
    if (start > end) return { ok: false, reason: 'range.order' };
    const startValue = new Date(`${start}T00:00:00`);
    const endValue = new Date(`${end}T00:00:00`);
    const rangeDays = Math.round((endValue - startValue) / 86400000) + 1;
    if (rangeDays > 366) return { ok: false, reason: 'range.tooLong' };
    return { ok: true };
}

/** URL of the authenticated cover art proxy for one item. */
export function coverArtUrl({ sourceId, id, size = 300 }) {
    const params = new URLSearchParams({
        source_id: sourceId,
        id,
        size: String(size),
    });
    return `/api/coverart?${params.toString()}`;
}

/** Resolve a legacy album cover only when its image is loaded. */
export function albumCoverUrl({ sourceId, album, artist = '', size = 300 }) {
    const params = new URLSearchParams({ source_id: sourceId, album, size: String(size) });
    if (artist) params.set('artist', artist);
    return `/api/stats/album-cover?${params}`;
}

/** Open an artist or source-qualified album within the selected statistics scope. */
export function entityDetailUrl({ type, name, id = '', sourceId = '', artist = '' }, scope) {
    if (!['artist', 'album'].includes(type) || !name || name.length > 512
        || (type === 'album' && !sourceId) || sourceId.length > 128
        || id.length > 128 || artist.length > 512) return null;
    const params = new URLSearchParams(buildStatsScopeQuery(scope));
    if (scope.artistMode) params.set('artist_mode', scope.artistMode);
    params.set('entity_type', type);
    params.set('entity_name', name);
    if (id) params.set('entity_id', id);
    if (sourceId) params.set('entity_source_id', sourceId);
    if (artist) params.set('entity_artist', artist);
    return `/?${params}`;
}

/** Localized listening duration (hours/minutes/seconds buckets). */
export function formatDuration(seconds, t) {
    const total = Number(seconds) || 0;
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = Math.floor(total % 60);
    if (hours > 0) return t('duration.hours', { hours, minutes });
    if (minutes > 0) return t('duration.minutes', { minutes });
    return t('duration.seconds', { seconds: secs });
}

/** Localized listening duration rounded to the nearest second. */
export function formatPreciseDuration(seconds, t) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    if (hours > 0) {
        return t('duration.hoursMinutesSeconds', { hours, minutes, seconds: secs });
    }
    if (minutes > 0) return t('duration.minutesSeconds', { minutes, seconds: secs });
    return t('duration.seconds', { seconds: secs });
}

/** Localized stored duration, retaining non-zero seconds without trailing zeroes. */
export function formatRecordedDuration(seconds, t) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    return total >= 60 && total % 60 !== 0
        ? formatPreciseDuration(total, t)
        : formatDuration(total, t);
}
