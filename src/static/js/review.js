import { apiFetch, isAbortError } from './http.js';
import { createLoginController } from './auth.js';
import { UNAUTHORIZED_EVENT } from './http.js';
import { readPreference, onPreferenceChange } from './prefs.js';
import { createI18n } from '../localization.js';
import { pageMessages } from './i18n/index.js';
import { chartPalette, createThemeTokens } from './charts.js';
import { formatDuration } from './format.js';
import { createListbox } from './listbox.js';

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
    const saved = readPreference('navidrome-timezone', 'browser');
    if (saved === 'browser' || saved === 'UTC') return saved === 'browser' ? (browserTimezone || 'UTC') : saved;
    return saved || 'UTC';
}

let monthlyChart = null;
let hourlyChart = null;
let weekdayChart = null;
let currentYear = new Date().getFullYear();

function chartBase() {
    return createThemeTokens(document.documentElement.dataset.theme);
}

function initCharts() {
    const mount = (id) => echarts.init(document.getElementById(id), null, { renderer: 'canvas' });
    monthlyChart = mount('reviewMonthlyChart');
    hourlyChart = mount('reviewHourlyChart');
    weekdayChart = mount('reviewWeekdayChart');
}

function barOption(categories, values, { horizontal = false, categoryInterval = 0, seriesName = '', valueFormatter = null } = {}) {
    const categoryAxis = {
        type: 'category',
        data: categories,
        axisLine: { lineStyle: { color: 'rgba(128,128,140,0.25)' } },
        axisLabel: {
            color: chartBase().textStyle.color,
            fontSize: 11,
            hideOverlap: true,
            interval: categoryInterval,
        },
        axisTick: { show: false },
    };
    const valueAxis = {
        type: 'value',
        axisLabel: { color: chartBase().textStyle.color, fontSize: 11, hideOverlap: true },
        splitLine: { lineStyle: { color: 'rgba(128,128,140,0.15)' } },
    };
    return {
        backgroundColor: 'transparent',
        textStyle: chartBase().textStyle,
        tooltip: {
            ...chartBase().tooltip,
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
            itemStyle: { color: chartPalette[0], borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
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
    const current = new Date().getFullYear();
    const fragment = document.createDocumentFragment();
    for (let year = current; year >= current - 5; year -= 1) {
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
            loadReview();
        },
    });
    yearListbox.setSelected(String(currentYear));
}

async function loadReview() {
    const content = document.getElementById('reviewContent');
    const empty = document.getElementById('reviewEmpty');
    const errorEl = document.getElementById('reviewError');
    content.classList.add('hidden');
    empty.classList.add('hidden');
    errorEl.classList.add('hidden');
    try {
        const params = new URLSearchParams({ year: String(currentYear), timezone: resolveTimezone() });
        const response = await apiFetch(`/api/stats/review?${params.toString()}`);
        if (!response.ok) throw new Error(`review request failed (${response.status})`);
        const review = await response.json();
        document.getElementById('reviewSubtitle').textContent =
            t('review.subtitle', { year: String(review.year) });
        const sourceId = new URLSearchParams(window.location.search).get('source_id') || '';
        renderReview(review, sourceId);
    } catch (error) {
        if (isAbortError(error)) return;
        errorEl.classList.remove('hidden');
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

function applyTheme() {
    const base = chartBase();
    [monthlyChart, hourlyChart, weekdayChart].forEach((chart) => {
        if (!chart) return;
        const option = chart.getOption();
        if (!option || !option.series || !option.series.length) return;
        chart.setOption({ backgroundColor: base.backgroundColor, textStyle: base.textStyle, tooltip: base.tooltip });
    });
}

onPreferenceChange('navidrome-theme', (value) => {
    if (value) document.documentElement.dataset.theme = value;
    applyTheme();
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

async function bootstrap() {
    localize();
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
