import { coverArtUrl } from '../format.js';

function formatElapsed(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const minutes = Math.floor(total / 60);
    const secs = total % 60;
    return `${minutes}:${String(secs).padStart(2, '0')}`;
}

/** Own the live now-playing request, rendering, and local elapsed-time clock. */
export function createNowPlaying({
    apiFetch,
    isAbortError,
    t,
    formatNumber,
    getScope,
    setPanelState,
    setPanelSummary,
}) {
    let requestController = null;
    let requestGeneration = 0;
    let loadedOnce = false;
    let ticker = null;
    let renderedAt = 0;
    let renderedEntries = [];

    function stopTicker() {
        if (ticker) {
            clearInterval(ticker);
            ticker = null;
        }
    }

    function startTicker() {
        stopTicker();
        if (!renderedEntries.length || document.hidden) return;
        ticker = setInterval(() => {
            const delta = Math.floor((Date.now() - renderedAt) / 1000);
            for (const entry of renderedEntries) {
                entry.span.textContent = formatElapsed(entry.baseline + delta);
            }
        }, 1000);
    }

    function cancel() {
        requestGeneration += 1;
        if (requestController) requestController.abort();
        requestController = null;
        stopTicker();
    }

    function createSourceBadge(item) {
        const sourceName = item && (item.source_name || item.source_id);
        if (!sourceName) return null;
        const badge = document.createElement('span');
        badge.className = 'source-badge';
        badge.textContent = String(sourceName);
        badge.title = t('label.source', { name: sourceName });
        badge.setAttribute('aria-label', badge.title);
        return badge;
    }

    function createCoverImage(item) {
        if (!item.source_id || !item.track_id) return null;
        const img = document.createElement('img');
        img.className = 'now-playing-cover';
        img.loading = 'lazy';
        img.decoding = 'async';
        img.alt = '';
        img.src = coverArtUrl({ sourceId: item.source_id, id: item.track_id, size: 300 });
        img.addEventListener('error', () => img.remove());
        return img;
    }

    function render(items, showSources) {
        const list = document.getElementById('nowPlayingList');
        const countEl = document.getElementById('nowPlayingCount');
        list.replaceChildren();
        renderedEntries = [];

        if (!Array.isArray(items)) {
            setPanelState('nowPlaying', 'error', t('error.nowPlaying'));
            countEl.textContent = '';
            stopTicker();
            return;
        }
        if (items.length === 0) {
            setPanelState('nowPlaying', 'empty', t('empty.nowPlaying'));
            countEl.textContent = '';
            stopTicker();
            return;
        }

        setPanelState('nowPlaying', 'ready');
        setPanelSummary('nowPlaying', t('aria.nowPlayingSummary', {
            count: formatNumber(items.length),
        }));
        countEl.textContent = `· ${items.length}`;

        items.forEach((item) => {
            const li = document.createElement('li');
            li.className = 'now-playing-item';
            const cover = createCoverImage(item);
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
            titleRow.append(title, artist);
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
            client.append(clientGlyph, clientLabel);
            const separator = document.createElement('span');
            separator.className = 'now-playing-separator';
            separator.textContent = '·';
            const user = document.createElement('span');
            user.className = 'now-playing-user';
            user.textContent = item.username || '-';
            user.title = item.username || '';
            subRow.append(client, separator, user);
            if (showSources) {
                const badge = createSourceBadge(item);
                if (badge) subRow.appendChild(badge);
            }
            meta.appendChild(subRow);
            li.appendChild(meta);

            const elapsed = document.createElement('span');
            elapsed.className = 'now-playing-elapsed stat-value';
            elapsed.textContent = formatElapsed(item.seconds_elapsed);
            li.appendChild(elapsed);
            list.appendChild(li);
            renderedEntries.push({
                span: elapsed,
                baseline: Math.max(0, Math.floor(Number(item.seconds_elapsed) || 0)),
            });
        });

        renderedAt = Date.now();
        startTicker();
    }

    async function refresh() {
        const scope = Object.freeze({ ...getScope() });
        const generation = ++requestGeneration;
        if (requestController) requestController.abort();
        const controller = new AbortController();
        requestController = controller;
        stopTicker();
        if (!loadedOnce) setPanelState('nowPlaying', 'loading');
        try {
            const sourceParam = scope.sourceId
                ? `?source_id=${encodeURIComponent(scope.sourceId)}`
                : '';
            const response = await apiFetch(`/api/stats/now-playing${sourceParam}`, {
                signal: controller.signal,
            });
            if (generation !== requestGeneration || controller.signal.aborted) return;
            if (!response.ok) throw new Error('now-playing request failed');
            const payload = await response.json();
            if (generation !== requestGeneration || controller.signal.aborted) return;
            const visible = scope.username
                ? payload.filter((item) => item.username === scope.username)
                : payload;
            render(visible, !scope.sourceId);
            if (Array.isArray(payload)) loadedOnce = true;
        } catch (error) {
            if (isAbortError(error) || generation !== requestGeneration) return;
            console.error('Error fetching now playing:', error);
            stopTicker();
            setPanelState('nowPlaying', 'error', t('error.nowPlaying'));
        } finally {
            if (generation === requestGeneration) requestController = null;
        }
    }

    return Object.freeze({ refresh, cancel, startTicker, stopTicker });
}
