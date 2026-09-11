import { apiFetch, isAbortError } from './http.js';
import { createLoginController } from './auth.js';
import { UNAUTHORIZED_EVENT } from './http.js';
import { readPreference } from './prefs.js';
import { createI18n } from '../localization.js';
import { pageMessages } from './i18n/index.js';
import { createThemeTokens } from './charts.js';
import { formatDuration, formatRecordedDuration } from './format.js';
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
function resolveArtistMode() {
    const requested = new URLSearchParams(window.location.search).get('artist_mode');
    const mode = requested ?? readPreference('navidrome-artist-mode', 'combined');
    return mode === 'separate' ? 'separate' : 'combined';
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

function initialReviewMonth() {
    const requested = Number(new URLSearchParams(window.location.search).get('month'));
    return Number.isInteger(requested) && requested >= 1 && requested <= 12
        ? requested
        : new Date().getMonth() + 1;
}

function initialReviewPeriod() {
    const params = new URLSearchParams(window.location.search);
    return params.get('period') === 'month' || params.has('month') ? 'month' : 'year';
}

let monthlyChart = null;
let hourlyChart = null;
let weekdayChart = null;
let currentYear = initialReviewYear();
let currentMonth = initialReviewMonth();
let currentPeriod = initialReviewPeriod();
let reviewRequestController = null;
let reviewRequestGeneration = 0;
let monthListbox = null;

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
    const periodEntries = review.period === 'month' ? review.daily : review.monthly;
    const periodLabel = review.period === 'month'
        ? (entry) => entry.date.slice(8)
        : (entry) => entry.month.slice(5);
    monthlyChart.setOption(barOption(
        periodEntries.map(periodLabel),
        periodEntries.map(metricValue),
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
    setChartSummary(
        'reviewMonthlySummary',
        review.period === 'month' ? 'review.aria.dailySummary' : 'review.aria.monthlySummary',
        periodEntries,
        periodLabel,
    );
    document.getElementById('reviewMonthlyChart').setAttribute(
        'aria-label',
        t(review.period === 'month' ? 'review.aria.dailyChart' : 'review.aria.monthlyChart'),
    );
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

function reviewDurationValue(review) {
    const total = Number(review.total_listen_sec) || 0;
    if (Number(review.total_plays) > 0 && review.duration_quality === 'unknown') return '—';
    return formatRecordedDuration(total, t);
}

function busiestDay(review) {
    const rows = Array.isArray(review.daily) ? review.daily : [];
    return rows.reduce((best, row) => (
        Number(row.count) > Number(best?.count || 0) ? row : best
    ), null);
}

function renderReview(review, sourceId) {
    lastReview = review;
    setText('reviewTotalPlays', num(review.total_plays));
    setText('reviewListenTime', reviewDurationValue(review));
    setText('reviewActiveDays', num(review.active_days));
    setText('reviewUniqueTracks', num(review.unique_tracks));
    setText('reviewFirstRecordedTracks', num(review.first_recorded_tracks));
    const change = Number(review.plays_change_pct);
    setText('reviewPlayChange', Number.isFinite(change)
        ? t('review.changePrevious', {
            value: `${change > 0 ? '+' : ''}${num(change)}`,
            period: t(review.period === 'month' ? 'review.previousMonth' : 'review.previousYear'),
        })
        : '');
    setText('reviewStreak', t('review.streakDays', { count: num(review.longest_streak_days) }));
    setText('reviewFirstPlay', review.first_played_at ? review.first_played_at.slice(0, 10) : '-');
    setText('reviewLastPlay', review.last_played_at ? review.last_played_at.slice(0, 10) : '-');
    const peakDay = busiestDay(review);
    setText('reviewBusiestLabel', t(review.period === 'month'
        ? 'review.biggestDay'
        : 'review.biggestMonth'));
    setText('reviewBiggestMonth', review.period === 'month'
        ? (peakDay?.date || '-')
        : (review.biggest_month || '-'));
    setText('reviewPeriodChartTitle', t(review.period === 'month' ? 'review.daily' : 'review.monthly'));
    setText('reviewEmptyMessage', t(review.period === 'month' ? 'review.emptyMonth' : 'review.emptyYear'));

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
    renderTopList('reviewTopAlbums', review.top_albums, { coverId: 'cover_art_id', sourceId });
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

function fillMonthSelect() {
    const menu = document.getElementById('reviewMonthMenu');
    const label = document.getElementById('reviewMonthButtonLabel');
    const formatter = new Intl.DateTimeFormat(i18n.getLocale(), { month: 'long' });
    const options = Array.from({ length: 12 }, (_, index) => {
        const option = document.createElement('button');
        option.type = 'button';
        option.setAttribute('role', 'option');
        option.className = 'filter-option review-month-option';
        option.dataset.value = String(index + 1);
        option.textContent = formatter.format(new Date(2024, index, 1));
        return option;
    });
    menu.replaceChildren(...options);
    label.textContent = options[currentMonth - 1].textContent;
    if (!monthListbox) {
        monthListbox = createListbox({
            trigger: document.getElementById('reviewMonthButton'),
            menu,
            onSelect: (option) => {
                const month = Number(option.dataset.value);
                if (!Number.isInteger(month) || month < 1 || month > 12) return;
                const changed = month !== currentMonth;
                currentMonth = month;
                label.textContent = option.textContent;
                updateReviewUrl();
                if (changed) loadReview();
            },
        });
    }
    monthListbox.setSelected(String(currentMonth));
}

function setReviewPeriod(period, { reload = true } = {}) {
    if (period !== 'year' && period !== 'month') return;
    currentPeriod = period;
    document.querySelectorAll('[data-review-period]').forEach((button) => {
        button.setAttribute('aria-pressed', button.dataset.reviewPeriod === period ? 'true' : 'false');
    });
    document.getElementById('reviewMonthControl').classList.toggle('hidden', period !== 'month');
    updateReviewUrl();
    if (reload) loadReview();
}

function updateReviewUrl() {
    const params = new URLSearchParams(window.location.search);
    params.set('year', String(currentYear));
    params.set('period', currentPeriod);
    if (currentPeriod === 'month') params.set('month', String(currentMonth));
    else params.delete('month');
    params.set('timezone', resolveTimezone());
    params.set('artist_mode', resolveArtistMode());
    const query = params.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
}

function requestedScope() {
    const params = new URLSearchParams(window.location.search);
    return {
        sourceId: params.get('source_id') || '',
        username: params.get('username') || '',
    };
}

function renderReviewScope(username, sourceId, timezoneName) {
    const userLabel = username || t('user.all');
    const sourceLabel = sourceId || t('dashboard.allServers');
    document.getElementById('reviewScope').textContent =
        `${t('history.user')}: ${userLabel} · ${t('dashboard.serverFilter')}: ${sourceLabel}`
        + ` · ${t('review.timezone')}: ${timezoneName}`;
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
        artist_mode: resolveArtistMode(),
    });
    if (currentPeriod === 'month') params.set('month', String(currentMonth));
    const { sourceId, username } = requestedScope();
    if (sourceId) params.set('source_id', sourceId);
    if (username) params.set('username', username);
    const selectedMonth = `${currentYear}-${String(currentMonth).padStart(2, '0')}`;
    document.getElementById('reviewSubtitle').textContent = currentPeriod === 'month'
        ? t('review.subtitleMonth', { month: selectedMonth })
        : t('review.subtitle', { year: String(currentYear) });
    renderReviewScope(username, sourceId, resolveTimezone());
    showReviewState('loading');
    try {
        const response = await apiFetch(`/api/stats/review?${params.toString()}`, { signal: controller.signal });
        if (!response.ok) throw new Error(`review request failed (${response.status})`);
        const review = await response.json();
        if (generation !== reviewRequestGeneration) return;
        document.getElementById('reviewSubtitle').textContent = review.period === 'month'
            ? t('review.subtitleMonth', {
                month: `${review.year}-${String(review.month).padStart(2, '0')}`,
            })
            : t('review.subtitle', { year: String(review.year) });
        renderReviewScope(
            review.username ?? username,
            review.source_id ?? sourceId,
            review.timezone ?? resolveTimezone(),
        );
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
    fillMonthSelect();
    if (lastReview) {
        setText('reviewPeriodChartTitle', t(lastReview.period === 'month' ? 'review.daily' : 'review.monthly'));
        setText('reviewEmptyMessage', t(lastReview.period === 'month' ? 'review.emptyMonth' : 'review.emptyYear'));
    }
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
document.querySelectorAll('[data-review-period]').forEach((button) => {
    button.addEventListener('click', () => setReviewPeriod(button.dataset.reviewPeriod));
});

async function bootstrap() {
    localize();
    updateReviewUrl();
    fillYearSelect();
    fillMonthSelect();
    setReviewPeriod(currentPeriod, { reload: false });
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
