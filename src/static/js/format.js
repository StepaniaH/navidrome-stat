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
