import { apiFetch, isAbortError } from './http.js';
import { createLoginController } from './auth.js';
import { UNAUTHORIZED_EVENT } from './http.js';
import { readPreference } from './prefs.js';
import { createI18n } from '../localization.js';
import { pageMessages } from './i18n/index.js';
import { createThemeTokens } from './charts.js';
import { formatDuration } from './format.js';
import { createListbox } from './listbox.js';
import { THEME_CHANGE_EVENT } from '../theme-bootstrap.js';

const i18n = createI18n({ messages: pageMessages('dashboard', 'review'), fallbackLocale: 'en' });
const t = (key, values) => i18n.t(key, values);
const num = (value) => i18n.formatNumber(value);

let browserTimezone = null;
try {
    browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
} catch (_error) {
    browserTimezone = null;
}
function resolveTimezone() {
    const requested = new URLSearchParams(window.location.search).get('timezone');
    if (requested) return requested === 'browser' ? (browserTimezone || 'UTC') : requested;
    const saved = readPreference('navidrome-timezone', 'browser');
    if (saved === 'browser' || saved === 'UTC') return saved === 'browser' ? (browserTimezone || 'UTC') : saved;
    return saved || 'UTC';
}

const REVIEW_YEAR_MIN = 1970;
const REVIEW_YEAR_MAX = 2075;

function initialReviewYear() {
    const requested = Number(new URLSearchParams(window.location.search).get('year'));
    if (Number.isInteger(requested) && requested >= REVIEW_YEAR_MIN && requested <= REVIEW_YEAR_MAX) {
        return requested;
    }
    return Math.min(REVIEW_YEAR_MAX, Math.max(REVIEW_YEAR_MIN, new Date().getFullYear()));
}

let monthlyChart = null;
let hourlyChart = null;
let weekdayChart = null;
let currentYear = initialReviewYear();
let reviewRequestController = null;
let reviewRequestGeneration = 0;

function initCharts() {
    const mount = (id) => echarts.init(document.getElementById(id), null, { renderer: 'canvas' });
    monthlyChart = mount('reviewMonthlyChart');
    hourlyChart = mount('reviewHourlyChart');
    weekdayChart = mount('reviewWeekdayChart');
}

