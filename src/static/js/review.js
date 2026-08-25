import { apiFetch, isAbortError } from './http.js';
import { createLoginController } from './auth.js';
import { UNAUTHORIZED_EVENT } from './http.js';
import { readPreference, onPreferenceChange } from './prefs.js';
import { createI18n } from '../localization.js';
import { catalog, dashboardMessages } from './messages-dashboard.js';
import { catalog as reviewCatalog, reviewMessages } from './messages-review.js';
import { chartPalette, createThemeTokens } from './charts.js';
import { formatDuration } from './format.js';
import { createListbox } from './listbox.js';

const messages = {
    'zh-CN': { ...catalog(dashboardMessages.zhCN), ...reviewCatalog(reviewMessages.zhCN) },
    'zh-TW': { ...catalog(dashboardMessages.zhTW), ...reviewCatalog(reviewMessages.zhTW) },
    en: { ...catalog(dashboardMessages.en), ...reviewCatalog(reviewMessages.en) },
    ja: { ...catalog(dashboardMessages.ja), ...reviewCatalog(reviewMessages.ja) },
};

const i18n = createI18n({ messages, fallbackLocale: 'en' });
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

function barOption(categories, values, { horizontal = false, categoryInterval = 0 } = {}) {
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
        tooltip: { ...chartBase().tooltip, trigger: 'axis' },
        grid: { left: 8, right: 20, top: 16, bottom: 8, containLabel: true },
        ...(horizontal
            ? { xAxis: { ...valueAxis, splitNumber: 4 }, yAxis: categoryAxis }
            : { xAxis: categoryAxis, yAxis: valueAxis }),
        series: [{
            type: 'bar',
            data: values,
            itemStyle: { color: chartPalette[0], borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
            barMaxWidth: 26,
        }],
    };
}

function renderCharts(review) {
    monthlyChart.setOption(barOption(
        review.monthly.map((entry) => entry.month.slice(5)),
        review.monthly.map((entry) => entry.count),
    ));
    hourlyChart.setOption(barOption(
        review.hourly.map((entry) => String(entry.hour)),
        review.hourly.map((entry) => entry.count),
        { categoryInterval: 2 },
    ));
    weekdayChart.setOption(barOption(
        review.weekday.map((entry) => t(`weekday.${['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][entry.weekday]}`)),
        review.weekday.map((entry) => entry.count),
        { horizontal: true },
    ));
}

function coverImage(sourceId, id, className) {
    if (!sourceId || !id) return null;
    const img = document.createElement('img');
    img.className = className;
    img.loading = 'lazy';
    img.decoding = 'async';
    img.alt = '';
    const params = new URLSearchParams({ source_id: sourceId, id, size: '300' });
    img.src = `/api/coverart?${params.toString()}`;
    img.addEventListener('error', () => img.remove());
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

        const id = coverId === 'album_id' ? entry.album_id : entry.track_id;
        const cover = coverImage(sourceId, id, 'review-top-cover');
        if (cover) li.appendChild(cover);
        else {
            const placeholder = document.createElement('span');
            placeholder.className = 'review-top-cover review-top-cover-fallback';
            placeholder.textContent = String(entry.name || '?').charAt(0).toUpperCase();
            li.appendChild(placeholder);
        }

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
    renderTopList('reviewTopArtists', review.top_artists, { coverId: null, sourceId: '' });
    renderTopList('reviewTopAlbums', review.top_albums, { coverId: 'album_id', sourceId });
    renderTopList('reviewTopTracks', review.top_tracks, { coverId: 'track_id', sourceId });
}

let yearListbox = null;

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
    yearListbox = createListbox({
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
}

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
