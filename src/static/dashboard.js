import { pageMessages } from './js/i18n/index.js';
import { createI18n } from './localization.js';
import { applyAppVersion } from './js/app-info.js';
import {
    buildStatsQuery,
    formatDuration,
    formatPreciseDuration,
    validateCustomRange,
} from './js/format.js';
import { readPreference } from './js/prefs.js';
import { createListbox } from './js/listbox.js';
import { getFilters, setFilters } from './js/filters.js';
import { THEME_CHANGE_EVENT } from './theme-bootstrap.js';
import { createLoginController } from './js/auth.js';
import { createNowPlaying } from './js/dashboard/now-playing.js';
import { createHistory } from './js/dashboard/history.js';
import { createPlayAccounting } from './js/dashboard/play-accounting.js';
import { createHistoricalDashboard } from './js/dashboard/historical-dashboard.js';
import { createEntityDetail } from './js/dashboard/entity-detail.js';
import { createDataRelations } from './js/dashboard/data-relations.js';
import {
    apiFetch,
    isAbortError,
    UnauthorizedError,
    UNAUTHORIZED_EVENT,
} from './js/http.js';


    const REFRESH_MS = 60000;
    const HIDDEN_REFRESH_MS = 300000;
    const NOW_PLAYING_REFRESH_MS = 10000;
    let statsRequestController = null;
    let statsRequestGeneration = 0;
    let refreshTimer = null;
    let nowPlayingRefreshTimer = null;
    let hasLoadedOnce = false;
    let authRequired = false;
    const initialFilters = getFilters();
    let statsDays = initialFilters.days;
    let customStartDate = initialFilters.startDate;
    let customEndDate = initialFilters.endDate;
    let selectedSourceId = initialFilters.sourceId;
    let selectedUsername = initialFilters.username;
    let selectedRelationDimension = initialFilters.relationDimension;
    const knownSources = new Map();
    let knownUsers = [];
    let globalHistoryRecordCount = null;
    let entityDetail = null;
    let historicalDashboard = null;
    let dataRelations = null;
    // Shared by the artist and album rankings; changing it refreshes both.
    let rankingMetric = initialFilters.metric;

    // Keep the shareable URL in sync whenever a filter changes.
    function persistFilters() {
        setFilters({
            days: statsDays,
            timezone: getFilters().entityType ? resolveStatsTimezone() : statsTimezone,
            metric: rankingMetric,
            sourceId: selectedSourceId,
            username: selectedUsername,
            startDate: customStartDate,
            endDate: customEndDate,
            relationDimension: selectedRelationDimension,
        });
        syncReviewLink();
    }

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
        if (selectedUsername) params.set('username', selectedUsername);
        link.href = `/review?${params.toString()}`;
    }
    syncReviewLink();

    function stopRefreshTimers() {
        if (refreshTimer) clearInterval(refreshTimer);
        if (nowPlayingRefreshTimer) clearInterval(nowPlayingRefreshTimer);
        refreshTimer = null;
        nowPlayingRefreshTimer = null;
    }

    function cancelDashboardRequests() {
        statsRequestGeneration += 1;
        if (statsRequestController) statsRequestController.abort();
        statsRequestController = null;
        nowPlaying.cancel();
        playAccounting.cancel();
        entityDetail?.cancel();
        dataRelations?.cancel();
    }

    function stopDashboardActivity() {
        stopRefreshTimers();
        nowPlaying.stopTicker();
        cancelDashboardRequests();
        setLoading(false);
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

    async function refreshAfterLogin() {
        applyAppVersion();
        await Promise.all([
            Promise.allSettled([fetchUserOptions(), fetchDashboardDiagnostics()]),
            fetchStats(),
            nowPlaying.refresh(),
        ]);
        if (lastStatsSnapshot) {
            history.render(lastStatsSnapshot.history, { showSources: !selectedSourceId });
            history.updateFirstUse(lastStatsSnapshot);
        }
        entityDetail?.restore();
        if (document.getElementById('loginOverlay').classList.contains('hidden')) {
            scheduleRefresh();
        }
    }

    const login = createLoginController({
        overlayId: 'loginOverlay',
        tokenId: 'loginToken',
        inertSelector: '#dashboardApp',
        useHiddenClass: true,
        onShow: () => {
            stopDashboardActivity();
            setStatus('error', dashboardMessage('auth.required'));
        },
        onAuthenticated: refreshAfterLogin,
    });

    function showLogin(message) {
        login.show(message);
    }

    function applyChartTheme() {
        historicalDashboard?.updateTheme();
        entityDetail?.updateTheme();
        dataRelations?.updateTheme();
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
        return formatDuration(seconds, dashboardMessage);
    }
    function dashboardPreciseDuration(seconds) {
        return formatPreciseDuration(seconds, dashboardMessage);
    }
    const playAccounting = createPlayAccounting({
        apiFetch,
        isAbortError,
        t: dashboardMessage,
        formatNumber: dashboardNumber,
        getScope: captureStatsRequestState,
    });
    function refreshDashboardLanguage() {
        translateDashboard();
        setStatus('loading', dashboardMessage('status.syncing'));
        setActiveStatsWindowButton(statsDays);
        setActiveRankingMetric(rankingMetric);
        renderSourceOptions();
        renderUserOptions();
        history.localize();
        playAccounting.localize();
        entityDetail?.localize();
        dataRelations?.localize();
    }
    translateDashboard();
    window.addEventListener(UNAUTHORIZED_EVENT, () => {
        showLogin(hasLoadedOnce ? dashboardMessage('auth.expired') : undefined);
    });

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
        'heatmap', 'relationTrend', 'relationMatrix', 'relationComparison',
        'artists', 'albums', 'sources', 'history',
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
        relationTrend: {
            wrap: 'relationTrendChartWrap',
            skeleton: 'relationTrendChartSkeleton',
            contents: [{ id: 'relationTrendChart', hide: 'visibility' }],
            empty: 'relationTrendChartEmpty',
            error: 'relationTrendChartError',
            summary: 'relationTrendChartSummary',
        },
        relationMatrix: {
            wrap: 'relationMatrixChartWrap',
            skeleton: 'relationMatrixChartSkeleton',
            contents: [{ id: 'relationMatrixChart', hide: 'visibility' }],
            empty: 'relationMatrixChartEmpty',
            error: 'relationMatrixChartError',
            summary: 'relationMatrixChartSummary',
        },
        relationComparison: {
            wrap: 'relationComparisonChartWrap',
            skeleton: 'relationComparisonChartSkeleton',
            contents: [{ id: 'relationComparisonChart', hide: 'visibility' }],
            empty: 'relationComparisonChartEmpty',
            error: 'relationComparisonChartError',
            summary: 'relationComparisonChartSummary',
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

    const nowPlaying = createNowPlaying({
        apiFetch,
        isAbortError,
        t: dashboardMessage,
        formatNumber: dashboardNumber,
        getScope: () => ({ sourceId: selectedSourceId, username: selectedUsername }),
        setPanelState,
        setPanelSummary,
    });
    const history = createHistory({
        t: dashboardMessage,
        formatNumber: dashboardNumber,
        getLocale: () => dashboardI18n.getLocale(),
        isFiltered: currentEmptyStateIsFiltered,
        beginArrayPanel,
        setPanelSummary,
    });
    entityDetail = createEntityDetail({
        apiFetch,
        isAbortError,
        t: dashboardMessage,
        formatNumber: dashboardNumber,
        formatDuration: dashboardDuration,
        formatPreciseDuration: dashboardPreciseDuration,
        formatPlays: dashboardPlays,
        getLocale: () => dashboardI18n.getLocale(),
        getScope: captureStatsRequestState,
        getScopeContext: () => ({
            windowLabel: statsWindowLabel(),
            metricLabel: dashboardMessage(
                rankingMetric === 'listen_time' ? 'metric.listenTime' : 'metric.plays',
            ),
            sourceLabel: selectedSourceId
                ? (knownSources.get(selectedSourceId) || selectedSourceId)
                : dashboardMessage('source.all'),
            userLabel: selectedUsername || dashboardMessage('user.all'),
            timezoneLabel: resolveStatsTimezone(),
        }),
        getFallbackSourceId: firstKnownSourceId,
    });
    historicalDashboard = createHistoricalDashboard({
        t: dashboardMessage,
        formatNumber: dashboardNumber,
        formatDuration: dashboardDuration,
        formatPreciseDuration: dashboardPreciseDuration,
        formatPlays: dashboardPlays,
        beginArrayPanel,
        setPanelState,
        setPanelSummary,
        renderSafely: renderPanelSafely,
        getSourceId: () => selectedSourceId,
        getFirstSourceId: firstKnownSourceId,
        onEntitySelect: (identity, trigger) => entityDetail.open(identity, trigger),
    });
    dataRelations = createDataRelations({
        apiFetch,
        isAbortError,
        t: dashboardMessage,
        formatNumber: dashboardNumber,
        formatDuration: dashboardDuration,
        formatPlays: dashboardPlays,
        getLocale: () => dashboardI18n.getLocale(),
        getScope: captureStatsRequestState,
        getWindowLabel: statsWindowLabel,
        getDimension: () => selectedRelationDimension,
        onDimensionChange: (dimension) => {
            selectedRelationDimension = dimension;
            persistFilters();
        },
        onEntitySelect: (identity, trigger) => entityDetail.open(identity, trigger),
        setPanelState,
        setPanelSummary,
    });

    function firstKnownSourceId() {
        for (const id of knownSources.keys()) return id;
        return '';
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
        const response = await apiFetch('/api/stats/users');
        if (!response.ok) throw new Error('users request failed');
        const payload = await response.json();
        knownUsers = Array.isArray(payload.users) ? payload.users.map(String) : [];
        renderUserOptions();
    }

    async function fetchDashboardDiagnostics() {
        const response = await apiFetch('/api/diagnostics');
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

    let lastStatsSnapshot = null;
    let lastRankingMetric = 'plays';

    function renderStatPanels(snapshot) {
        historicalDashboard.render(snapshot, lastRankingMetric);
        renderPanelSafely('history', () => history.render(
            snapshot.history,
            { showSources: !selectedSourceId },
        ));
    }

    async function fetchStats() {
        const requestState = captureStatsRequestState();
        if (playAccounting.isOpen()) playAccounting.refresh({ force: true });
        const generation = ++statsRequestGeneration;
        if (statsRequestController) statsRequestController.abort();
        const controller = new AbortController();
        statsRequestController = controller;
        let sourceSelectionReset = false;
        setLoading(true);
        setStatus('loading', dashboardMessage('status.syncing'));
        dataRelations.refresh({ scope: requestState });

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
            const snapshotRes = await apiFetch(`/api/stats/dashboard?${query}`, {
                signal: controller.signal,
            });
            if (generation !== statsRequestGeneration || controller.signal.aborted) return;
            if (!snapshotRes.ok) {
                throw new Error('statistics request failed (' + snapshotRes.status + ')');
            }
            const snapshot = await snapshotRes.json();
            if (generation !== statsRequestGeneration || controller.signal.aborted) return;
            playAccounting.invalidate();
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
            history.updateFirstUse(snapshot);
            window.requestAnimationFrame(historicalDashboard.resize);

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
                        nowPlaying.refresh();
                    });
                }
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
                nowPlaying.refresh,
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
        dataRelations?.sync();
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
            nowPlaying.refresh();
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
            nowPlaying.refresh();
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
    playAccounting.mount();
    history.mount();
    entityDetail.mount();
    dataRelations.mount();
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
        nowPlaying.refresh();
        entityDetail.refresh();
    });

    document.getElementById('loginForm').addEventListener('submit', async (event) => {
        event.preventDefault();
        const token = document.getElementById('loginToken').value;
        try {
            await login.submit(token);
            document.getElementById('loginToken').value = '';
        } catch (error) {
            showLogin(dashboardMessage('auth.invalid'));
        }
    });

    login.bind();

    document.addEventListener('visibilitychange', () => {
        scheduleRefresh();
        if (document.hidden) {
            nowPlaying.stopTicker();
        } else if (document.getElementById('loginOverlay').classList.contains('hidden')) {
            nowPlaying.startTicker();
            fetchStats();
            nowPlaying.refresh();
            entityDetail.refresh();
        }
    });

    window.addEventListener('storage', (event) => {
        if (event.key !== 'navidrome-language') return;
        refreshDashboardLanguage();
        fetchStats();
        nowPlaying.refresh();
    });

    window.addEventListener('resize', () => {
        historicalDashboard.resize();
        dataRelations.resize();
    });

    async function bootstrap() {
        try {
            applyAppVersion();
            const statusRes = await apiFetch('/api/auth/status');
            if (statusRes.ok) {
                const statusData = await statusRes.json();
                authRequired = Boolean(statusData.auth_required);
            }
        } catch (error) {
            if (error instanceof UnauthorizedError) return;
            console.warn('Unable to read auth status', error);
        }

        if (authRequired) {
            try {
                await apiFetch('/api/stats/dashboard?days=30');
            } catch (error) {
                if (error instanceof UnauthorizedError) return;
                throw error;
            }
            if (!login.isHidden()) {
                return;
            }
        }

        await Promise.all([
            Promise.allSettled([fetchUserOptions(), fetchDashboardDiagnostics()]),
            fetchStats(),
            nowPlaying.refresh(),
        ]);
        if (lastStatsSnapshot) {
            history.render(lastStatsSnapshot.history, { showSources: !selectedSourceId });
            history.updateFirstUse(lastStatsSnapshot);
        }
        entityDetail.restore();
        scheduleRefresh();
    }

    bootstrap();
