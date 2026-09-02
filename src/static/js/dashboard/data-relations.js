import { colorWithAlpha, createThemeTokens } from '../charts.js';
import { buildStatsQuery, escapeHtml } from '../format.js';

const DIMENSIONS = Object.freeze(['artist', 'album', 'client']);
const DAYPARTS = Object.freeze(['night', 'morning', 'afternoon', 'evening']);
const OTHER_KEY = '__other__';

/** Render the lazy, chart-led cross-dimensional analysis section. */
export function createDataRelations({
    apiFetch,
    isAbortError,
    t,
    formatNumber,
    formatDuration,
    formatPlays,
    getLocale,
    getScope,
    getWindowLabel,
    getDimension,
    onDimensionChange,
    onEntitySelect,
    setPanelState,
    setPanelSummary,
}) {
    const trendChart = echarts.init(
        document.getElementById('relationTrendChart'),
        null,
        { renderer: 'canvas' },
    );
    const matrixChart = echarts.init(
        document.getElementById('relationMatrixChart'),
        null,
        { renderer: 'canvas' },
    );
    const comparisonChart = echarts.init(
        document.getElementById('relationComparisonChart'),
        null,
        { renderer: 'canvas' },
    );
    const charts = [trendChart, matrixChart, comparisonChart];
    let chartTheme = createThemeTokens();
    let controller = null;
    let generation = 0;
    let lastPayload = null;

    function metricValue(item, metric) {
        const field = metric === 'listen_time'
            ? 'total_listen_sec'
            : 'play_count';
        return Number(item?.[field]) || 0;
    }

    function metricLabel(metric) {
        return t(metric === 'listen_time' ? 'metric.listenTime' : 'metric.plays');
    }

    function entityLabel(item) {
        if (item?.key === OTHER_KEY) return t('relations.other');
        if (item?.label) return String(item.label);
        return t('label.unknownClient');
    }

    function displayLabels(items) {
        const counts = new Map();
        items.forEach((item) => {
            const label = entityLabel(item);
            counts.set(label, (counts.get(label) || 0) + 1);
        });
        return new Map(items.map((item) => {
            const label = entityLabel(item);
            const display = counts.get(label) > 1 && item.source_name
                ? `${label} · ${item.source_name}`
                : label;
            return [item.key, display];
        }));
    }

    function formatBoth(playCount, listenSec) {
        return `${t('label.play')} ${formatPlays(playCount)} · ${t('label.listening')} ${formatDuration(listenSec)}`;
    }

    function axisDuration(value) {
        const seconds = Math.max(0, Number(value) || 0);
        if (seconds >= 3600) {
            const hours = seconds / 3600;
            return `${hours >= 10 ? Math.round(hours) : hours.toFixed(1).replace(/\.0$/, '')}h`;
        }
        if (seconds >= 60) return `${Math.round(seconds / 60)}m`;
        return `${Math.round(seconds)}s`;
    }

    function canOpenEntity(item) {
        const dimension = lastPayload?.dimension;
        if (!item || item.key === OTHER_KEY || !String(item.label || '').trim()) return false;
        if (dimension === 'album') return Boolean(item.source_id);
        return dimension === 'artist' || dimension === 'client';
    }

    function openEntity(item, chart) {
        const dimension = lastPayload?.dimension;
        if (!canOpenEntity(item)) return;
        if (dimension === 'artist') {
            onEntitySelect({
                type: 'artist',
                name: item.label,
                id: item.entity_id || '',
                sourceId: '',
                artist: '',
            }, chart.getDom());
            return;
        }
        if (dimension === 'client') {
            onEntitySelect({
                type: 'client',
                name: item.label,
                id: '',
                sourceId: '',
                artist: '',
            }, chart.getDom());
            return;
        }
        if (dimension === 'album' && item.source_id) {
            onEntitySelect({
                type: 'album',
                name: item.label,
                id: item.entity_id || '',
                sourceId: item.source_id,
                artist: item.artist || '',
            }, chart.getDom());
        }
    }

    trendChart.on('click', (params) => openEntity(params.data?.relation, trendChart));
    matrixChart.on('click', (params) => openEntity(params.data?.relation, matrixChart));
    comparisonChart.on('click', (params) => (
        openEntity(params.data?.relation, comparisonChart)
    ));

    function updateControls() {
        const selected = getDimension();
        document.querySelectorAll('.relations-dimension-btn').forEach((button) => {
            const active = button.dataset.relationsDimension === selected;
            button.setAttribute('aria-pressed', active ? 'true' : 'false');
            button.classList.toggle('bg-accent', active);
            button.classList.toggle('text-white', active);
            button.classList.toggle('text-slate-400', !active);
        });
    }

    function updateText(payload = lastPayload) {
        const metric = payload?.metric || getScope().metric;
        const scopeParts = [getWindowLabel(), metricLabel(metric)];
        if (metric === 'listen_time' && payload) {
            scopeParts.push(t('relations.durationCoverage', {
                value: formatNumber(payload.duration_coverage_pct),
            }));
            scopeParts.push(t('relations.reportedDuration', {
                value: formatNumber(payload.reported_duration_pct),
            }));
        }
        document.getElementById('relationsScope').textContent = scopeParts.join(' · ');

        const grain = payload?.grain || 'day';
        document.getElementById('relationTrendSubtitle').textContent = t(
            'relations.trendSubtitle',
            { grain: t(`relations.grain.${grain}`), metric: metricLabel(metric) },
        );
        document.getElementById('relationMatrixSubtitle').textContent = t(
            'relations.daypartSubtitle',
            { metric: metricLabel(metric) },
        );
        document.getElementById('relationComparisonSubtitle').textContent = t(
            'relations.comparisonSubtitle',
            { metric: metricLabel(metric) },
        );
        updateControls();
    }

    function selectedHasValues(items, metric, pointField = 'points') {
        return Array.isArray(items) && items.some((item) => (
            Array.isArray(item?.[pointField])
            && item[pointField].some((point) => metricValue(point, metric) > 0)
        ));
    }

    function bucketAxisLabel(bucket, grain) {
        if (grain === 'month') return String(bucket);
        try {
            const date = new Date(`${bucket}T00:00:00Z`);
            return new Intl.DateTimeFormat(getLocale(), {
                month: 'short',
                day: 'numeric',
            }).format(date);
        } catch (error) {
            return String(bucket);
        }
    }

    function renderTrend(payload) {
        const rows = Array.isArray(payload.trend) ? payload.trend : [];
        const hasValues = selectedHasValues(rows, payload.metric);
        if (!hasValues) {
            trendChart.clear();
            document.getElementById('relationTrendEmptyText').textContent = t(
                payload.metric === 'listen_time'
                    ? 'relations.emptyListening'
                    : 'relations.emptyTrend',
            );
            setPanelState('relationTrend', 'empty');
            return;
        }
        setPanelState('relationTrend', 'ready');
        const labels = displayLabels(rows);
        const buckets = rows[0]?.points?.map((point) => point.bucket) || [];
        const colors = rows.map((row, index) => (
            row.key === OTHER_KEY
                ? colorWithAlpha(chartTheme.axisText, 0.72)
                : chartTheme.palette[index % chartTheme.palette.length]
        ));
        trendChart.setOption({
            ...chartTheme.base,
            animationDurationUpdate: 350,
            color: colors,
            grid: { left: 52, right: 20, top: 48, bottom: 42 },
            legend: {
                type: 'scroll',
                top: 0,
                left: 0,
                right: 0,
                textStyle: { color: chartTheme.axisText, fontSize: 11 },
                pageTextStyle: { color: chartTheme.axisText },
            },
            tooltip: {
                ...chartTheme.base.tooltip,
                trigger: 'axis',
                formatter: (params) => {
                    if (!params.length) return '';
                    const lines = [escapeHtml(String(params[0].axisValue || ''))];
                    params.forEach((point) => {
                        const data = point.data || {};
                        lines.push(
                            `${point.marker}${escapeHtml(point.seriesName)}<br/>`
                            + `${formatBoth(data.playCount, data.listenSec)}`,
                        );
                    });
                    return lines.join('<br/>');
                },
            },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: buckets,
                axisLine: { lineStyle: { color: chartTheme.axisLine } },
                axisTick: { show: false },
                axisLabel: {
                    color: chartTheme.axisText,
                    fontSize: 11,
                    hideOverlap: true,
                    formatter: (value) => bucketAxisLabel(value, payload.grain),
                },
            },
            yAxis: {
                type: 'value',
                min: 0,
                splitLine: { lineStyle: { color: chartTheme.gridLine } },
                axisLabel: {
                    color: chartTheme.axisText,
                    fontSize: 11,
                    formatter: payload.metric === 'listen_time'
                        ? axisDuration
                        : (value) => formatNumber(value),
                },
            },
            series: rows.map((row) => ({
                name: labels.get(row.key),
                type: 'line',
                smooth: false,
                showSymbol: false,
                symbolSize: 7,
                emphasis: { focus: 'series' },
                lineStyle: {
                    width: row.key === OTHER_KEY ? 1.5 : 2,
                    type: row.key === OTHER_KEY ? 'dashed' : 'solid',
                },
                data: row.points.map((point) => ({
                    value: metricValue(point, payload.metric),
                    playCount: Number(point.play_count) || 0,
                    listenSec: Number(point.total_listen_sec) || 0,
                    relation: row,
                    cursor: canOpenEntity(row) ? 'pointer' : 'default',
                })),
            })),
        }, true);
        setPanelSummary('relationTrend', t('relations.ariaTrendSummary', {
            series: formatNumber(rows.length),
            buckets: formatNumber(buckets.length),
        }));
    }

    function renderMatrix(payload) {
        const rows = Array.isArray(payload.matrix) ? payload.matrix : [];
        const hasValues = selectedHasValues(rows, payload.metric);
        if (!hasValues) {
            matrixChart.clear();
            document.getElementById('relationMatrixEmptyText').textContent = t(
                payload.metric === 'listen_time'
                    ? 'relations.emptyListening'
                    : 'relations.emptyDaypart',
            );
            setPanelState('relationMatrix', 'empty');
            return;
        }
        setPanelState('relationMatrix', 'ready');
        const labels = displayLabels(rows);
        const values = [];
        rows.forEach((row, rowIndex) => {
            DAYPARTS.forEach((daypart, daypartIndex) => {
                const point = row.points.find((candidate) => candidate.daypart === daypart) || {};
                values.push({
                    value: [daypartIndex, rowIndex, metricValue(point, payload.metric)],
                    playCount: Number(point.play_count) || 0,
                    listenSec: Number(point.total_listen_sec) || 0,
                    relation: row,
                    cursor: canOpenEntity(row) ? 'pointer' : 'default',
                });
            });
        });
        const maximum = Math.max(1, ...values.map((item) => Number(item.value[2]) || 0));
        matrixChart.setOption({
            ...chartTheme.base,
            animationDurationUpdate: 350,
            grid: { left: 104, right: 16, top: 14, bottom: 72 },
            tooltip: {
                ...chartTheme.base.tooltip,
                formatter: (params) => {
                    const data = params.data || {};
                    const row = data.relation || {};
                    const daypart = DAYPARTS[Number(params.value?.[0])] || '';
                    return `${escapeHtml(labels.get(row.key) || '')}<br/>`
                        + `${escapeHtml(t(`relations.daypart.${daypart}`))}<br/>`
                        + formatBoth(data.playCount, data.listenSec);
                },
            },
            xAxis: {
                type: 'category',
                data: DAYPARTS.map((key) => t(`relations.daypart.${key}`)),
                axisLine: { lineStyle: { color: chartTheme.axisLine } },
                axisTick: { show: false },
                axisLabel: { color: chartTheme.axisText, fontSize: 11 },
            },
            yAxis: {
                type: 'category',
                inverse: true,
                data: rows.map((row) => labels.get(row.key)),
                axisLine: { lineStyle: { color: chartTheme.axisLine } },
                axisTick: { show: false },
                axisLabel: {
                    color: chartTheme.axisText,
                    fontSize: 11,
                    width: 88,
                    overflow: 'truncate',
                },
            },
            visualMap: {
                min: 0,
                max: maximum,
                calculable: false,
                orient: 'horizontal',
                left: 'center',
                bottom: 6,
                itemWidth: 12,
                textStyle: { color: chartTheme.axisText, fontSize: 11 },
                inRange: { color: chartTheme.heatmap },
            },
            series: [{
                name: metricLabel(payload.metric),
                type: 'heatmap',
                data: values,
                itemStyle: { borderRadius: 3, borderWidth: 2, borderColor: 'transparent' },
                emphasis: { itemStyle: { shadowBlur: 10, shadowColor: chartTheme.shadow } },
            }],
        }, true);
        setPanelSummary('relationMatrix', t('relations.ariaDaypartSummary', {
            rows: formatNumber(rows.length),
            cells: formatNumber(values.length),
        }));
    }

    function comparisonHasValues(rows, metric) {
        const prefix = metric === 'listen_time' ? 'total_listen_sec' : 'play_count';
        return rows.some((row) => (
            Number(row[`current_${prefix}`]) > 0 || Number(row[`previous_${prefix}`]) > 0
        ));
    }

    function renderComparison(payload) {
        const rows = Array.isArray(payload.comparison) ? payload.comparison : [];
        if (!payload.comparison_available || !comparisonHasValues(rows, payload.metric)) {
            comparisonChart.clear();
            let key = 'relations.emptyComparison';
            if (!payload.comparison_available) key = 'relations.noAllHistoryComparison';
            else if (payload.metric === 'listen_time') key = 'relations.emptyListening';
            document.getElementById('relationComparisonEmptyText').textContent = t(key);
            setPanelState('relationComparison', 'empty');
            return;
        }
        setPanelState('relationComparison', 'ready');
        const labels = displayLabels(rows);
        const currentField = payload.metric === 'listen_time'
            ? 'current_total_listen_sec'
            : 'current_play_count';
        const previousField = payload.metric === 'listen_time'
            ? 'previous_total_listen_sec'
            : 'previous_play_count';
        const seriesData = (field) => rows.map((row) => ({
            value: Number(row[field]) || 0,
            relation: row,
            cursor: canOpenEntity(row) ? 'pointer' : 'default',
        }));
        comparisonChart.setOption({
            ...chartTheme.base,
            animationDurationUpdate: 350,
            color: [chartTheme.palette[0], colorWithAlpha(chartTheme.palette[1], 0.68)],
            grid: { left: 112, right: 18, top: 42, bottom: 32 },
            legend: {
                top: 0,
                textStyle: { color: chartTheme.axisText, fontSize: 11 },
            },
            tooltip: {
                ...chartTheme.base.tooltip,
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                formatter: (params) => {
                    if (!params.length) return '';
                    const row = params[0].data?.relation || {};
                    return `${escapeHtml(labels.get(row.key) || '')}<br/>`
                        + `${t('relations.current')}: ${formatBoth(row.current_play_count, row.current_total_listen_sec)}<br/>`
                        + `${t('relations.previous')}: ${formatBoth(row.previous_play_count, row.previous_total_listen_sec)}`;
                },
            },
            xAxis: {
                type: 'value',
                min: 0,
                splitLine: { lineStyle: { color: chartTheme.gridLine } },
                axisLabel: {
                    color: chartTheme.axisText,
                    fontSize: 11,
                    formatter: payload.metric === 'listen_time'
                        ? axisDuration
                        : (value) => formatNumber(value),
                },
            },
            yAxis: {
                type: 'category',
                inverse: true,
                data: rows.map((row) => labels.get(row.key)),
                axisLine: { lineStyle: { color: chartTheme.axisLine } },
                axisTick: { show: false },
                axisLabel: {
                    color: chartTheme.axisText,
                    fontSize: 11,
                    width: 96,
                    overflow: 'truncate',
                },
            },
            series: [
                {
                    name: t('relations.current'),
                    type: 'bar',
                    barMaxWidth: 14,
                    data: seriesData(currentField),
                    itemStyle: { borderRadius: [0, 4, 4, 0] },
                },
                {
                    name: t('relations.previous'),
                    type: 'bar',
                    barMaxWidth: 14,
                    data: seriesData(previousField),
                    itemStyle: { borderRadius: [0, 4, 4, 0] },
                },
            ],
        }, true);
        setPanelSummary('relationComparison', t('relations.ariaComparisonSummary', {
            rows: formatNumber(rows.length),
        }));
    }

    function render(payload) {
        lastPayload = payload;
        updateText(payload);
        renderTrend(payload);
        renderMatrix(payload);
        renderComparison(payload);
        window.requestAnimationFrame(resize);
    }

    function setAllPanels(state, message) {
        ['relationTrend', 'relationMatrix', 'relationComparison'].forEach((panel) => (
            setPanelState(panel, state, message)
        ));
    }

    async function refresh({ scope = getScope() } = {}) {
        const dimension = getDimension();
        const requestGeneration = ++generation;
        if (controller) controller.abort();
        const requestController = new AbortController();
        controller = requestController;
        setAllPanels('loading');
        updateText();
        try {
            const params = new URLSearchParams(buildStatsQuery(scope));
            params.set('dimension', dimension);
            const response = await apiFetch(`/api/stats/relations?${params.toString()}`, {
                signal: requestController.signal,
            });
            if (!response.ok) throw new Error(`relations request failed (${response.status})`);
            const payload = await response.json();
            if (requestGeneration !== generation || requestController.signal.aborted) return;
            if (!payload || payload.dimension !== dimension) {
                throw new Error('relations response does not match the selected dimension');
            }
            render(payload);
        } catch (error) {
            if (isAbortError(error) || requestGeneration !== generation) return;
            console.error('Error fetching relation data:', error);
            setAllPanels('error', t('error.section'));
        } finally {
            if (requestGeneration === generation) controller = null;
        }
    }

    function cancel() {
        generation += 1;
        if (controller) controller.abort();
        controller = null;
    }

    function resize() {
        charts.forEach((chart) => {
            const dom = chart.getDom();
            if (chart.getWidth() !== dom.clientWidth || chart.getHeight() !== dom.clientHeight) {
                chart.resize();
            }
        });
    }

    function localize() {
        updateText();
        if (lastPayload) render(lastPayload);
    }

    function sync() {
        updateControls();
        updateText(null);
    }

    function updateTheme() {
        chartTheme = createThemeTokens();
        if (lastPayload) render(lastPayload);
    }

    function mount() {
        document.querySelectorAll('.relations-dimension-btn').forEach((button) => {
            button.addEventListener('click', () => {
                const dimension = button.dataset.relationsDimension;
                if (!DIMENSIONS.includes(dimension) || dimension === getDimension()) return;
                onDimensionChange(dimension);
                updateControls();
                refresh();
            });
        });
        updateControls();
        updateText();
    }

    return Object.freeze({
        cancel,
        localize,
        mount,
        refresh,
        resize,
        sync,
        updateTheme,
    });
}
