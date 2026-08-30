import { createThemeTokens } from '../charts.js';
import { coverArtUrl, escapeHtml, formatChangeText } from '../format.js';

const WEEKDAY_MESSAGE_KEYS = Object.freeze([
    'weekday.mon', 'weekday.tue', 'weekday.wed', 'weekday.thu',
    'weekday.fri', 'weekday.sat', 'weekday.sun',
]);
const HOUR_LABELS = Object.freeze(Array.from({ length: 24 }, (_, hour) => String(hour)));

/** Own all historical summary, chart, ranking, and source rendering. */
export function createHistoricalDashboard({
    t,
    formatNumber,
    formatDuration,
    formatPlays,
    beginArrayPanel,
    setPanelState,
    setPanelSummary,
    renderSafely,
    getSourceId,
    getFirstSourceId,
}) {
    const playerChart = echarts.init(
        document.getElementById('playerChart'),
        null,
        { renderer: 'canvas' },
    );
    const transcodingChart = echarts.init(
        document.getElementById('transcodingChart'),
        null,
        { renderer: 'canvas' },
    );
    const hourlyChart = echarts.init(
        document.getElementById('hourlyChart'),
        null,
        { renderer: 'canvas' },
    );
    const dailyChart = echarts.init(
        document.getElementById('dailyChart'),
        null,
        { renderer: 'canvas' },
    );
    const weekdayHourChart = echarts.init(
        document.getElementById('weekdayHourChart'),
        null,
        { renderer: 'canvas' },
    );
    const charts = [
        playerChart,
        transcodingChart,
        hourlyChart,
        dailyChart,
        weekdayHourChart,
    ];
    let chartTheme = createThemeTokens();
    let chartBase = chartTheme.base;
    let colorPalette = [...chartTheme.palette];
    let lastSnapshot = null;
    let lastMetric = 'plays';

    function resizeDashboardCharts() {
        // resize() interrupts animations, so skip steady-state calls.
        charts.forEach((chart) => {
            const dom = chart.getDom();
            if (chart.getWidth() !== dom.clientWidth || chart.getHeight() !== dom.clientHeight) {
                chart.resize();
            }
        });
    }

    function updateTheme() {
        chartTheme = createThemeTokens();
        chartBase = chartTheme.base;
        colorPalette = [...chartTheme.palette];
        if (lastSnapshot) render(lastSnapshot, lastMetric);
    }

    function updateSummary(summary, transcoding) {
        if (!summary || typeof summary !== 'object') {
            setPanelState('summary', 'error', t('error.section'));
            return;
        }
        const transcodingRows = Array.isArray(transcoding) ? transcoding : [];
        document.getElementById('statTotalPlays').textContent = formatNumber(summary.total_plays);
        document.getElementById('statListenTime').textContent = formatDuration(summary.total_listen_sec);
        document.getElementById('statUniqueTracks').textContent = formatNumber(summary.unique_tracks);
        document.getElementById('statTotalPlaysChange').textContent = formatChangeText(
            summary.plays_change_pct,
            { compareLabel: compareLabel() },
        );
        document.getElementById('statListenTimeChange').textContent = formatChangeText(
            summary.listen_change_pct,
            { compareLabel: compareLabel() },
        );

        const activeDays = Number(summary.active_days) || 0;
        const avgParts = [];
        if (activeDays > 0) avgParts.push(t('summary.activeDays', { count: activeDays }));
        if (typeof summary.average_daily_plays === 'number'
            && Number.isFinite(summary.average_daily_plays)) {
            avgParts.push(t('summary.playsPerDay', {
                count: summary.average_daily_plays.toFixed(1),
            }));
        }
        document.getElementById('statActiveDays').textContent = avgParts.join(' · ');

        const direct = transcodingRows.find((row) => !row.is_transcoding)?.count || 0;
        const transcoded = transcodingRows.find((row) => row.is_transcoding)?.count || 0;
        const unique = document.getElementById('statUniqueTracks');
        if (direct + transcoded > 0) {
            unique.title = t('summary.uniqueDetails', {
                days: activeDays,
                ratio: Math.round((transcoded / (direct + transcoded)) * 100),
                clients: summary.client_count ?? 0,
            });
        } else {
            unique.title = activeDays > 0 ? t('summary.activeDays', { count: activeDays }) : '';
        }
        setPanelState('summary', 'ready');
        setPanelSummary('summary', t('aria.summaryPlays', {
            plays: formatNumber(summary.total_plays),
            tracks: formatNumber(summary.unique_tracks),
        }));
    }

    function compareLabel() {
        return t('compare.previous');
    }

    function renderPlayerChart(data) {
        const legend = document.getElementById('playerChartLegend');
        legend.replaceChildren();
        legend.classList.add('hidden');
        const rows = beginArrayPanel(
            'players',
            data,
            (items) => items.length > 0 && items.some((item) => Number(item.count) > 0),
            t('empty.clients'),
        );
        if (!rows) return;

        const table = document.createElement('table');
        table.className = 'player-legend-table';
        const caption = document.createElement('caption');
        caption.className = 'sr-only';
        caption.textContent = t('client.detailTitle');
        table.appendChild(caption);
        const header = document.createElement('tr');
        [
            t('client.name'), t('client.plays'), t('client.listeningTime'),
            t('client.averagePlay'), t('client.transcodingRate'),
        ].forEach((label, index) => {
            const cell = document.createElement('th');
            cell.scope = 'col';
            cell.textContent = label;
            if (index >= 3) cell.classList.add('hide-mobile');
            header.appendChild(cell);
        });
        const thead = document.createElement('thead');
        thead.appendChild(header);
        table.appendChild(thead);
        const tbody = document.createElement('tbody');
        rows.forEach((item) => {
            const row = document.createElement('tr');
            const name = document.createElement('td');
            name.className = 'client-cell';
            name.textContent = item.client_name || t('label.unknownClient');
            name.title = name.textContent;
            const count = document.createElement('td');
            count.textContent = formatNumber(item.count);
            const total = document.createElement('td');
            total.textContent = formatDuration(item.total_listen_sec);
            const average = document.createElement('td');
            average.className = 'hide-mobile';
            average.textContent = formatDuration(item.average_listen_sec);
            const transcode = document.createElement('td');
            transcode.className = 'hide-mobile';
            const rate = Number(item.transcoding_rate_pct);
            transcode.textContent = Number.isFinite(rate) ? `${rate.toFixed(1)}%` : '—';
            row.append(name, count, total, average, transcode);
            tbody.appendChild(row);
        });
        table.appendChild(tbody);
        legend.appendChild(table);
        legend.classList.remove('hidden');

        playerChart.setOption({
            ...chartBase,
            animationDurationUpdate: 450,
            color: colorPalette,
            legend: {
                bottom: 0,
                textStyle: { color: chartTheme.axisText, fontSize: 11 },
                itemWidth: 10,
                itemHeight: 10,
            },
            tooltip: {
                ...chartBase.tooltip,
                formatter: (params) => `${escapeHtml(params.name || '')}<br/>${t('label.play')} ${formatPlays(params.value)}`,
            },
            series: [{
                name: t('dashboard.clients'),
                type: 'pie',
                radius: ['42%', '68%'],
                center: ['50%', '45%'],
                universalTransition: true,
                itemStyle: {
                    borderRadius: 6,
                    borderColor: chartTheme.pieSeparator,
                    borderWidth: 2,
                },
                label: { color: chartTheme.axisText, fontSize: 11 },
                data: rows.map((item) => ({
                    name: item.client_name || t('label.unknownClient'),
                    value: item.count,
                })),
            }],
        });
        setPanelSummary('players', t('aria.clientsSummary', {
            count: formatNumber(rows.length),
            top: rows[0].client_name || t('source.unknown'),
            plays: formatNumber(rows[0].count),
        }));
    }

    function renderTranscodingChart(data) {
        const rows = beginArrayPanel(
            'transcoding',
            data,
            (items) => items.length > 0 && items.some((item) => Number(item.count) > 0),
            t('empty.transcoding'),
        );
        if (!rows) return;
        const transformed = rows.map((item) => ({
            name: item.is_transcoding ? t('label.transcoded') : t('label.directPlay'),
            value: item.count,
            playsPct: Number(item.plays_pct) || 0,
            listenPct: Number(item.listen_sec_pct) || 0,
            listenSec: Number(item.total_listen_sec) || 0,
        }));
        transcodingChart.setOption({
            ...chartBase,
            animationDurationUpdate: 450,
            color: [colorPalette[2], colorPalette[5]],
            legend: { bottom: 0, textStyle: { color: chartTheme.axisText, fontSize: 11 } },
            tooltip: {
                ...chartBase.tooltip,
                formatter: (params) => {
                    const item = params.data || {};
                    return `${params.name}<br/>${t('label.play')} ${formatPlays(item.value)} (${item.playsPct ?? 0}%)<br/>${t('label.listening')} ${formatDuration(item.listenSec)} (${item.listenPct ?? 0}%)`;
                },
            },
            series: [{
                name: t('label.play'),
                type: 'pie',
                radius: '62%',
                center: ['50%', '45%'],
                universalTransition: true,
                itemStyle: {
                    borderRadius: 4,
                    borderColor: chartTheme.pieSeparator,
                    borderWidth: 2,
                },
                label: { color: chartTheme.axisText, fontSize: 11 },
                data: transformed,
            }],
        });
        setPanelSummary('transcoding', t('aria.transcodingSummary', {
            direct: formatNumber(rows.find((item) => !item.is_transcoding)?.count || 0),
            transcoded: formatNumber(rows.find((item) => item.is_transcoding)?.count || 0),
        }));
    }

    function renderHourlyChart(data) {
        const rows = beginArrayPanel(
            'hourly',
            data,
            (items) => items.length > 0 && items.some((item) => Number(item.count) > 0),
            t('empty.hourly'),
        );
        if (!rows) return;
        const buckets = Array.from({ length: 24 }, (_, hour) => {
            const found = rows.find((item) => Number(item.hour) === hour);
            return { hour, count: found ? Number(found.count) : 0 };
        });
        hourlyChart.setOption({
            ...chartBase,
            animationDurationUpdate: 450,
            color: [colorPalette[0]],
            grid: { left: 40, right: 16, top: 16, bottom: 32 },
            tooltip: {
                ...chartBase.tooltip,
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                formatter: (params) => {
                    const point = params[0];
                    return `${point.axisValue} ${t('label.hour')}<br/>${t('label.play')} ${formatPlays(point.data)}`;
                },
            },
            xAxis: {
                type: 'category',
                data: buckets.map((bucket) => String(bucket.hour)),
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
                name: t('metric.plays'),
                type: 'bar',
                data: buckets.map((bucket) => bucket.count),
                itemStyle: {
                    borderRadius: [4, 4, 0, 0],
                    color: {
                        type: 'linear',
                        x: 0,
                        y: 0,
                        x2: 0,
                        y2: 1,
                        colorStops: [
                            { offset: 0, color: chartTheme.barGradient[0] },
                            { offset: 1, color: chartTheme.barGradient[1] },
                        ],
                    },
                },
            }],
        });
        const peak = buckets.reduce(
            (best, bucket) => (bucket.count > best.count ? bucket : best),
            buckets[0],
        );
        setPanelSummary('hourly', t('aria.hourlySummary', {
            hour: formatNumber(peak.hour),
            plays: formatNumber(peak.count),
        }));
    }

    function renderDailyChart(data) {
        const rows = beginArrayPanel(
            'daily',
            data,
            (items) => items.length > 0 && items.some((item) => Number(item.count) > 0),
            t('empty.daily'),
        );
        if (!rows) return;
        const sorted = [...rows].sort((a, b) => String(a.date).localeCompare(String(b.date)));
        const dates = sorted.map((item) => item.date);
        const counts = sorted.map((item) => Number(item.count));
        dailyChart.setOption({
            ...chartBase,
            animationDurationUpdate: 450,
            color: [colorPalette[2]],
            grid: { left: 40, right: 16, top: 16, bottom: 32 },
            tooltip: {
                ...chartBase.tooltip,
                trigger: 'axis',
                formatter: (params) => {
                    const point = params[0];
                    return `${point.axisValue}<br/>${t('label.play')} ${formatPlays(point.data)}`;
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
                name: t('metric.plays'),
                type: 'line',
                smooth: true,
                symbol: 'circle',
                symbolSize: 6,
                data: counts,
                lineStyle: { width: 2 },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0,
                        y: 0,
                        x2: 0,
                        y2: 1,
                        colorStops: [
                            { offset: 0, color: chartTheme.areaGradient[0] },
                            { offset: 1, color: chartTheme.areaGradient[1] },
                        ],
                    },
                },
            }],
        });
        setPanelSummary('daily', t('aria.dailySummary', {
            days: formatNumber(sorted.filter((item) => Number(item.count) > 0).length),
            plays: formatNumber(Math.max(0, ...counts)),
        }));
    }

    function heatmapRamp() {
        return chartTheme.heatmap;
    }

    function renderWeekdayHourChart(data) {
        const rows = beginArrayPanel(
            'heatmap',
            data,
            (items) => items.some((item) => Number(item.count) > 0),
            t('empty.heatmap'),
        );
        if (!rows) return;
        const points = rows.map((item) => [
            Number(item.hour),
            Number(item.weekday),
            Number(item.count) || 0,
        ]);
        const maxCount = Math.max(1, ...points.map((point) => point[2]));
        const weekdayLabels = WEEKDAY_MESSAGE_KEYS.map((key) => t(key));
        weekdayHourChart.setOption({
            ...chartBase,
            animationDurationUpdate: 450,
            tooltip: {
                ...chartBase.tooltip,
                formatter: (params) => {
                    const [hour, weekday, count] = params.value;
                    return `${weekdayLabels[weekday] || '?'} ${hour} ${t('label.hour')}<br/>${t('label.play')} ${formatPlays(count)}`;
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
                name: t('metric.plays'),
                type: 'heatmap',
                data: points,
                label: { show: false },
                itemStyle: { borderRadius: 3, borderWidth: 2, borderColor: 'transparent' },
                emphasis: { itemStyle: { shadowBlur: 10, shadowColor: chartTheme.shadow } },
            }],
        });
        const peak = rows.reduce(
            (best, item) => (Number(item.count) > Number(best.count) ? item : best),
            rows[0],
        );
        setPanelSummary('heatmap', t('aria.heatmapSummary', {
            weekday: weekdayLabels[Number(peak.weekday)] || String(peak.weekday),
            hour: formatNumber(peak.hour),
            plays: formatNumber(peak.count),
        }));
    }

    function createRankingFallback(text) {
        const fallback = document.createElement('span');
        fallback.className = 'ranking-cover ranking-cover-fallback';
        fallback.setAttribute('aria-hidden', 'true');
        fallback.textContent = String(text || '?').trim().charAt(0).toUpperCase() || '?';
        return fallback;
    }

    function createCoverImage({ sourceId, id, className, onError }) {
        if (!sourceId || !id) return null;
        const image = document.createElement('img');
        image.className = className;
        image.loading = 'lazy';
        image.decoding = 'async';
        image.alt = '';
        image.src = coverArtUrl({ sourceId, id, size: 300 });
        image.addEventListener('error', onError
            ? () => onError(image)
            : () => image.remove());
        return image;
    }

    function renderRankingList({
        containerId,
        panel,
        data,
        labelKey,
        barClass,
        ariaLabel,
        metric,
        sourceId,
    }) {
        const container = document.getElementById(containerId);
        container.replaceChildren();
        container.setAttribute('role', 'list');
        container.setAttribute('aria-label', ariaLabel);
        const rows = beginArrayPanel(
            panel,
            data,
            (items) => items.length > 0 && items.some((item) => (
                Number(item.value) > 0
                || Number(item.count) > 0
                || Number(item.total_listen_sec) > 0
            )),
            t(panel === 'artists' ? 'empty.artists' : 'empty.albums'),
        );
        if (!rows) return;
        const maxValue = Math.max(1, ...rows.map((item) => Number(item.value) || 0));
        rows.forEach((item, index) => {
            const value = Number(item.value) || 0;
            const count = Number(item.count) || 0;
            const totalListenSec = Number(item.total_listen_sec) || 0;
            const percentage = Math.max(0, Math.min(100, Math.round((value / maxValue) * 100)));
            const labelValue = item[labelKey] != null ? String(item[labelKey]) : '';
            const row = document.createElement('div');
            row.className = 'ranking-row';
            row.setAttribute('role', 'listitem');
            const rank = document.createElement('div');
            rank.className = 'ranking-rank stat-value';
            rank.setAttribute('aria-hidden', 'true');
            rank.textContent = String(index + 1);
            const label = document.createElement('div');
            label.className = 'ranking-label';
            label.textContent = labelValue || '-';
            label.title = labelValue;
            const cover = createCoverImage({
                sourceId: item.source_id || sourceId,
                id: panel === 'albums' ? item.album_id : item.artist_id,
                className: 'ranking-cover',
                onError: (image) => image.replaceWith(createRankingFallback(labelValue)),
            });
            const barCell = document.createElement('div');
            barCell.className = 'ranking-bar-cell';
            barCell.setAttribute('aria-hidden', 'true');
            const track = document.createElement('div');
            track.className = 'ranking-track';
            const bar = document.createElement('div');
            bar.className = `ranking-bar ${barClass}`;
            bar.style.width = `${percentage}%`;
            track.appendChild(bar);
            barCell.appendChild(track);
            const countCell = document.createElement('div');
            countCell.className = 'ranking-count stat-value';
            const ariaSummary = metric === 'listen_time'
                ? `${t('label.listening')} ${formatDuration(value)} · ${formatPlays(count)}`
                : `${t('label.play')} ${formatPlays(count)} · ${formatDuration(totalListenSec)}`;
            countCell.setAttribute('aria-label', `${labelValue || '-'} · ${ariaSummary}`);
            const primary = document.createElement('div');
            primary.className = 'ranking-count-primary';
            primary.textContent = metric === 'listen_time'
                ? formatDuration(value)
                : formatPlays(count);
            const secondary = document.createElement('div');
            secondary.className = 'ranking-count-secondary';
            secondary.textContent = metric === 'listen_time'
                ? formatPlays(count)
                : formatDuration(totalListenSec);
            countCell.append(primary, secondary);
            row.append(rank, cover || createRankingFallback(labelValue), label, barCell, countCell);
            container.appendChild(row);
        });
        setPanelSummary(panel, t('aria.rankingSummary', {
            count: formatNumber(rows.length),
            top: String(rows[0][labelKey] || ''),
        }));
    }

    function renderTopArtistsChart(data, metric) {
        renderRankingList({
            containerId: 'topArtistsChart',
            panel: 'artists',
            data,
            labelKey: 'artist',
            barClass: 'ranking-bar-artists',
            ariaLabel: t(metric === 'listen_time' ? 'aria.artistsByTime' : 'aria.artistsByPlays'),
            metric,
            sourceId: getSourceId() || getFirstSourceId(),
        });
    }

    function renderTopAlbumsChart(data, metric) {
        renderRankingList({
            containerId: 'topAlbumsChart',
            panel: 'albums',
            data,
            labelKey: 'album',
            barClass: 'ranking-bar-albums',
            ariaLabel: t(metric === 'listen_time' ? 'aria.albumsByTime' : 'aria.albumsByPlays'),
            metric,
            sourceId: getSourceId() || getFirstSourceId(),
        });
    }

    function renderServerSourceBreakdown(data) {
        const container = document.getElementById('serverSourceBreakdown');
        container.replaceChildren();
        const rows = beginArrayPanel(
            'sources',
            data,
            (items) => items.length > 0,
            t('source.empty'),
        );
        if (!rows) return;
        rows.forEach((item) => {
            const row = document.createElement('div');
            row.className = 'source-breakdown-row';
            const name = document.createElement('span');
            name.className = 'source-breakdown-name';
            name.textContent = item.source_name || item.source_id || t('source.unknown');
            name.title = name.textContent;
            const count = document.createElement('span');
            count.className = 'source-breakdown-count stat-value';
            count.textContent = formatPlays(item.count);
            const duration = document.createElement('span');
            duration.className = 'source-breakdown-duration stat-value';
            duration.textContent = formatDuration(item.total_listen_sec);
            row.append(name, count, duration);
            container.appendChild(row);
        });
        setPanelSummary('sources', t('aria.sourcesSummary', {
            count: formatNumber(rows.length),
        }));
    }

    function render(snapshot, metric = 'plays') {
        lastSnapshot = snapshot;
        lastMetric = metric;
        renderSafely('summary', () => updateSummary(snapshot.summary, snapshot.transcoding));
        renderSafely('players', () => renderPlayerChart(snapshot.players));
        renderSafely('transcoding', () => renderTranscodingChart(snapshot.transcoding));
        renderSafely('hourly', () => renderHourlyChart(snapshot.hourly));
        renderSafely('daily', () => renderDailyChart(snapshot.daily));
        renderSafely('heatmap', () => renderWeekdayHourChart(snapshot.heatmap));
        renderSafely('artists', () => renderTopArtistsChart(snapshot.top_artists, metric));
        renderSafely('albums', () => renderTopAlbumsChart(snapshot.top_albums, metric));
        renderSafely('sources', () => renderServerSourceBreakdown(snapshot.servers));
    }

    return Object.freeze({ render, resize: resizeDashboardCharts, updateTheme });
}
