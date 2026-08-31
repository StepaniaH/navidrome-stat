import { createThemeTokens } from '../charts.js';
import { buildStatsQuery, coverArtUrl } from '../format.js';
import {
    getFilters,
    pushFilters,
    setFilters,
    subscribe,
} from '../filters.js';

const EMPTY_ENTITY = Object.freeze({
    entityType: '',
    entityName: '',
    entityId: '',
    entitySourceId: '',
    entityArtist: '',
});

function identityFromFilters(filters) {
    if (!filters.entityType || !filters.entityName) return null;
    return {
        type: filters.entityType,
        name: filters.entityName,
        id: filters.entityId || '',
        sourceId: filters.entitySourceId || '',
        artist: filters.entityArtist || '',
    };
}

function identityPatch(identity) {
    return {
        entityType: identity.type,
        entityName: identity.name,
        entityId: identity.id || '',
        entitySourceId: identity.sourceId || '',
        entityArtist: identity.artist || '',
    };
}

function appendText(parent, className, text) {
    const element = document.createElement('span');
    element.className = className;
    element.textContent = text;
    parent.appendChild(element);
    return element;
}

/** Own the URL-addressable artist, album, and client detail dialog. */
export function createEntityDetail({
    apiFetch,
    isAbortError,
    t,
    formatNumber,
    formatDuration,
    formatPreciseDuration,
    formatPlays,
    getLocale,
    getScope,
    getScopeContext,
    getFallbackSourceId,
}) {
    const layer = document.getElementById('entityDetailLayer');
    const panel = document.getElementById('entityDetailPanel');
    const loading = document.getElementById('entityDetailLoading');
    const error = document.getElementById('entityDetailError');
    const content = document.getElementById('entityDetailContent');
    let requestController = null;
    let requestGeneration = 0;
    let trendChart = null;
    let currentIdentity = null;
    let lastPayload = null;
    let lastFocused = null;
    let unsubscribe = null;
    let copyResetTimer = null;
    let mounted = false;

    function ensureTrendChart() {
        if (!trendChart) {
            trendChart = echarts.init(
                document.getElementById('entityTrendChart'),
                null,
                { renderer: 'canvas' },
            );
        }
        return trendChart;
    }

    function setState(state, message = '') {
        loading.classList.toggle('hidden', state !== 'loading');
        error.classList.toggle('hidden', state !== 'error');
        content.classList.toggle('hidden', state !== 'ready');
        panel.setAttribute('aria-busy', state === 'loading' ? 'true' : 'false');
        if (state === 'error') {
            document.getElementById('entityDetailErrorText').textContent = (
                message || t('entity.loadError')
            );
        }
    }

    function formatDateTime(value) {
        if (!value) return '—';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        try {
            return new Intl.DateTimeFormat(getLocale(), {
                dateStyle: 'medium',
                timeStyle: 'short',
                timeZone: getScope().timezone,
            }).format(date);
        } catch (_error) {
            return date.toLocaleString();
        }
    }

    function renderCover(identity, entityId = identity.id) {
        const cover = document.getElementById('entityDetailCover');
        const fallback = document.createElement('span');
        fallback.id = 'entityDetailCoverFallback';
        fallback.textContent = identity.name.trim().charAt(0).toUpperCase() || '?';
        cover.replaceChildren(fallback);
        const sourceId = identity.sourceId || getScope().sourceId || getFallbackSourceId();
        if (!sourceId || !entityId) return;
        const image = document.createElement('img');
        image.alt = '';
        image.src = coverArtUrl({ sourceId, id: entityId, size: 300 });
        image.addEventListener('error', () => image.replaceWith(fallback));
        cover.replaceChildren(image);
    }

    function renderScope() {
        const scope = document.getElementById('entityDetailScope');
        const context = getScopeContext();
        const labels = [
            context.windowLabel,
            context.metricLabel,
            context.sourceLabel,
            context.userLabel,
            context.timezoneLabel,
        ].filter(Boolean);
        scope.replaceChildren(...labels.map((text) => {
            const chip = document.createElement('span');
            chip.className = 'entity-scope-chip';
            chip.textContent = text;
            chip.title = text;
            return chip;
        }));
    }

    function renderIdentity(identity, payload = null) {
        const typeKey = identity.type === 'album'
            ? 'entity.album'
            : identity.type === 'client'
                ? 'entity.client'
                : 'entity.artist';
        const type = t(typeKey);
        document.getElementById('entityDetailType').textContent = t('entity.detailType', { type });
        document.getElementById('entityDetailName').textContent = identity.name;
        const artist = document.getElementById('entityDetailArtist');
        const artistName = payload?.artist || identity.artist;
        artist.textContent = artistName || '';
        artist.classList.toggle('hidden', !artistName || identity.type !== 'album');
        renderScope();
        renderCover(identity, payload?.entity_id || identity.id);
    }

    function renderRank(payload) {
        document.getElementById('entityDetailCurrentRank').textContent = (
            payload.current_rank == null ? '—' : `#${formatNumber(payload.current_rank)}`
        );
        const change = document.getElementById('entityDetailRankChange');
        const previous = document.getElementById('entityDetailPreviousRank');
        if (!payload.comparison_available) {
            change.textContent = t('entity.rankNoComparison');
            previous.textContent = '';
            return;
        }
        if (payload.previous_rank == null) {
            change.textContent = t('entity.rankNew');
            previous.textContent = '';
            return;
        }
        const delta = Number(payload.rank_change) || 0;
        if (delta > 0) change.textContent = t('entity.rankUp', { count: formatNumber(delta) });
        else if (delta < 0) change.textContent = t('entity.rankDown', { count: formatNumber(Math.abs(delta)) });
        else change.textContent = t('entity.rankSame');
        previous.textContent = t('entity.previousRank', {
            rank: formatNumber(payload.previous_rank),
        });
    }

    function renderTrend(payload) {
        const rows = Array.isArray(payload.trend) ? payload.trend : [];
        const chartElement = document.getElementById('entityTrendChart');
        const empty = document.getElementById('entityTrendEmpty');
        chartElement.classList.toggle('hidden', rows.length === 0);
        empty.classList.toggle('hidden', rows.length > 0);
        if (!rows.length) {
            if (trendChart) trendChart.clear();
            document.getElementById('entityTrendSummary').textContent = t('entity.trendEmpty');
            return;
        }
        const chart = ensureTrendChart();
        const theme = createThemeTokens();
        chart.setOption({
            animation: document.documentElement.dataset.motion !== 'reduced',
            color: [theme.palette[0], theme.palette[2] || theme.palette[1]],
            textStyle: theme.base.textStyle,
            tooltip: {
                ...theme.base.tooltip,
                trigger: 'axis',
                formatter(params) {
                    const items = Array.isArray(params) ? params : [params];
                    const date = items[0]?.axisValueLabel || '';
                    const plays = items.find((item) => item.seriesName === t('metric.plays'))?.value || 0;
                    const listen = items.find((item) => item.seriesName === t('metric.listenTime'))?.value || 0;
                    return `${date}<br>${t('metric.plays')}: ${formatNumber(plays)}<br>${t('metric.listenTime')}: ${formatDuration(listen)}`;
                },
            },
            legend: {
                top: 0,
                textStyle: { color: theme.axisText, fontSize: 11 },
            },
            grid: { left: 44, right: 52, top: 38, bottom: 30 },
            xAxis: {
                type: 'category',
                data: rows.map((row) => row.date),
                boundaryGap: false,
                axisLine: { lineStyle: { color: theme.axisLine } },
                axisLabel: { color: theme.axisText, fontSize: 10, hideOverlap: true },
            },
            yAxis: [
                {
                    type: 'value',
                    minInterval: 1,
                    axisLabel: { color: theme.axisText, fontSize: 10 },
                    splitLine: { lineStyle: { color: theme.gridLine } },
                },
                {
                    type: 'value',
                    axisLabel: {
                        color: theme.axisText,
                        fontSize: 10,
                        formatter: (value) => formatDuration(value),
                    },
                    splitLine: { show: false },
                },
            ],
            series: [
                {
                    name: t('metric.plays'),
                    type: 'line',
                    smooth: true,
                    symbol: rows.length <= 31 ? 'circle' : 'none',
                    symbolSize: 5,
                    lineStyle: { width: 2 },
                    areaStyle: { opacity: 0.08 },
                    data: rows.map((row) => Number(row.play_count) || 0),
                },
                {
                    name: t('metric.listenTime'),
                    type: 'line',
                    yAxisIndex: 1,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1.5, type: 'dashed' },
                    data: rows.map((row) => Number(row.total_listen_sec) || 0),
                },
            ],
        }, true);
        window.requestAnimationFrame(() => chart.resize());
        document.getElementById('entityTrendSummary').textContent = t('entity.trendSummary', {
            days: formatNumber(rows.length),
            plays: formatNumber(payload.total_plays),
            duration: formatDuration(payload.total_listen_sec),
        });
    }

    function renderTopTracks(payload) {
        const container = document.getElementById('entityTopTracks');
        const empty = document.getElementById('entityTopTracksEmpty');
        const rows = Array.isArray(payload.top_tracks) ? payload.top_tracks : [];
        container.replaceChildren();
        empty.classList.toggle('hidden', rows.length > 0);
        rows.forEach((item, index) => {
            const row = document.createElement('li');
            row.className = 'entity-detail-list-item';
            appendText(row, 'entity-list-rank stat-value', String(index + 1));
            const copy = document.createElement('div');
            copy.className = 'entity-list-copy';
            const title = appendText(
                copy,
                'entity-list-title',
                item.title || t('entity.unknownTrack'),
            );
            title.title = title.textContent;
            const contextFields = currentIdentity?.type === 'client'
                ? [item.artist, item.album, item.source_name]
                : [item.album, item.source_name];
            const context = contextFields.filter(Boolean).join(' · ');
            if (context) appendText(copy, 'entity-list-context', context);
            if (item.last_played_at) {
                appendText(copy, 'entity-list-meta', t('entity.lastPlayedAt', {
                    time: formatDateTime(item.last_played_at),
                }));
            }
            const value = document.createElement('span');
            value.className = 'entity-list-value stat-value';
            value.textContent = `${formatPlays(item.play_count)} · ${formatDuration(item.total_listen_sec)}`;
            row.append(copy, value);
            container.appendChild(row);
        });
    }

    function renderRecentPlays(payload) {
        const container = document.getElementById('entityRecentPlays');
        const empty = document.getElementById('entityRecentPlaysEmpty');
        const rows = Array.isArray(payload.recent_plays) ? payload.recent_plays : [];
        container.replaceChildren();
        empty.classList.toggle('hidden', rows.length > 0);
        rows.forEach((item, index) => {
            const row = document.createElement('li');
            row.className = 'entity-detail-list-item';
            appendText(row, 'entity-list-rank stat-value', String(index + 1));
            const copy = document.createElement('div');
            copy.className = 'entity-list-copy';
            const title = appendText(
                copy,
                'entity-list-title',
                item.title || t('entity.unknownTrack'),
            );
            title.title = title.textContent;
            const contextFields = currentIdentity?.type === 'client'
                ? [item.artist, item.album, item.source_name]
                : [item.album, item.source_name];
            const context = contextFields.filter(Boolean).join(' · ');
            if (context) appendText(copy, 'entity-list-context', context);
            const meta = [
                formatDateTime(item.played_at),
                item.username,
                currentIdentity?.type === 'client' ? '' : item.client_name,
            ].filter(Boolean).join(' · ');
            appendText(copy, 'entity-list-meta', meta);
            const value = document.createElement('span');
            value.className = 'entity-list-value stat-value';
            value.textContent = formatDuration(item.listen_duration_sec);
            row.append(copy, value);
            container.appendChild(row);
        });
    }

    function renderPayload(payload) {
        lastPayload = payload;
        renderIdentity(currentIdentity, payload);
        document.getElementById('entityDetailPlays').textContent = formatNumber(payload.total_plays);
        document.getElementById('entityDetailListen').textContent = formatDuration(payload.total_listen_sec);
        document.getElementById('entityDetailAverage').textContent = formatPreciseDuration(
            payload.average_listen_sec,
        );
        document.getElementById('entityDetailTracks').textContent = formatNumber(payload.unique_tracks);
        const first = document.getElementById('entityDetailFirst');
        const last = document.getElementById('entityDetailLast');
        first.textContent = formatDateTime(payload.first_played_at);
        first.title = first.textContent;
        last.textContent = formatDateTime(payload.last_played_at);
        last.title = last.textContent;
        renderRank(payload);
        renderTrend(payload);
        renderTopTracks(payload);
        renderRecentPlays(payload);
    }

    function show(identity) {
        const wasHidden = layer.classList.contains('hidden');
        currentIdentity = identity;
        layer.classList.remove('hidden');
        layer.setAttribute('aria-hidden', 'false');
        document.body.classList.add('entity-detail-open');
        renderIdentity(identity);
        if (wasHidden) window.requestAnimationFrame(() => panel.focus());
    }

    function cancel() {
        requestGeneration += 1;
        if (requestController) requestController.abort();
        requestController = null;
    }

    function hide() {
        const wasVisible = !layer.classList.contains('hidden');
        cancel();
        layer.classList.add('hidden');
        layer.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('entity-detail-open');
        currentIdentity = null;
        lastPayload = null;
        if (wasVisible && lastFocused && document.contains(lastFocused)) {
            lastFocused.focus();
        }
        lastFocused = null;
    }

    async function load(identity) {
        cancel();
        const generation = ++requestGeneration;
        const controller = new AbortController();
        requestController = controller;
        setState('loading');
        try {
            const scope = getScope();
            const params = new URLSearchParams(buildStatsQuery(scope));
            params.set('entity_type', identity.type);
            params.set('name', identity.name);
            if (identity.id) params.set('entity_id', identity.id);
            if (identity.sourceId) params.set('entity_source_id', identity.sourceId);
            if (identity.artist) params.set('artist', identity.artist);
            const response = await apiFetch(`/api/stats/entity-detail?${params}`, {
                signal: controller.signal,
            });
            if (!response.ok) throw new Error(`entity detail request failed (${response.status})`);
            const payload = await response.json();
            if (generation !== requestGeneration || controller.signal.aborted) return;
            setState('ready');
            renderPayload(payload);
        } catch (loadError) {
            if (isAbortError(loadError) || generation !== requestGeneration) return;
            console.error('Error fetching entity detail:', loadError);
            setState('error', t('entity.loadError'));
        } finally {
            if (generation === requestGeneration) requestController = null;
        }
    }

    function sync(filters, { fetch = true } = {}) {
        const identity = identityFromFilters(filters);
        if (!identity) {
            hide();
            return;
        }
        show(identity);
        if (fetch) load(identity);
    }

    function open(identity, trigger = document.activeElement) {
        lastFocused = trigger;
        const patch = {
            ...identityPatch(identity),
            // A shared detail URL must keep the exact IANA zone, not the
            // device-dependent "browser" preference token.
            timezone: getScope().timezone,
        };
        if (getFilters().entityType) setFilters(patch);
        else pushFilters(patch);
    }

    function close() {
        if (window.history.state?.navidromeEntityDetail) {
            window.history.back();
        } else {
            setFilters(EMPTY_ENTITY);
        }
    }

    async function copyUrl() {
        const button = document.getElementById('entityDetailCopy');
        const label = button.querySelector('span');
        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(window.location.href);
            } else {
                const textarea = document.createElement('textarea');
                textarea.value = window.location.href;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                textarea.remove();
            }
            label.textContent = t('entity.copyDone');
        } catch (_error) {
            label.textContent = t('entity.copyError');
        }
        if (copyResetTimer) clearTimeout(copyResetTimer);
        copyResetTimer = setTimeout(() => {
            label.textContent = t('entity.copyLink');
            copyResetTimer = null;
        }, 1800);
    }

    function trapFocus(event) {
        if (event.key === 'Escape') {
            event.preventDefault();
            close();
            return;
        }
        if (event.key !== 'Tab') return;
        const focusable = [...panel.querySelectorAll(
            'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        )].filter((element) => !element.classList.contains('hidden'));
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
    }

    function mount() {
        if (mounted) return;
        mounted = true;
        document.getElementById('entityDetailClose').addEventListener('click', close);
        document.getElementById('entityDetailBackdrop').addEventListener('click', close);
        document.getElementById('entityDetailRetry').addEventListener('click', () => {
            if (currentIdentity) load(currentIdentity);
        });
        document.getElementById('entityDetailCopy').addEventListener('click', copyUrl);
        panel.addEventListener('keydown', trapFocus);
        window.addEventListener('resize', () => trendChart?.resize());
        unsubscribe = subscribe((filters) => sync(filters));
        sync(getFilters(), { fetch: false });
    }

    function restore() {
        sync(getFilters());
    }

    function refresh() {
        if (currentIdentity) load(currentIdentity);
    }

    function localize() {
        if (currentIdentity) renderIdentity(currentIdentity, lastPayload);
        if (lastPayload) renderPayload(lastPayload);
    }

    function updateTheme() {
        if (lastPayload) renderTrend(lastPayload);
    }

    return {
        cancel,
        close,
        localize,
        mount,
        open,
        refresh,
        restore,
        updateTheme,
        destroy() {
            cancel();
            if (unsubscribe) unsubscribe();
        },
    };
}
