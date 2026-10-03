import { readPreference } from './prefs.js';

export const DAILY_AVERAGE_KEY = 'navidrome-daily-average-mode';

export function dailyAverageMode() {
    return readPreference(DAILY_AVERAGE_KEY, 'calendar') === 'active' ? 'active' : 'calendar';
}

export function dailyAverage(summary, mode = dailyAverageMode()) {
    const value = summary[`average_${mode}_daily_plays`];
    return Number.isFinite(value) ? value : summary.average_daily_plays;
}