function barOption(categories, values, { horizontal = false, categoryInterval = 0, seriesName = '', valueFormatter = null } = {}) {
    const theme = createThemeTokens();
    const base = theme.base;
    const categoryAxis = {
        type: 'category',
        data: categories,
        axisLine: { lineStyle: { color: theme.axisLine } },
        axisLabel: {
            color: theme.axisText,
            fontSize: 11,
            hideOverlap: true,
            interval: categoryInterval,
        },
        axisTick: { show: false },
    };
    const valueAxis = {
        type: 'value',
        axisLabel: { color: theme.axisText, fontSize: 11, hideOverlap: true },
        splitLine: { lineStyle: { color: theme.gridLine } },
    };
    return {
        ...base,
        tooltip: {
            ...base.tooltip,
            trigger: 'axis',
            ...(valueFormatter ? { valueFormatter } : {}),
        },
        grid: { left: 8, right: 20, top: 16, bottom: 8, containLabel: true },
        ...(horizontal
            ? { xAxis: { ...valueAxis, splitNumber: 4 }, yAxis: categoryAxis }
            : { xAxis: categoryAxis, yAxis: valueAxis }),
        series: [{
            type: 'bar',
            ...(seriesName ? { name: seriesName } : {}),
            data: values,
            itemStyle: { color: theme.palette[0], borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
            barMaxWidth: 26,
        }],
    };
}

let reviewMetric = 'plays';
let lastReview = null;

function metricValue(entry) {
    return reviewMetric === 'listen_time' ? Number(entry.total_listen_sec) || 0 : entry.count;
}

function metricValueFormatter(value) {
    return reviewMetric === 'listen_time' ? formatDuration(Number(value) || 0, t) : t('unit.plays', { count: num(value) });
}

function setChartSummary(id, messageKey, entries, labelForEntry) {
    if (!entries.length) {
        setText(id, '');
        return;
    }
    const peak = entries.reduce((best, entry) => (
        metricValue(entry) > metricValue(best) ? entry : best
    ));
    setText(id, t(messageKey, {
        label: labelForEntry(peak),
        value: metricValueFormatter(metricValue(peak)),
    }));
}

function renderCharts(review) {
    const seriesName = t(reviewMetric === 'listen_time' ? 'metric.listenTime' : 'metric.plays');
    const valueFormatter = (value) => metricValueFormatter(value);
    monthlyChart.setOption(barOption(
        review.monthly.map((entry) => entry.month.slice(5)),
        review.monthly.map(metricValue),
        { seriesName, valueFormatter },
    ));
    hourlyChart.setOption(barOption(
        review.hourly.map((entry) => String(entry.hour)),
        review.hourly.map(metricValue),
        { categoryInterval: 2, seriesName, valueFormatter },
    ));
    weekdayChart.setOption(barOption(
        review.weekday.map((entry) => t(`weekday.${['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][entry.weekday]}`)),
        review.weekday.map(metricValue),
        { horizontal: true, seriesName, valueFormatter },
    ));
    setChartSummary('reviewMonthlySummary', 'review.aria.monthlySummary', review.monthly, (entry) => entry.month.slice(5));
    setChartSummary('reviewHourlySummary', 'review.aria.hourlySummary', review.hourly, (entry) => `${entry.hour}:00`);
    setChartSummary('reviewWeekdaySummary', 'review.aria.weekdaySummary', review.weekday, (entry) => (
        t(`weekday.${['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][entry.weekday]}`)
    ));
    resizeCharts();
}

function resizeCharts() {
    // Resize only on a real size mismatch: resize() interrupts running
    // update animations, so steady-state calls must be skipped.
    [monthlyChart, hourlyChart, weekdayChart].forEach((chart) => {
        if (!chart) return;
        const dom = chart.getDom();
        if (chart.getWidth() !== dom.clientWidth || chart.getHeight() !== dom.clientHeight) {
            chart.resize();
        }
    });
}

function letterFallback(text) {
    const placeholder = document.createElement('span');
    placeholder.className = 'review-top-cover review-top-cover-fallback';
    placeholder.textContent = String(text || '?').charAt(0).toUpperCase();
    return placeholder;
}

function coverImage(sourceId, id, className, fallbackText) {
    if (!sourceId || !id) return letterFallback(fallbackText);
    const img = document.createElement('img');
    img.className = className;
    img.loading = 'lazy';
    img.decoding = 'async';
    img.alt = '';
    const params = new URLSearchParams({ source_id: sourceId, id, size: '300' });
    img.src = `/api/coverart?${params.toString()}`;
    img.addEventListener('error', () => img.replaceWith(letterFallback(fallbackText)));
    return img;
}

function renderTopList(listId, entries, { coverId, sourceId }) {
    const list = document.getElementById(listId);
    list.replaceChildren();
    entries.forEach((entry, index) => {
        const li = document.createElement('li');
        li.className = 'review-top-item';

        const rank = document.createElement('span');
        rank.className = 'review-top-rank';
        rank.textContent = String(index + 1);
        li.appendChild(rank);

        const id = entry[coverId];
        li.appendChild(coverImage(entry.source_id || sourceId, id, 'review-top-cover', entry.name));

        const meta = document.createElement('span');
        meta.className = 'review-top-meta';
        const name = document.createElement('span');
        name.className = 'review-top-name';
        name.textContent = entry.name || '-';
        name.title = entry.name || '';
        const detail = document.createElement('span');
        detail.className = 'review-top-detail';
        detail.textContent = `${num(entry.count)} · ${formatDuration(entry.total_listen_sec, t)}`;
        meta.append(name, detail);
        li.appendChild(meta);
        list.appendChild(li);
    });
}

function setText(id, value) {
    document.getElementById(id).textContent = value;
}

function renderReview(review, sourceId) {
    lastReview = review;
    setText('reviewTotalPlays', num(review.total_plays));
    setText('reviewListenTime', formatDuration(review.total_listen_sec, t));
    setText('reviewActiveDays', num(review.active_days));
    setText('reviewUniqueTracks', num(review.unique_tracks));
    setText('reviewStreak', t('review.streakDays', { count: num(review.longest_streak_days) }));
    setText('reviewFirstPlay', review.first_played_at ? review.first_played_at.slice(0, 10) : '-');
    setText('reviewLastPlay', review.last_played_at ? review.last_played_at.slice(0, 10) : '-');
    setText('reviewBiggestMonth', review.biggest_month || '-');

    const hasPlays = review.total_plays > 0;
    document.getElementById('reviewEmpty').classList.toggle('hidden', hasPlays);
    document.getElementById('reviewContent').classList.toggle('hidden', !hasPlays);
    if (!hasPlays) {
        [monthlyChart, hourlyChart, weekdayChart].forEach((chart) => chart && chart.clear());
        ['reviewMonthlySummary', 'reviewHourlySummary', 'reviewWeekdaySummary']
            .forEach((id) => setText(id, ''));
        return;
    }
    renderCharts(review);
    renderTopList('reviewTopArtists', review.top_artists, { coverId: 'artist_id', sourceId });
    renderTopList('reviewTopAlbums', review.top_albums, { coverId: 'album_id', sourceId });
    renderTopList('reviewTopTracks', review.top_tracks, { coverId: 'track_id', sourceId });
}

function fillYearSelect() {
    const menu = document.getElementById('reviewYearMenu');
    const label = document.getElementById('reviewYearButtonLabel');
    const current = Math.min(REVIEW_YEAR_MAX, Math.max(REVIEW_YEAR_MIN, new Date().getFullYear()));
    const fragment = document.createDocumentFragment();
    for (let year = Math.max(current, currentYear); year >= REVIEW_YEAR_MIN; year -= 1) {
        const option = document.createElement('button');
        option.type = 'button';
        option.setAttribute('role', 'option');
        option.className = 'filter-option review-year-option';
        option.dataset.value = String(year);
        const text = document.createElement('span');
        text.textContent = String(year);
        const check = document.createElement('span');
        check.className = 'option-check';
        check.setAttribute('aria-hidden', 'true');
        check.textContent = '✓';
        option.append(text, check);
        fragment.appendChild(option);
    }
    menu.replaceChildren(fragment);
    label.textContent = String(currentYear);
    const yearListbox = createListbox({
        trigger: document.getElementById('reviewYearButton'),
        menu,
        onSelect: (option) => {
            const year = Number(option.dataset.value);
            if (!Number.isFinite(year) || year === currentYear) return;
            currentYear = year;
            label.textContent = String(currentYear);
            updateReviewUrl();
            loadReview();
        },
    });
    yearListbox.setSelected(String(currentYear));
}

function updateReviewUrl() {
    const params = new URLSearchParams(window.location.search);
    params.set('year', String(currentYear));
    params.set('timezone', resolveTimezone());
    const query = params.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
}

function showReviewState(state) {
    document.getElementById('reviewLoading').classList.toggle('hidden', state !== 'loading');
    document.getElementById('reviewContent').classList.toggle('hidden', state !== 'content');
    document.getElementById('reviewEmpty').classList.toggle('hidden', state !== 'empty');
    document.getElementById('reviewError').classList.toggle('hidden', state !== 'error');
}

async function loadReview() {
    reviewRequestController?.abort();
    const controller = new AbortController();
    reviewRequestController = controller;
    const generation = ++reviewRequestGeneration;
    const params = new URLSearchParams({
        year: String(currentYear),
        timezone: resolveTimezone(),
    });
    const sourceId = new URLSearchParams(window.location.search).get('source_id') || '';
    if (sourceId) params.set('source_id', sourceId);
    document.getElementById('reviewSubtitle').textContent = t('review.subtitle', { year: String(currentYear) });
    showReviewState('loading');
    try {
        const response = await apiFetch(`/api/stats/review?${params.toString()}`, { signal: controller.signal });
        if (!response.ok) throw new Error(`review request failed (${response.status})`);
        const review = await response.json();
        if (generation !== reviewRequestGeneration) return;
        document.getElementById('reviewSubtitle').textContent =
            t('review.subtitle', { year: String(review.year) });
        renderReview(review, sourceId);
        showReviewState(review.total_plays > 0 ? 'content' : 'empty');
    } catch (error) {
        if (isAbortError(error)) return;
        if (generation !== reviewRequestGeneration) return;
        showReviewState('error');
        console.error('Unable to load review', error);
    }
}

const login = createLoginController({
    overlayId: 'loginOverlay',
    tokenId: 'loginToken',
    inertSelector: '#reviewApp',
    useHiddenClass: true,
    onAuthenticated: loadReview,
});

window.addEventListener(UNAUTHORIZED_EVENT, () => login.show());

window.addEventListener(THEME_CHANGE_EVENT, () => {
    if (lastReview && lastReview.total_plays > 0) renderCharts(lastReview);
});

function localize() {
    i18n.setLocale(readPreference('navidrome-language', 'en'), { persist: false, translateDom: false });
    i18n.translate();
    if (lastReview && lastReview.total_plays > 0) renderCharts(lastReview);
}

function setReviewMetric(metric) {
    if (metric !== 'plays' && metric !== 'listen_time') return;
    reviewMetric = metric;
    document.querySelectorAll('#reviewMetricControl [data-review-metric]').forEach((btn) => {
        const active = btn.dataset.reviewMetric === metric;
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.classList.toggle('bg-accent', active);
        btn.classList.toggle('text-white', active);
        btn.classList.toggle('text-slate-400', !active);
    });
    if (lastReview && lastReview.total_plays > 0) renderCharts(lastReview);
}

document.querySelectorAll('#reviewMetricControl [data-review-metric]').forEach((btn) => {
    btn.addEventListener('click', () => setReviewMetric(btn.dataset.reviewMetric));
});
document.getElementById('reviewRetryButton').addEventListener('click', loadReview);

async function bootstrap() {
    localize();
    updateReviewUrl();
    fillYearSelect();
    initCharts();
    window.addEventListener('resize', () => {
        [monthlyChart, hourlyChart, weekdayChart].forEach((chart) => chart && chart.resize());
    });
    await loadReview();
}

login.bind();
document.getElementById('loginForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const tokenInput = document.getElementById('loginToken');
    try {
        await login.submit(tokenInput.value);
        tokenInput.value = '';
    } catch (_error) {
        const errorEl = document.getElementById('loginError');
        errorEl.textContent = t('auth.invalid');
        errorEl.classList.remove('hidden');
    }
});
bootstrap();
