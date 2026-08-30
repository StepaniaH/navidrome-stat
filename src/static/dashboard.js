import { pageMessages } from './js/i18n/index.js';
import { createI18n } from './localization.js';
import { applyAppVersion } from './js/app-info.js';
import { buildStatsQuery, coverArtUrl, escapeHtml, formatChangeText, formatDuration, validateCustomRange } from './js/format.js';
import { createThemeTokens } from './js/charts.js';
import { onPreferenceChange, readPreference, writePreference } from './js/prefs.js';
import { attachPopover, createListbox } from './js/listbox.js';
import { getFilters, setFilters } from './js/filters.js';
import { THEME_CHANGE_EVENT } from './theme-bootstrap.js';


    const REFRESH_MS = 60000;
    const HIDDEN_REFRESH_MS = 300000;
    const NOW_PLAYING_REFRESH_MS = 10000;
    let colorPalette = [];

    const playerChart = echarts.init(document.getElementById('playerChart'), null, { renderer: 'canvas' });
    const transcodingChart = echarts.init(document.getElementById('transcodingChart'), null, { renderer: 'canvas' });
    const hourlyChart = echarts.init(document.getElementById('hourlyChart'), null, { renderer: 'canvas' });
    const dailyChart = echarts.init(document.getElementById('dailyChart'), null, { renderer: 'canvas' });
    const weekdayHourChart = echarts.init(document.getElementById('weekdayHourChart'), null, { renderer: 'canvas' });

    function resizeDashboardCharts() {
        // Resize only on a real size mismatch: resize() interrupts running
        // update animations, so steady-state calls must be skipped.
        [playerChart, transcodingChart, hourlyChart, dailyChart, weekdayHourChart].forEach((chart) => {
            const dom = chart.getDom();
            if (chart.getWidth() !== dom.clientWidth || chart.getHeight() !== dom.clientHeight) {
                chart.resize();
            }
        });
    }

    // The backend uses Python's `date.weekday()` order: Monday=0 through Sunday=6.
    const WEEKDAY_MESSAGE_KEYS = [
        'weekday.mon', 'weekday.tue', 'weekday.wed', 'weekday.thu',
        'weekday.fri', 'weekday.sat', 'weekday.sun',
    ];
    const HOUR_LABELS = Array.from({ length: 24 }, (_, h) => String(h));

    const HISTORY_COLUMNS_KEY = 'navidrome-history-columns';
    const HISTORY_COLUMNS = [
        { id: 'user', label: 'history.user', cell: 'history-cell-user', col: 'history-col-user' },
        { id: 'track', label: 'history.track', cell: 'history-cell-title', col: 'history-col-track' },
        { id: 'artist', label: 'history.artist', cell: 'history-cell-artist', col: 'history-col-artist' },
        { id: 'album', label: 'history.album', cell: 'history-cell-album', col: 'history-col-album' },
        { id: 'played', label: 'history.lastPlayed', cell: 'history-cell-played', col: 'history-col-played' },
        { id: 'count', label: 'history.plays', cell: 'history-cell-count', col: 'history-col-count' },
    ];

    function allHistoryColumns() {
        return new Set(HISTORY_COLUMNS.map((column) => column.id));
    }

    function readHistoryColumns() {
        const raw = readPreference(HISTORY_COLUMNS_KEY, '');
        if (!raw) return allHistoryColumns();
        const saved = new Set(raw.split(',')
            .filter((id) => HISTORY_COLUMNS.some((column) => column.id === id)));
        return saved.size ? saved : allHistoryColumns();
    }

    let historyColumns = readHistoryColumns();

    function applyHistoryColumns(columns) {
        for (const column of HISTORY_COLUMNS) {
            const visible = columns.has(column.id);
            document.querySelectorAll(`.history-table .${column.cell}, .history-table col.${column.col}`)
                .forEach((element) => element.classList.toggle('column-hidden', !visible));
        }
    }

    function setupHistoryColumns() {
        const button = document.getElementById('historyColumnsButton');
        const panel = document.getElementById('historyColumnsPanel');
        attachPopover({ trigger: button, panel });

        function updatePanel() {
            panel.querySelectorAll('.column-option').forEach((option) => {
                const column = HISTORY_COLUMNS.find(({ id }) => id === option.dataset.columnId);
                if (!column) return;
                const active = historyColumns.has(column.id);
                option.querySelector('.column-option-label').textContent = dashboardMessage(column.label);
                option.setAttribute('aria-pressed', active ? 'true' : 'false');
                option.classList.toggle('column-option-off', !active);
                option.disabled = active && historyColumns.size === 1;
            });
        }

        function buildPanel() {
            const list = document.createElement('div');
            list.className = 'columns-menu';
            for (const column of HISTORY_COLUMNS) {
                const option = document.createElement('button');
                option.type = 'button';
                option.className = 'filter-option column-option';
                option.dataset.columnId = column.id;
                const text = document.createElement('span');
                text.className = 'column-option-label';
                const check = document.createElement('span');
                check.className = 'option-check';
                check.setAttribute('aria-hidden', 'true');
                check.textContent = '✓';
                option.append(text, check);
                option.addEventListener('click', () => {
                    if (historyColumns.has(column.id)) historyColumns.delete(column.id);
                    else historyColumns.add(column.id);
                    writePreference(HISTORY_COLUMNS_KEY, [...historyColumns].join(','));
                    historyColumns = readHistoryColumns();
                    updatePanel();
                    applyHistoryColumns(historyColumns);
                });
                list.appendChild(option);
            }
            panel.replaceChildren(list);
            updatePanel();
        }

        buildPanel();
        applyHistoryColumns(historyColumns);
        onPreferenceChange(HISTORY_COLUMNS_KEY, () => {
            historyColumns = readHistoryColumns();
            updatePanel();
            applyHistoryColumns(historyColumns);
        });
    }

    let statsRequestController = null;
    let nowPlayingRequestController = null;
    let statsRequestGeneration = 0;
    let nowPlayingRequestGeneration = 0;
    let refreshTimer = null;
    let nowPlayingRefreshTimer = null;
    let hasLoadedOnce = false;
    let nowPlayingLoadedOnce = false;
    let authRequired = false;
    const initialFilters = getFilters();
    let statsDays = initialFilters.days;
    let customStartDate = initialFilters.startDate;
    let customEndDate = initialFilters.endDate;
    let selectedSourceId = initialFilters.sourceId;
    let selectedUsername = initialFilters.username;
    const knownSources = new Map();
    let knownUsers = [];
    let globalHistoryRecordCount = null;
    // Shared by the artist and album rankings; changing it refreshes both.
    let rankingMetric = initialFilters.metric;

    // Keep the shareable URL in sync whenever a filter changes.
    function persistFilters() {
        setFilters({
            days: statsDays,
            timezone: statsTimezone,
            metric: rankingMetric,
            sourceId: selectedSourceId,
            username: selectedUsername,
            startDate: customStartDate,
            endDate: customEndDate,
        });
        syncReviewLink();
    }
    let lastFocusBeforeLogin = null;

    // `browser` resolves to an IANA zone before requests; the API does not accept the token.
    const hasSharedTimezone = new URLSearchParams(window.location.search).has('timezone');
    let statsTimezone = hasSharedTimezone ? initialFilters.timezone : 'browser';
    const savedStatsTimezone = readPreference('navidrome-timezone');
    if (!hasSharedTimezone && (savedStatsTimezone === 'browser' || savedStatsTimezone === 'UTC')) {
        statsTimezone = savedStatsTimezone;
    }
    let browserTimezone = null;
    try {
        browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
    } catch (e) {
        browserTimezone = null;
    }
    function resolveStatsTimezone() {
        return statsTimezone === 'browser' ? (browserTimezone || 'UTC') : statsTimezone;
    }
    function syncReviewLink() {
        const link = document.getElementById('reviewLink');
        if (!link) return;
        const params = new URLSearchParams({ timezone: resolveStatsTimezone() });
        if (selectedSourceId) params.set('source_id', selectedSourceId);
        link.href = `/review?${params.toString()}`;
    }
    syncReviewLink();

    const fetchOptions = { credentials: 'same-origin' };

    function stopRefreshTimers() {
        if (refreshTimer) clearInterval(refreshTimer);
        if (nowPlayingRefreshTimer) clearInterval(nowPlayingRefreshTimer);
        refreshTimer = null;
        nowPlayingRefreshTimer = null;
    }

    function cancelDashboardRequests() {
        statsRequestGeneration += 1;
        nowPlayingRequestGeneration += 1;
        if (statsRequestController) statsRequestController.abort();
        if (nowPlayingRequestController) nowPlayingRequestController.abort();
        statsRequestController = null;
        nowPlayingRequestController = null;
    }

    function stopDashboardActivity() {
        stopRefreshTimers();
        stopNowPlayingTicker();
        cancelDashboardRequests();
        setLoading(false);
    }

    function isAbortError(error) {
        return error instanceof DOMException && error.name === 'AbortError';
    }

    function captureStatsRequestState() {
        return Object.freeze({
            days: statsDays,
            startDate: customStartDate,
            endDate: customEndDate,
            sourceId: selectedSourceId,
            username: selectedUsername,
            metric: rankingMetric,
            timezone: resolveStatsTimezone(),
        });
    }

    function captureNowPlayingRequestState() {
        return Object.freeze({ sourceId: selectedSourceId, username: selectedUsername });
    }

    function showLogin(message) {
        const overlay = document.getElementById('loginOverlay');
        const errorEl = document.getElementById('loginError');
        if (overlay.classList.contains('hidden')) {
            lastFocusBeforeLogin = document.activeElement;
        }
        stopDashboardActivity();
        overlay.classList.remove('hidden');
        document.getElementById('dashboardApp').inert = true;
        if (message) {
            errorEl.textContent = message;
            errorEl.classList.remove('hidden');
        } else {
            errorEl.classList.add('hidden');
        }
        setStatus('error', dashboardMessage('auth.required'));
        window.requestAnimationFrame(() => document.getElementById('loginToken').focus());
    }

    function hideLogin() {
        document.getElementById('loginOverlay').classList.add('hidden');
        document.getElementById('loginError').classList.add('hidden');
        document.getElementById('dashboardApp').inert = false;
        if (lastFocusBeforeLogin instanceof HTMLElement) lastFocusBeforeLogin.focus();
        lastFocusBeforeLogin = null;
    }

    async function submitLogin(token) {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ token }),
        });
        if (!response.ok) {
            throw new Error('invalid token');
        }
        hideLogin();
        applyAppVersion();
        await Promise.all([
            Promise.allSettled([fetchUserOptions(), fetchDashboardDiagnostics()]),
            fetchStats(),
            fetchNowPlaying(),
        ]);
        if (lastStatsSnapshot) {
            renderHistoryTable(lastStatsSnapshot.history, !selectedSourceId);
            updateNewUserGuide(lastStatsSnapshot);
        }
        if (document.getElementById('loginOverlay').classList.contains('hidden')) {
            scheduleRefresh();
        }
    }

    // Theme tokens stay mutable so a preference change can re-color charts live.
    let chartTheme = createThemeTokens();
    let chartBase = chartTheme.base;
    colorPalette = [...chartTheme.palette];

    function applyChartTheme() {
        chartTheme = createThemeTokens();
        chartBase = chartTheme.base;
        colorPalette = [...chartTheme.palette];
        if (lastStatsSnapshot) renderStatPanels(lastStatsSnapshot);
    }

    window.addEventListener(THEME_CHANGE_EVENT, applyChartTheme);


    const dashboardI18n = createI18n({
        messages: pageMessages('dashboard', 'review'),
        fallbackLocale: 'en',
    });
    function translateDashboard() {
        dashboardI18n.setLocale(
            readPreference('navidrome-language', 'en'),
            { persist: false, translateDom: false },
        );
        dashboardI18n.translate();
    }
    function dashboardMessage(key, values = {}) { return dashboardI18n.t(key, values); }
    function dashboardNumber(value) { return dashboardI18n.formatNumber(value); }
    function dashboardPlays(value) {
        return dashboardMessage('unit.plays', { count: dashboardNumber(value) });
    }
    function dashboardDuration(seconds) {
        const total = Number(seconds) || 0;
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const secs = Math.floor(total % 60);
        if (hours > 0) return dashboardMessage('duration.hours', { hours, minutes });
        if (minutes > 0) return dashboardMessage('duration.minutes', { minutes });
        return dashboardMessage('duration.seconds', { seconds: secs });
    }
    function refreshDashboardLanguage() {
        translateDashboard();
        setStatus('loading', dashboardMessage('status.syncing'));
        setActiveStatsWindowButton(statsDays);
        setActiveRankingMetric(rankingMetric);
        renderSourceOptions();
        renderUserOptions();
    }
    translateDashboard();

    function setStatus(state, text) {
        const dot = document.getElementById('statusDot');
        const label = document.getElementById('statusText');
        label.textContent = text;
        dot.className = 'dashboard-live-dot ';
        if (state === 'ok') dot.className += 'bg-mint pulse-dot';
        else if (state === 'error') dot.className += 'bg-red-400';
        else if (state === 'loading') dot.className += 'bg-accent animate-pulse';
        else dot.className += 'bg-slate-600';
    }

    function showError(msg) {
        const banner = document.getElementById('errorBanner');
        document.getElementById('errorText').textContent = msg;
        banner.classList.remove('hidden');
    }

    function hideError() {
        document.getElementById('errorBanner').classList.add('hidden');
    }

    const STATS_PANEL_NAMES = [
        'summary', 'players', 'transcoding', 'hourly', 'daily',
        'heatmap', 'artists', 'albums', 'sources', 'history',
    ];
    const PANEL_CONFIG = {
        nowPlaying: {
            wrap: 'nowPlayingPanel',
            skeleton: 'nowPlayingSkeleton',
            contents: [{ id: 'nowPlayingList', hide: 'hidden' }],
            empty: 'nowPlayingEmpty',
            error: 'nowPlayingError',
            summary: 'nowPlayingSummary',
            keepContentOnError: true,
        },
        summary: {
            wrap: 'summarySection',
            error: 'summaryError',
            summary: 'summaryAria',
        },
        players: {
            wrap: 'playerChartWrap',
            skeleton: 'playerChartSkeleton',
            contents: [{ id: 'playerChart', hide: 'visibility' }],
            empty: 'playerChartEmpty',
            error: 'playerChartError',
            summary: 'playerChartSummary',
        },
        transcoding: {
            wrap: 'transcodingChartWrap',
            skeleton: 'transcodingChartSkeleton',
            contents: [{ id: 'transcodingChart', hide: 'visibility' }],
            empty: 'transcodingChartEmpty',
            error: 'transcodingChartError',
            summary: 'transcodingChartSummary',
        },
        hourly: {
            wrap: 'hourlyChartWrap',
            skeleton: 'hourlyChartSkeleton',
            contents: [{ id: 'hourlyChart', hide: 'visibility' }],
            empty: 'hourlyChartEmpty',
            error: 'hourlyChartError',
            summary: 'hourlyChartSummary',
        },
        daily: {
            wrap: 'dailyChartWrap',
            skeleton: 'dailyChartSkeleton',
            contents: [{ id: 'dailyChart', hide: 'visibility' }],
            empty: 'dailyChartEmpty',
            error: 'dailyChartError',
            summary: 'dailyChartSummary',
        },
        heatmap: {
            wrap: 'weekdayHourChartWrap',
            skeleton: 'weekdayHourChartSkeleton',
            contents: [{ id: 'weekdayHourChart', hide: 'visibility' }],
            empty: 'weekdayHourChartEmpty',
            error: 'weekdayHourChartError',
            summary: 'weekdayHourChartSummary',
        },
        artists: {
            wrap: 'topArtistsChartWrap',
            skeleton: 'topArtistsChartSkeleton',
            contents: [{ id: 'topArtistsChart', hide: 'invisible' }],
            empty: 'topArtistsChartEmpty',
            error: 'topArtistsChartError',
            summary: 'topArtistsChartSummary',
        },
        albums: {
            wrap: 'topAlbumsChartWrap',
            skeleton: 'topAlbumsChartSkeleton',
            contents: [{ id: 'topAlbumsChart', hide: 'invisible' }],
            empty: 'topAlbumsChartEmpty',
            error: 'topAlbumsChartError',
            summary: 'topAlbumsChartSummary',
        },
        sources: {
            wrap: 'serverSourcePanel',
            contents: [{ id: 'serverSourceBreakdown', hide: 'hidden' }],
            empty: 'serverSourceEmpty',
            error: 'serverSourceError',
            summary: 'serverSourceSummary',
        },
        history: {
            wrap: 'historyTableWrap',
            empty: 'historyEmpty',
            error: 'historyError',
            summary: 'historySummary',
        },
    };

    function setPanelSummary(name, text) {
        const cfg = PANEL_CONFIG[name];
        if (!cfg || !cfg.summary) return;
        const el = document.getElementById(cfg.summary);
        if (el) el.textContent = text;
    }

    function setPanelState(name, state, message) {
        const cfg = PANEL_CONFIG[name];
        if (!cfg) return;
        const wrap = document.getElementById(cfg.wrap);
        if (wrap) {
            wrap.setAttribute('aria-busy', state === 'loading' ? 'true' : 'false');
            wrap.dataset.panelState = state;
        }
        const skeleton = cfg.skeleton && document.getElementById(cfg.skeleton);
        if (skeleton) {
            skeleton.classList.toggle('hidden', state !== 'loading');
            skeleton.setAttribute('aria-hidden', state === 'loading' ? 'false' : 'true');
        }
        const empty = cfg.empty && document.getElementById(cfg.empty);
        if (empty) empty.classList.toggle('hidden', state !== 'empty');
        const error = cfg.error && document.getElementById(cfg.error);
        if (error) {
            error.classList.toggle('hidden', state !== 'error');
            if (state === 'error') {
                const target = error.querySelector('span') || error;
                target.textContent = message || dashboardMessage('error.section');
            }
        }
        const hideContents = state === 'loading'
            || state === 'empty'
            || (state === 'error' && !cfg.keepContentOnError);
        (cfg.contents || []).forEach((item) => {
            const el = document.getElementById(item.id);
            if (!el) return;
            if (item.hide === 'hidden') {
                el.classList.toggle('hidden', hideContents);
            } else if (item.hide === 'invisible') {
                el.classList.toggle('invisible', hideContents);
            } else if (item.hide === 'visibility') {
                el.style.visibility = hideContents ? 'hidden' : 'visible';
                el.classList.toggle('invisible', hideContents);
            }
        });
        if (state === 'loading') setPanelSummary(name, dashboardMessage('aria.loading'));
        else if (state === 'empty') setPanelSummary(name, message || dashboardMessage('aria.empty'));
        else if (state === 'error') setPanelSummary(name, message || dashboardMessage('error.section'));
    }

    function snapshotArray(data) {
        if (data === undefined || data === null) return { kind: 'missing' };
        if (!Array.isArray(data)) return { kind: 'invalid' };
        return { kind: 'ok', value: data };
    }

    function beginArrayPanel(name, data, hasValues, emptyMessage) {
        const parsed = snapshotArray(data);
        if (parsed.kind !== 'ok') {
            setPanelState(name, 'error', dashboardMessage('error.section'));
            return null;
        }
        if (!hasValues(parsed.value)) {
            setPanelState(name, 'empty', emptyMessage);
            return null;
        }
        setPanelState(name, 'ready');
        return parsed.value;
    }

    function renderPanelSafely(name, fn) {
        try {
            fn();
        } catch (error) {
            console.error('Error rendering panel', name, error);
            setPanelState(name, 'error', dashboardMessage('error.section'));
        }
    }

    function setLoading(loading) {
        if (loading && !hasLoadedOnce) {
            STATS_PANEL_NAMES.forEach((name) => setPanelState(name, 'loading'));
        }
    }

    function formatListenDuration(totalSeconds) { return dashboardDuration(totalSeconds); }

    function formatPlayedAt(isoString) {
        if (!isoString) return '—';
        const date = new Date(isoString);
        if (Number.isNaN(date.getTime())) return '—';
        return date.toLocaleString(dashboardI18n.getLocale(), {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    function formatElapsed(seconds) {
        const total = Math.max(0, Math.floor(Number(seconds) || 0));
        const minutes = Math.floor(total / 60);
        const secs = total % 60;
        return `${minutes}:${String(secs).padStart(2, '0')}`;
    }

    // Advance elapsed time locally; each server refresh resets the authoritative baseline.
    let nowPlayingTicker = null;
    let nowPlayingRenderedAt = 0;
    let nowPlayingEntries = [];

    function stopNowPlayingTicker() {
        if (nowPlayingTicker) {
            clearInterval(nowPlayingTicker);
            nowPlayingTicker = null;
        }
    }

    function startNowPlayingTicker() {
        stopNowPlayingTicker();
        if (!nowPlayingEntries.length || document.hidden) return;
        nowPlayingTicker = setInterval(() => {
            const delta = Math.floor((Date.now() - nowPlayingRenderedAt) / 1000);
            for (const entry of nowPlayingEntries) {
                entry.span.textContent = formatElapsed(entry.baseline + delta);
            }
        }, 1000);
    }

    function createSourceBadge(item) {
        const sourceName = item && (item.source_name || item.source_id);
        if (!sourceName) return null;
        const badge = document.createElement('span');
        badge.className = 'source-badge';
        badge.textContent = String(sourceName);
        badge.title = dashboardMessage('label.source', { name: sourceName });
        badge.setAttribute('aria-label', badge.title);
        return badge;
    }

    function createSourceLabel(item) {
        const sourceName = item && (item.source_name || item.source_id);
        if (!sourceName) return null;
        const label = document.createElement('span');
        label.className = 'history-user-source';
        label.textContent = String(sourceName);
        label.title = dashboardMessage('label.source', { name: sourceName });
        return label;
    }

    function firstKnownSourceId() {
        for (const id of knownSources.keys()) return id;
        return '';
    }

    function createRankingFallback(text) {
        const span = document.createElement('span');
        span.className = 'ranking-cover ranking-cover-fallback';
        span.setAttribute('aria-hidden', 'true');
        span.textContent = String(text || '?').trim().charAt(0).toUpperCase() || '?';
        return span;
    }

    function createCoverImage({ sourceId, id, className, onError }) {
        if (!sourceId || !id) return null;
        const img = document.createElement('img');
        img.className = className;
        img.loading = 'lazy';
        img.decoding = 'async';
        img.alt = '';
        img.src = coverArtUrl({ sourceId, id, size: 300 });
        img.addEventListener('error', onError ? () => onError(img) : (() => img.remove()));
        return img;
    }

    function renderNowPlaying(items, showSources = !selectedSourceId) {
        const list = document.getElementById('nowPlayingList');
        const countEl = document.getElementById('nowPlayingCount');
        list.replaceChildren();
        nowPlayingEntries = [];

        if (!Array.isArray(items)) {
            setPanelState('nowPlaying', 'error', dashboardMessage('error.nowPlaying'));
            countEl.textContent = '';
            stopNowPlayingTicker();
            return;
        }
        if (items.length === 0) {
            setPanelState('nowPlaying', 'empty', dashboardMessage('empty.nowPlaying'));
            countEl.textContent = '';
            stopNowPlayingTicker();
            return;
        }

        setPanelState('nowPlaying', 'ready');
        setPanelSummary('nowPlaying', dashboardMessage('aria.nowPlayingSummary', {
            count: dashboardNumber(items.length),
        }));
        countEl.textContent = `· ${items.length}`;

        items.forEach((item) => {
            const li = document.createElement('li');
            li.className = 'now-playing-item';

            const cover = createCoverImage({
                sourceId: item.source_id,
                id: item.track_id,
                className: 'now-playing-cover',
            });
            if (cover) {
                li.appendChild(cover);
            } else {
                const icon = document.createElement('span');
                icon.className = 'now-playing-icon';
                icon.setAttribute('aria-hidden', 'true');
                icon.textContent = '♪';
                li.appendChild(icon);
            }

            const meta = document.createElement('div');
            meta.className = 'now-playing-meta';

            const titleRow = document.createElement('div');
            titleRow.className = 'now-playing-title-row';
            const title = document.createElement('span');
            title.className = 'now-playing-title';
            title.textContent = item.title || '-';
            title.title = item.title || '';
            const artist = document.createElement('span');
            artist.className = 'now-playing-artist';
            artist.textContent = item.artist ? `· ${item.artist}` : '';
            artist.title = item.artist || '';
            titleRow.appendChild(title);
            titleRow.appendChild(artist);
            meta.appendChild(titleRow);

            const subRow = document.createElement('div');
            subRow.className = 'now-playing-subrow';
            const client = document.createElement('span');
            client.className = 'now-playing-client';
            const clientGlyph = document.createElement('span');
            clientGlyph.className = 'now-playing-client-glyph';
            clientGlyph.textContent = '▣';
            clientGlyph.setAttribute('aria-hidden', 'true');
            const clientLabel = document.createElement('span');
            clientLabel.className = 'now-playing-client-label';
            clientLabel.textContent = item.client_name || '-';
            clientLabel.title = item.client_name || '';
            client.appendChild(clientGlyph);
            client.appendChild(clientLabel);
            const sep = document.createElement('span');
            sep.className = 'now-playing-separator';
            sep.textContent = '·';
            const user = document.createElement('span');
            user.className = 'now-playing-user';
            user.textContent = item.username || '-';
            user.title = item.username || '';
            subRow.appendChild(client);
            subRow.appendChild(sep);
            subRow.appendChild(user);
            if (showSources) {
                const sourceBadge = createSourceBadge(item);
                if (sourceBadge) subRow.appendChild(sourceBadge);
            }
            meta.appendChild(subRow);

            li.appendChild(meta);

            const elapsed = document.createElement('span');
            elapsed.className = 'now-playing-elapsed stat-value';
            elapsed.textContent = formatElapsed(item.seconds_elapsed);
            li.appendChild(elapsed);

            list.appendChild(li);

            const baseline = Math.max(0, Math.floor(Number(item.seconds_elapsed) || 0));
            nowPlayingEntries.push({ span: elapsed, baseline });
        });

        nowPlayingRenderedAt = Date.now();
        startNowPlayingTicker();
    }

    function updateSummary(summary, transcoding) {
        if (!summary || typeof summary !== 'object') {
            setPanelState('summary', 'error', dashboardMessage('error.section'));
            return;
        }
        const transcodingRows = Array.isArray(transcoding) ? transcoding : [];
        document.getElementById('statTotalPlays').textContent =
            dashboardNumber(summary.total_plays);
        document.getElementById('statListenTime').textContent =
            formatListenDuration(summary.total_listen_sec);
        document.getElementById('statUniqueTracks').textContent =
            dashboardNumber(summary.unique_tracks);

        const playsChangeEl = document.getElementById('statTotalPlaysChange');
        const listenChangeEl = document.getElementById('statListenTimeChange');
        const activeDaysEl = document.getElementById('statActiveDays');
        playsChangeEl.textContent = formatChangeText(summary.plays_change_pct, { compareLabel: compareLabel() });
        listenChangeEl.textContent = formatChangeText(summary.listen_change_pct, { compareLabel: compareLabel() });

        const activeDays = Number(summary.active_days) || 0;
        const avgPlays = summary.average_daily_plays;
        const avgParts = [];
        if (activeDays > 0) {
            avgParts.push(dashboardMessage('summary.activeDays', { count: activeDays }));
        }
        if (typeof avgPlays === 'number' && Number.isFinite(avgPlays)) {
            avgParts.push(dashboardMessage('summary.playsPerDay', {
                count: avgPlays.toFixed(1),
            }));
        }
        activeDaysEl.textContent = avgParts.join(' · ');

        const direct = transcodingRows.find(t => !t.is_transcoding)?.count || 0;
        const trans = transcodingRows.find(t => t.is_transcoding)?.count || 0;
        const total = direct + trans;
        const uniqueEl = document.getElementById('statUniqueTracks');
        if (total > 0) {
            const ratio = Math.round((trans / total) * 100);
            uniqueEl.title = dashboardMessage('summary.uniqueDetails', {
                days: activeDays,
                ratio,
                clients: summary.client_count ?? 0,
            });
        } else {
            uniqueEl.title = activeDays > 0
                ? dashboardMessage('summary.activeDays', { count: activeDays })
                : '';
        }
        setPanelState('summary', 'ready');
        setPanelSummary('summary', dashboardMessage('aria.summaryPlays', {
            plays: dashboardNumber(summary.total_plays),
            tracks: dashboardNumber(summary.unique_tracks),
        }));
    }

    function compareLabel() {
        return dashboardMessage('compare.previous');
    }

    function renderPlayerChart(data) {
        const legend = document.getElementById('playerChartLegend');
        legend.replaceChildren();
        legend.classList.add('hidden');
        const rows = beginArrayPanel(
            'players',
            data,
            (items) => items.length > 0 && items.some(d => Number(d.count) > 0),
            dashboardMessage('empty.clients'),
        );
        if (!rows) return;

        const table = document.createElement('table');
        table.className = 'player-legend-table';
        const caption = document.createElement('caption');
        caption.className = 'sr-only';
        caption.textContent = dashboardMessage('client.detailTitle');
        table.appendChild(caption);
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        [
            dashboardMessage('client.name'),
            dashboardMessage('client.plays'),
            dashboardMessage('client.listeningTime'),
            dashboardMessage('client.averagePlay'),
            dashboardMessage('client.transcodingRate'),
        ].forEach((label, index) => {
            const th = document.createElement('th');
            th.scope = 'col';
            th.textContent = label;
            if (index >= 3) th.classList.add('hide-mobile');
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);
        const tbody = document.createElement('tbody');
        data.forEach((item, index) => {
            const row = document.createElement('tr');
            const name = document.createElement('td');
            name.className = 'client-cell';
            name.textContent = item.client_name || dashboardMessage('label.unknownClient');
            name.title = item.client_name || dashboardMessage('label.unknownClient');
            const count = document.createElement('td');
            count.textContent = dashboardNumber(item.count);
            const total = document.createElement('td');
            total.textContent = formatListenDuration(item.total_listen_sec);
            const average = document.createElement('td');
            average.className = 'hide-mobile';
            average.textContent = formatListenDuration(item.average_listen_sec);
            const transcode = document.createElement('td');
            transcode.className = 'hide-mobile';
            const rate = Number(item.transcoding_rate_pct);
            transcode.textContent = Number.isFinite(rate) ? `${rate.toFixed(1)}%` : '—';
            [name, count, total, average, transcode].forEach(cell => {
                row.appendChild(cell);
            });
            tbody.appendChild(row);
        });
        table.appendChild(tbody);
        legend.appendChild(table);
        legend.classList.remove('hidden');

        playerChart.setOption({
            ...chartBase,
            animationDurationUpdate: 450,
            animationEasingUpdate: 'cubicInOut',
            animationTypeUpdate: 'transition',
            color: colorPalette,
            legend: { bottom: 0, textStyle: { color: chartTheme.axisText, fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
            tooltip: {
                ...chartBase.tooltip,
                formatter: (params) => {
                    const name = escapeHtml(params.name || '');
                    return `${name}<br/>${dashboardMessage('label.play')} ${dashboardPlays(params.value)}`;
                },
            },
            series: [{
                name: dashboardMessage('dashboard.clients'),
                type: 'pie',
                radius: ['42%', '68%'],
                center: ['50%', '45%'],
                animationDurationUpdate: 650,
                animationEasingUpdate: 'cubicInOut',
                universalTransition: true,
                itemStyle: { borderRadius: 6, borderColor: chartTheme.pieSeparator, borderWidth: 2 },
                label: { color: chartTheme.axisText, fontSize: 11 },
                data: data.map(item => ({
                    name: item.client_name || dashboardMessage('label.unknownClient'),
                    value: item.count,
                })),
            }],
        });
        setPanelSummary('players', dashboardMessage('aria.clientsSummary', {
            count: dashboardNumber(rows.length),
            top: rows[0].client_name || dashboardMessage('source.unknown'),
            plays: dashboardNumber(rows[0].count),
        }));
    }

    function renderTranscodingChart(data) {
        const rows = beginArrayPanel(
            'transcoding',
            data,
            (items) => items.length > 0 && items.some(d => Number(d.count) > 0),
            dashboardMessage('empty.transcoding'),
        );
        if (!rows) return;

        const transformed = rows.map(item => ({
            name: item.is_transcoding
                ? dashboardMessage('label.transcoded')
                : dashboardMessage('label.directPlay'),
            value: item.count,
            playsPct: Number(item.plays_pct) || 0,
            listenPct: Number(item.listen_sec_pct) || 0,
            listenSec: Number(item.total_listen_sec) || 0,
        }));

        transcodingChart.setOption({
            ...chartBase,
            animationDurationUpdate: 450,
            animationEasingUpdate: 'cubicInOut',
            animationTypeUpdate: 'transition',
            color: [colorPalette[2], colorPalette[5]],
            legend: { bottom: 0, textStyle: { color: chartTheme.axisText, fontSize: 11 } },
            tooltip: {
                ...chartBase.tooltip,
                formatter: (params) => {
                    const item = params.data || {};
                    return `${params.name}<br/>${dashboardMessage('label.play')} ${dashboardPlays(item.value)} (${item.playsPct ?? 0}%)<br/>${dashboardMessage('label.listening')} ${dashboardDuration(item.listenSec)} (${item.listenPct ?? 0}%)`;
                },
            },
            series: [{
                name: dashboardMessage('label.play'),
                type: 'pie',
                radius: '62%',
                center: ['50%', '45%'],
                animationDurationUpdate: 650,
                animationEasingUpdate: 'cubicInOut',
                universalTransition: true,
                itemStyle: { borderRadius: 4, borderColor: chartTheme.pieSeparator, borderWidth: 2 },
                label: { color: chartTheme.axisText, fontSize: 11 },
                data: transformed,
            }],
        });
        const directCount = rows.find(t => !t.is_transcoding)?.count || 0;
        const transcodedCount = rows.find(t => t.is_transcoding)?.count || 0;
        setPanelSummary('transcoding', dashboardMessage('aria.transcodingSummary', {
            direct: dashboardNumber(directCount),
            transcoded: dashboardNumber(transcodedCount),
        }));
    }

    function renderHourlyChart(data) {
        const rows = beginArrayPanel(
            'hourly',
            data,
            (items) => items.length > 0 && items.some(d => Number(d.count) > 0),
            dashboardMessage('empty.hourly'),
        );
        if (!rows) return;

        const buckets = Array.from({ length: 24 }, (_, h) => {
            const found = rows.find(d => Number(d.hour) === h);
            return { hour: h, count: found ? Number(found.count) : 0 };
        });

        hourlyChart.setOption({
            ...chartBase,
            animationDurationUpdate: 450,
            animationEasingUpdate: 'cubicInOut',
            color: [colorPalette[0]],
            grid: { left: 40, right: 16, top: 16, bottom: 32 },
            tooltip: {
                ...chartBase.tooltip,
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                formatter: (params) => {
                    const p = params[0];
                    return `${p.axisValue} ${dashboardMessage('label.hour')}<br/>${dashboardMessage('label.play')} ${dashboardPlays(p.data)}`;
                },
            },
            xAxis: {
                type: 'category',
                data: buckets.map(b => String(b.hour)),
                axisLine: { lineStyle: { color: chartTheme.axisLine } },
                axisLabel: { color: chartTheme.axisText, fontSize: 11 },
                axisTick: { show: false },
            },
            yAxis: {
                type: 'value',
                splitLine: { lineStyle: { color: chartTheme.gridLine } },
                axisLabel: { color: chartTheme.axisText, fontSize: 11 },
            },
            series: [{
                name: dashboardMessage('metric.plays'),
                type: 'bar',
                data: buckets.map(b => b.count),
                itemStyle: {
                    borderRadius: [4, 4, 0, 0],
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: chartTheme.barGradient[0] },
                            { offset: 1, color: chartTheme.barGradient[1] },
                        ],
                    },
                },
            }],
        });
        const peakHour = buckets.reduce((best, b) => b.count > best.count ? b : best, buckets[0]);
        setPanelSummary('hourly', dashboardMessage('aria.hourlySummary', {
            hour: dashboardNumber(peakHour.hour),
            plays: dashboardNumber(peakHour.count),
        }));
    }

    function renderDailyChart(data) {
        const rows = beginArrayPanel(
            'daily',
            data,
            (items) => items.length > 0 && items.some(d => Number(d.count) > 0),
            dashboardMessage('empty.daily'),
        );
        if (!rows) return;

        const sorted = [...rows].sort((a, b) => String(a.date).localeCompare(String(b.date)));
        const dates = sorted.map(d => d.date);
        const counts = sorted.map(d => Number(d.count));

        dailyChart.setOption({
            ...chartBase,
            animationDurationUpdate: 450,
            animationEasingUpdate: 'cubicInOut',
            color: [colorPalette[2]],
            grid: { left: 40, right: 16, top: 16, bottom: 32 },
            tooltip: {
                ...chartBase.tooltip,
                trigger: 'axis',
                formatter: (params) => {
                    const p = params[0];
                    return `${p.axisValue}<br/>${dashboardMessage('label.play')} ${dashboardPlays(p.data)}`;
                },
            },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: dates,
                axisLine: { lineStyle: { color: chartTheme.axisLine } },
                axisLabel: { color: chartTheme.axisText, fontSize: 11 },
                axisTick: { show: false },
            },
            yAxis: {
                type: 'value',
                splitLine: { lineStyle: { color: chartTheme.gridLine } },
                axisLabel: { color: chartTheme.axisText, fontSize: 11 },
            },
            series: [{
                name: dashboardMessage('metric.plays'),
                type: 'line',
                smooth: true,
                symbol: 'circle',
                symbolSize: 6,
                data: counts,
                lineStyle: { width: 2 },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: chartTheme.areaGradient[0] },
                            { offset: 1, color: chartTheme.areaGradient[1] },
                        ],
                    },
                },
            }],
        });
        const activeDays = sorted.filter(d => Number(d.count) > 0).length;
        setPanelSummary('daily', dashboardMessage('aria.dailySummary', {
            days: dashboardNumber(activeDays),
            plays: dashboardNumber(Math.max(0, ...counts)),
        }));
    }

    function heatmapRamp() {
        return chartTheme.heatmap;
    }

    function renderWeekdayHourChart(data) {
        const rows = beginArrayPanel(
            'heatmap',
            data,
            (items) => items.some(d => Number(d.count) > 0),
            dashboardMessage('empty.heatmap'),
        );
        if (!rows) return;

        const points = rows.map(item => [
            Number(item.hour),
            Number(item.weekday),
            Number(item.count) || 0,
        ]);
        const maxCount = Math.max(1, ...points.map(p => p[2]));
        const weekdayLabels = WEEKDAY_MESSAGE_KEYS.map(key => dashboardMessage(key));

        weekdayHourChart.setOption({
            ...chartBase,
            animationDurationUpdate: 450,
            animationEasingUpdate: 'cubicInOut',
            tooltip: {
                ...chartBase.tooltip,
                formatter: (params) => {
                    const [h, w, c] = params.value;
                    return `${weekdayLabels[w] || '?'} ${h} ${dashboardMessage('label.hour')}<br/>${dashboardMessage('label.play')} ${dashboardPlays(c)}`;
                },
            },
            grid: { left: 48, right: 16, top: 16, bottom: 80 },
            xAxis: {
                type: 'category',
                data: HOUR_LABELS,
                splitArea: { show: false },
                axisLine: { lineStyle: { color: chartTheme.axisLine } },
                axisLabel: { color: chartTheme.axisText, fontSize: 11 },
                axisTick: { show: false },
            },
            yAxis: {
                type: 'category',
                data: weekdayLabels,
                inverse: true,
                splitArea: { show: false },
                axisLine: { lineStyle: { color: chartTheme.axisLine } },
                axisLabel: { color: chartTheme.axisText, fontSize: 11 },
                axisTick: { show: false },
            },
            visualMap: {
                min: 0,
                max: maxCount,
                calculable: true,
                orient: 'horizontal',
                left: 'center',
                bottom: 0,
                itemWidth: 12,
                textStyle: { color: chartTheme.axisText, fontSize: 11 },
                inRange: { color: heatmapRamp() },
            },
            series: [{
                name: dashboardMessage('metric.plays'),
                type: 'heatmap',
                data: points,
                label: { show: false },
                itemStyle: { borderRadius: 3, borderWidth: 2, borderColor: 'transparent' },
                emphasis: { itemStyle: { shadowBlur: 10, shadowColor: chartTheme.shadow } },
            }],
        });
        const peak = rows.reduce((best, item) => (
            Number(item.count) > Number(best.count) ? item : best
        ), rows[0]);
        setPanelSummary('heatmap', dashboardMessage('aria.heatmapSummary', {
            weekday: weekdayLabels[Number(peak.weekday)] || String(peak.weekday),
            hour: dashboardNumber(peak.hour),
            plays: dashboardNumber(peak.count),
        }));
    }

    function renderRankingList({ containerId, panel, data, labelKey, barClass, ariaLabel, metric, sourceId }) {
        const container = document.getElementById(containerId);
        container.replaceChildren();
        container.setAttribute('role', 'list');
        container.setAttribute('aria-label', ariaLabel);

        // Check both ranking dimensions so sparse results still render.
        const rows = beginArrayPanel(
            panel,
            data,
            (items) => items.length > 0 && items.some(d => Number(d.value) > 0 || Number(d.count) > 0 || Number(d.total_listen_sec) > 0),
            dashboardMessage(panel === 'artists' ? 'empty.artists' : 'empty.albums'),
        );
        if (!rows) return;

        // The backend sorts by `value`, then name; the secondary cell shows the other metric.
        const maxValue = Math.max(
            1,
            ...data.map(d => Number(d.value) || 0),
        );

        data.forEach((item, idx) => {
            const value = Number(item.value) || 0;
            const count = Number(item.count) || 0;
            const totalListenSec = Number(item.total_listen_sec) || 0;
            const pct = Math.max(0, Math.min(100, Math.round((value / maxValue) * 100)));
            const labelValue = item[labelKey] != null ? String(item[labelKey]) : '';

            const row = document.createElement('div');
            row.className = 'ranking-row';
            row.setAttribute('role', 'listitem');

            const rankCell = document.createElement('div');
            rankCell.className = 'ranking-rank stat-value';
            rankCell.setAttribute('aria-hidden', 'true');
            rankCell.textContent = String(idx + 1);

            const labelCell = document.createElement('div');
            labelCell.className = 'ranking-label';
            labelCell.textContent = labelValue || '-';
            labelCell.title = labelValue;

            const cover = createCoverImage({
                sourceId: item.source_id || sourceId,
                id: panel === 'albums' ? item.album_id : item.artist_id,
                className: 'ranking-cover',
                onError: (image) => image.replaceWith(createRankingFallback(labelValue)),
            });

            const barCell = document.createElement('div');
            barCell.className = 'ranking-bar-cell';
            barCell.setAttribute('aria-hidden', 'true');
            const ariaSummary = metric === 'listen_time'
                ? `${dashboardMessage('label.listening')} ${dashboardDuration(value)} · ${dashboardPlays(count)}`
                : `${dashboardMessage('label.play')} ${dashboardPlays(count)} · ${dashboardDuration(totalListenSec)}`;
            const track = document.createElement('div');
            track.className = 'ranking-track';
            const bar = document.createElement('div');
            bar.className = `ranking-bar ${barClass}`;
            bar.style.width = `${pct}%`;
            track.appendChild(bar);
            barCell.appendChild(track);

            const countCell = document.createElement('div');
            countCell.className = 'ranking-count stat-value';
            countCell.setAttribute('aria-label', `${labelValue || '-'} · ${ariaSummary}`);
            const primary = document.createElement('div');
            primary.className = 'ranking-count-primary';
            primary.textContent = metric === 'listen_time' ? dashboardDuration(value) : dashboardPlays(count);
            const secondary = document.createElement('div');
            secondary.className = 'ranking-count-secondary';
            secondary.textContent = metric === 'listen_time' ? dashboardPlays(count) : dashboardDuration(totalListenSec);
            countCell.appendChild(primary);
            countCell.appendChild(secondary);

            row.appendChild(rankCell);
            if (cover) row.appendChild(cover);
            else row.appendChild(createRankingFallback(labelValue));
            row.appendChild(labelCell);
            row.appendChild(barCell);
            row.appendChild(countCell);
            container.appendChild(row);
        });
        setPanelSummary(panel, dashboardMessage('aria.rankingSummary', {
            count: dashboardNumber(rows.length),
            top: String(rows[0][labelKey] || ''),
        }));
    }

    function renderTopArtistsChart(data, metric) {
        const activeMetric = metric || rankingMetric;
        renderRankingList({
            containerId: 'topArtistsChart',
            panel: 'artists',
            data: data,
            labelKey: 'artist',
            barClass: 'ranking-bar-artists',
            ariaLabel: dashboardMessage(activeMetric === 'listen_time' ? 'aria.artistsByTime' : 'aria.artistsByPlays'),
            metric: activeMetric,
            sourceId: selectedSourceId || firstKnownSourceId(),
        });
    }

    function renderTopAlbumsChart(data, metric) {
        const activeMetric = metric || rankingMetric;
        renderRankingList({
            containerId: 'topAlbumsChart',
            panel: 'albums',
            data: data,
            labelKey: 'album',
            barClass: 'ranking-bar-albums',
            ariaLabel: dashboardMessage(activeMetric === 'listen_time' ? 'aria.albumsByTime' : 'aria.albumsByPlays'),
            metric: activeMetric,
            sourceId: selectedSourceId || firstKnownSourceId(),
        });
    }

    function renderServerSourceBreakdown(data) {
        const container = document.getElementById('serverSourceBreakdown');
        container.replaceChildren();
        const rows = beginArrayPanel(
            'sources',
            data,
            (items) => items.length > 0,
            dashboardMessage('source.empty'),
        );
        if (!rows) return;
        rows.forEach((item) => {
            const row = document.createElement('div');
            row.className = 'source-breakdown-row';
            const name = document.createElement('span');
            name.className = 'source-breakdown-name';
            name.textContent = item.source_name || item.source_id || dashboardMessage('source.unknown');
            name.title = name.textContent;
            const count = document.createElement('span');
            count.className = 'source-breakdown-count stat-value';
            count.textContent = dashboardPlays(item.count);
            const duration = document.createElement('span');
            duration.className = 'source-breakdown-duration stat-value';
            duration.textContent = formatListenDuration(item.total_listen_sec);
            row.append(name, count, duration);
            container.appendChild(row);
        });
        setPanelSummary('sources', dashboardMessage('aria.sourcesSummary', {
            count: dashboardNumber(rows.length),
        }));
    }

    function renderSourceOptions() {
        const menu = document.getElementById('statsSourceMenu');
        const entries = [
            ['', dashboardMessage('source.all')],
            ...[...knownSources.entries()]
                .sort((a, b) => String(a[1]).localeCompare(String(b[1]))),
        ];
        const options = entries.map(([id, name]) => {
            const option = document.createElement('button');
            option.type = 'button';
            option.className = 'filter-option stats-source-option';
            option.setAttribute('role', 'option');
            option.setAttribute('aria-selected', id === selectedSourceId ? 'true' : 'false');
            option.dataset.sourceId = id;
            const label = document.createElement('span');
            label.className = 'filter-option-label';
            label.textContent = name;
            const check = document.createElement('span');
            check.className = 'option-check';
            check.setAttribute('aria-hidden', 'true');
            check.textContent = '✓';
            option.append(label, check);
            return option;
        });
        menu.replaceChildren(...options);
        document.getElementById('statsSourceButtonLabel').textContent =
            entries.find(([id]) => id === selectedSourceId)?.[1]
            || dashboardMessage('source.all');
    }

    function updateSourceOptions(...sourceGroups) {
        const nextSources = new Map();
        sourceGroups.forEach((data) => {
            if (!Array.isArray(data)) return;
            data.forEach((item) => {
                const id = item && (item.source_id || item.id);
                const name = item && (item.source_name || item.display_name || id);
                if (id) {
                    nextSources.set(
                        String(id),
                        String(name),
                    );
                }
            });
        });
        knownSources.clear();
        nextSources.forEach((name, id) => knownSources.set(id, name));
        const selectionReset = Boolean(selectedSourceId && !knownSources.has(selectedSourceId));
        if (selectionReset) {
            selectedSourceId = '';
            persistFilters();
        }
        renderSourceOptions();
        return selectionReset;
    }

    function renderUserOptions() {
        const menu = document.getElementById('statsUserMenu');
        const entries = [
            ['', dashboardMessage('user.all')],
            ...[...knownUsers].sort((a, b) => a.localeCompare(b)).map((name) => [name, name]),
        ];
        const options = entries.map(([name]) => {
            const option = document.createElement('button');
            option.type = 'button';
            option.className = 'filter-option stats-user-option';
            option.setAttribute('role', 'option');
            option.setAttribute('aria-selected', name === selectedUsername ? 'true' : 'false');
            option.dataset.username = name;
            const label = document.createElement('span');
            label.className = 'filter-option-label';
            label.textContent = name || dashboardMessage('user.all');
            const check = document.createElement('span');
            check.className = 'option-check';
            check.setAttribute('aria-hidden', 'true');
            check.textContent = '✓';
            option.append(label, check);
            return option;
        });
        menu.replaceChildren(...options);
        document.getElementById('statsUserButtonLabel').textContent =
            entries.find(([name]) => name === selectedUsername)?.[0]
            || dashboardMessage('user.all');
    }

    async function fetchUserOptions() {
        const response = await fetch('/api/stats/users', fetchOptions);
        if (!response.ok) throw new Error('users request failed');
        const payload = await response.json();
        knownUsers = Array.isArray(payload.users) ? payload.users.map(String) : [];
        renderUserOptions();
    }

    async function fetchDashboardDiagnostics() {
        const response = await fetch('/api/diagnostics', fetchOptions);
        if (!response.ok) throw new Error('diagnostics request failed');
        const payload = await response.json();
        globalHistoryRecordCount = Number.isFinite(Number(payload.history_record_count))
            ? Number(payload.history_record_count)
            : null;
    }

    function currentEmptyStateIsFiltered() {
        if (globalHistoryRecordCount !== null) return globalHistoryRecordCount > 0;
        return knownUsers.length > 0 || Boolean(selectedSourceId || selectedUsername);
    }

    function renderHistoryTable(data, showSources = !selectedSourceId) {
        const tbody = document.getElementById('historyTable');
        tbody.replaceChildren();
        const filteredEmpty = currentEmptyStateIsFiltered();
        const empty = document.getElementById('historyEmpty');
        const emptyLines = empty.querySelectorAll('p');
        if (emptyLines[0]) {
            emptyLines[0].textContent = dashboardMessage(
                filteredEmpty ? 'history.filterEmpty' : 'history.empty',
            );
        }
        if (emptyLines[1]) {
            emptyLines[1].textContent = dashboardMessage(
                filteredEmpty ? 'history.filterEmptyHint' : 'history.emptyHint',
            );
        }
        const rows = beginArrayPanel(
            'history',
            data,
            (items) => items.length > 0,
            dashboardMessage(filteredEmpty ? 'history.filterEmpty' : 'history.empty'),
        );
        if (!rows) return;

        rows.forEach((item) => {
            const tr = document.createElement('tr');
            tr.className = 'history-row';

            const userTd = document.createElement('td');
            userTd.className = 'history-cell history-cell-user';
            const userSpan = document.createElement('span');
            userSpan.className = 'history-user-wrap';
            const avatar = document.createElement('span');
            avatar.className = 'history-avatar';
            avatar.textContent = String(item.username || '?').charAt(0).toUpperCase();
            avatar.setAttribute('aria-hidden', 'true');
            const userMeta = document.createElement('div');
            userMeta.className = 'history-user-meta';
            const userLabel = document.createElement('span');
            userLabel.className = 'history-user-label';
            userLabel.textContent = item.username || '-';
            userMeta.appendChild(userLabel);
            if (showSources) {
                const sourceLabel = createSourceLabel(item);
                if (sourceLabel) userMeta.appendChild(sourceLabel);
            }
            userSpan.appendChild(avatar);
            userSpan.appendChild(userMeta);
            userTd.appendChild(userSpan);

            const titleTd = document.createElement('td');
            titleTd.className = 'history-cell history-cell-title';
            const titleWrap = document.createElement('div');
            titleWrap.className = 'history-title-wrap';
            const trackCover = createCoverImage({
                sourceId: item.source_id,
                id: item.track_id,
                className: 'history-cover',
            });
            if (trackCover) titleWrap.appendChild(trackCover);
            const titleDiv = document.createElement('div');
            titleDiv.className = 'history-primary';
            titleDiv.textContent = item.title || '-';
            titleDiv.title = item.title || '';
            titleWrap.appendChild(titleDiv);
            titleTd.appendChild(titleWrap);

            const artistTd = document.createElement('td');
            artistTd.className = 'history-cell history-cell-artist';
            artistTd.textContent = item.artist || '-';
            artistTd.title = item.artist || '';

            const albumTd = document.createElement('td');
            albumTd.className = 'history-cell history-cell-album';
            albumTd.textContent = item.album || '-';
            albumTd.title = item.album || '';

            const playedTd = document.createElement('td');
            playedTd.className = 'history-cell history-cell-played';
            playedTd.textContent = formatPlayedAt(item.last_played_at);

            const countTd = document.createElement('td');
            countTd.className = 'history-cell history-cell-count';
            const badge = document.createElement('span');
            badge.className = 'history-count-badge stat-value';
            badge.textContent = String(item.play_count ?? 0);
            countTd.appendChild(badge);

            tr.appendChild(userTd);
            tr.appendChild(titleTd);
            tr.appendChild(artistTd);
            tr.appendChild(albumTd);
            tr.appendChild(playedTd);
            tr.appendChild(countTd);
            tbody.appendChild(tr);
        });
        setPanelSummary('history', dashboardMessage('aria.historySummary', {
            count: dashboardNumber(rows.length),
        }));
        applyHistoryColumns(historyColumns);
    }

    function updateNewUserGuide(snapshot) {
        const summary = snapshot && snapshot.summary;
        const noPlays = summary && Number(summary.total_plays) === 0;
        const noHistory = Array.isArray(snapshot && snapshot.history)
            && snapshot.history.length === 0;
        document.getElementById('newUserGuide').classList.toggle(
            'hidden',
            !(noPlays && noHistory && !currentEmptyStateIsFiltered()),
        );
    }

    let lastStatsSnapshot = null;
    let lastRankingMetric = 'plays';

    function renderStatPanels(snapshot) {
        renderPanelSafely('summary', () => updateSummary(snapshot.summary, snapshot.transcoding));
        renderPanelSafely('players', () => renderPlayerChart(snapshot.players));
        renderPanelSafely('transcoding', () => renderTranscodingChart(snapshot.transcoding));
        renderPanelSafely('hourly', () => renderHourlyChart(snapshot.hourly));
        renderPanelSafely('daily', () => renderDailyChart(snapshot.daily));
        renderPanelSafely('heatmap', () => renderWeekdayHourChart(snapshot.heatmap));
        renderPanelSafely('artists', () => renderTopArtistsChart(snapshot.top_artists, lastRankingMetric));
        renderPanelSafely('albums', () => renderTopAlbumsChart(snapshot.top_albums, lastRankingMetric));
        renderPanelSafely('history', () => renderHistoryTable(snapshot.history, !selectedSourceId));
        renderPanelSafely('sources', () => renderServerSourceBreakdown(snapshot.servers));
    }

    async function fetchStats() {
        const requestState = captureStatsRequestState();
        const generation = ++statsRequestGeneration;
        if (statsRequestController) statsRequestController.abort();
        const controller = new AbortController();
        statsRequestController = controller;
        let sourceSelectionReset = false;
        setLoading(true);
        setStatus('loading', dashboardMessage('status.syncing'));

        try {
            const query = buildStatsQuery({
                days: requestState.days,
                timezone: requestState.timezone,
                metric: requestState.metric,
                sourceId: requestState.sourceId,
                username: requestState.username,
                startDate: requestState.startDate,
                endDate: requestState.endDate,
            });
            const snapshotRes = await fetch(`/api/stats/dashboard?${query}`, {
                ...fetchOptions,
                signal: controller.signal,
            });
            if (generation !== statsRequestGeneration || controller.signal.aborted) return;
            if (snapshotRes.status === 401) {
                showLogin(dashboardMessage('auth.expired'));
                return;
            }
            if (!snapshotRes.ok) {
                throw new Error('statistics request failed (' + snapshotRes.status + ')');
            }
            const snapshot = await snapshotRes.json();
            if (generation !== statsRequestGeneration || controller.signal.aborted) return;
            if (
                Number(snapshot.summary?.total_plays) > 0
                || (Array.isArray(snapshot.history) && snapshot.history.length > 0)
            ) {
                globalHistoryRecordCount = Math.max(globalHistoryRecordCount ?? 0, 1);
            }
            lastStatsSnapshot = snapshot;
            lastRankingMetric = requestState.metric;
            // Sources feed the cover-art URLs, so refresh them before rendering.
            sourceSelectionReset = updateSourceOptions(
                snapshot.available_servers,
                snapshot.servers,
            );
            renderStatPanels(snapshot);
            updateNewUserGuide(snapshot);
            window.requestAnimationFrame(resizeDashboardCharts);

            hasLoadedOnce = true;
            hideError();
            setStatus('ok', dashboardMessage('status.live'));
            const now = new Date();
            document.getElementById('lastUpdated').textContent = dashboardMessage('status.lastUpdated', {
                time: now.toLocaleTimeString(dashboardI18n.getLocale(), {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                }),
            });
        } catch (error) {
            if (isAbortError(error) || generation !== statsRequestGeneration) return;
            setStatus('error', dashboardMessage('status.connectionError'));
            showError(dashboardMessage('error.stats', {
                stale: hasLoadedOnce ? dashboardMessage('error.stale') : '',
            }));
            if (!hasLoadedOnce) {
                STATS_PANEL_NAMES.forEach((name) => (
                    setPanelState(name, 'error', dashboardMessage('error.section'))
                ));
            }
            console.error('Error fetching data:', error);
        } finally {
            if (generation === statsRequestGeneration) {
                setLoading(false);
                statsRequestController = null;
                if (sourceSelectionReset) {
                    window.queueMicrotask(() => {
                        fetchStats();
                        fetchNowPlaying();
                    });
                }
            }
        }
    }

    async function fetchNowPlaying() {
        const requestState = captureNowPlayingRequestState();
        const generation = ++nowPlayingRequestGeneration;
        if (nowPlayingRequestController) nowPlayingRequestController.abort();
        const controller = new AbortController();
        nowPlayingRequestController = controller;
        stopNowPlayingTicker();
        if (!nowPlayingLoadedOnce) setPanelState('nowPlaying', 'loading');
        try {
            const sourceParam = requestState.sourceId
                ? `?source_id=${encodeURIComponent(requestState.sourceId)}`
                : '';
            const response = await fetch(`/api/stats/now-playing${sourceParam}`, {
                ...fetchOptions,
                signal: controller.signal,
            });
            if (generation !== nowPlayingRequestGeneration || controller.signal.aborted) return;
            if (response.status === 401) {
                showLogin(dashboardMessage('auth.expired'));
                return;
            }
            if (!response.ok) throw new Error('now-playing request failed');
            const payload = await response.json();
            if (generation !== nowPlayingRequestGeneration || controller.signal.aborted) return;
            const visible = requestState.username
                ? payload.filter((item) => item.username === requestState.username)
                : payload;
            renderNowPlaying(visible, !requestState.sourceId);
            if (Array.isArray(payload)) nowPlayingLoadedOnce = true;
        } catch (error) {
            if (isAbortError(error) || generation !== nowPlayingRequestGeneration) return;
            console.error('Error fetching now playing:', error);
            stopNowPlayingTicker();
            setPanelState('nowPlaying', 'error', dashboardMessage('error.nowPlaying'));
        } finally {
            if (generation === nowPlayingRequestGeneration) {
                nowPlayingRequestController = null;
            }
        }
    }

    function scheduleRefresh() {
        stopRefreshTimers();
        if (!document.getElementById('loginOverlay').classList.contains('hidden')) return;
        refreshTimer = setInterval(
            fetchStats,
            document.hidden ? HIDDEN_REFRESH_MS : REFRESH_MS,
        );
        if (!document.hidden) {
            nowPlayingRefreshTimer = setInterval(
                fetchNowPlaying,
                NOW_PLAYING_REFRESH_MS,
            );
        }
    }

    function setActiveRankingMetric(metric) {
        const label = metric === 'listen_time'
            ? dashboardMessage('ranking.byListening')
            : dashboardMessage('ranking.byPlays');
        document.querySelectorAll('.ranking-metric-btn').forEach((btn) => {
            const active = btn.dataset.rankingMetric === metric;
            btn.setAttribute('aria-pressed', active ? 'true' : 'false');
            btn.classList.toggle('bg-accent', active);
            btn.classList.toggle('text-white', active);
            btn.classList.toggle('text-slate-400', !active);
        });
        ['topArtistsSubtitle', 'topAlbumsSubtitle'].forEach((id) => {
            const element = document.getElementById(id);
            if (element) element.textContent = label;
        });
    }

    async function fetchRankings() {
        await fetchStats();
    }

    function statsWindowLabel() {
        if (customStartDate && customEndDate) {
            return `${customStartDate} — ${customEndDate}`;
        }
        return statsDays === 0
            ? dashboardMessage('window.allLabel')
            : dashboardMessage('window.daysLabel', { days: statsDays });
    }

    function setActiveStatsWindowButton(days) {
        document.querySelectorAll('.stats-window-option').forEach((btn) => {
            const active = Number(btn.dataset.days) === days;
            btn.setAttribute(
                'aria-selected',
                active && !customStartDate ? 'true' : 'false',
            );
        });
        document.getElementById('customRangeOption').setAttribute(
            'aria-selected',
            customStartDate && customEndDate ? 'true' : 'false',
        );
        document.getElementById('statsWindowButtonLabel').textContent = statsWindowLabel();
        const scope = document.getElementById('statsScopeLabel');
        if (scope) scope.textContent = statsWindowLabel();
        const dailySubtitle = document.getElementById('dailyChartSubtitle');
        if (dailySubtitle) {
            dailySubtitle.textContent = dashboardMessage('daily.subtitle', {
                window: statsWindowLabel(),
            });
        }
    }

    const windowListbox = createListbox({
        trigger: document.getElementById('statsWindowButton'),
        menu: document.getElementById('statsWindowMenu'),
        onSelect: (option) => {
            if (option.dataset.range === 'custom') {
                document.getElementById('customStartDate').focus();
                return false;
            }
            const days = Number(option.dataset.days);
            if (!Number.isFinite(days)) return false;
            const changed = days !== statsDays || customStartDate || customEndDate;
            statsDays = days;
            customStartDate = '';
            customEndDate = '';
            persistFilters();
            setActiveStatsWindowButton(days);
            if (changed) fetchStats();
        },
    });

    const sourceListbox = createListbox({
        trigger: document.getElementById('statsSourceButton'),
        menu: document.getElementById('statsSourceMenu'),
        onSelect: (option) => {
            const id = option.dataset.sourceId ?? '';
            if (selectedSourceId === id) return;
            selectedSourceId = id;
            persistFilters();
            renderSourceOptions();
            fetchStats();
            fetchNowPlaying();
        },
    });

    const userListbox = createListbox({
        trigger: document.getElementById('statsUserButton'),
        menu: document.getElementById('statsUserMenu'),
        onSelect: (option) => {
            const name = option.dataset.username ?? '';
            if (selectedUsername === name) return;
            selectedUsername = name;
            persistFilters();
            renderUserOptions();
            fetchStats();
            fetchNowPlaying();
        },
    });

    document.getElementById('customRangeCancel').addEventListener('click', () => {
        document.getElementById('customRangeError').classList.add('hidden');
        windowListbox.setOpen(false, { restoreFocus: true });
    });
    document.getElementById('customRangeApply').addEventListener('click', () => {
        const start = document.getElementById('customStartDate').value;
        const end = document.getElementById('customEndDate').value;
        const error = document.getElementById('customRangeError');
        const validation = validateCustomRange(start, end);
        const message = validation.ok ? '' : dashboardMessage(validation.reason);
        if (message) {
            error.textContent = message;
            error.classList.remove('hidden');
            return;
        }
        error.classList.add('hidden');
        customStartDate = start;
        customEndDate = end;
        persistFilters();
        setActiveStatsWindowButton(statsDays);
        windowListbox.setOpen(false, { restoreFocus: true });
        fetchStats();
    });

    setActiveStatsWindowButton(statsDays);
    setupHistoryColumns();
    updateSourceOptions([]);
    renderUserOptions();

    document.querySelectorAll('.ranking-metric-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            const metric = btn.dataset.rankingMetric;
            if (metric !== 'plays' && metric !== 'listen_time') return;
            if (metric === rankingMetric) return;
            rankingMetric = metric;
            persistFilters();
            setActiveRankingMetric(metric);
            fetchRankings();
        });
    });
    setActiveRankingMetric(rankingMetric);

    document.getElementById('refreshBtn').addEventListener('click', () => {
        fetchStats();
        fetchNowPlaying();
    });

    document.getElementById('loginForm').addEventListener('submit', async (event) => {
        event.preventDefault();
        const token = document.getElementById('loginToken').value;
        try {
            await submitLogin(token);
            document.getElementById('loginToken').value = '';
        } catch (error) {
            showLogin(dashboardMessage('auth.invalid'));
        }
    });

    document.getElementById('loginOverlay').addEventListener('keydown', (event) => {
        if (event.key !== 'Tab') return;
        const focusable = [...event.currentTarget.querySelectorAll('input, button')]
            .filter(element => !element.disabled && !element.hidden);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });

    document.addEventListener('visibilitychange', () => {
        scheduleRefresh();
        if (document.hidden) {
            stopNowPlayingTicker();
        } else if (document.getElementById('loginOverlay').classList.contains('hidden')) {
            startNowPlayingTicker();
            fetchStats();
            fetchNowPlaying();
        }
    });

    window.addEventListener('storage', (event) => {
        if (event.key !== 'navidrome-language') return;
        refreshDashboardLanguage();
        fetchStats();
        fetchNowPlaying();
    });

    window.addEventListener('resize', resizeDashboardCharts);

    async function bootstrap() {
        try {
            applyAppVersion();
            const statusRes = await fetch('/api/auth/status', fetchOptions);
            if (statusRes.ok) {
                const statusData = await statusRes.json();
                authRequired = Boolean(statusData.auth_required);
            }
        } catch (error) {
            console.warn('Unable to read auth status', error);
        }

        if (authRequired) {
            const probe = await fetch('/api/stats/dashboard?days=30', fetchOptions);
            if (probe.status === 401) {
                showLogin();
                return;
            }
        }

        await Promise.all([
            Promise.allSettled([fetchUserOptions(), fetchDashboardDiagnostics()]),
            fetchStats(),
            fetchNowPlaying(),
        ]);
        if (lastStatsSnapshot) {
            renderHistoryTable(lastStatsSnapshot.history, !selectedSourceId);
            updateNewUserGuide(lastStatsSnapshot);
        }
        scheduleRefresh();
    }

    bootstrap();
