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

/**
 * Build the dashboard statistics query string. `filters` uses camelCase keys;
 * empty source ids and missing custom ranges are omitted.
 */
export function buildStatsQuery(filters) {
    const params = new URLSearchParams();
    params.set('days', String(filters.days));
    params.set('timezone', filters.timezone);
    params.set('metric', filters.metric);
    if (filters.sourceId) params.set('source_id', filters.sourceId);
    if (filters.startDate && filters.endDate) {
        params.set('start_date', filters.startDate);
        params.set('end_date', filters.endDate);
    }
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
