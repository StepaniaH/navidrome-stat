import { buildStatsScopeQuery } from '../format.js';
import { attachPopover } from '../listbox.js';

/** Own the on-demand counted-vs-short-play explanation and request lifecycle. */
export function createPlayAccounting({ apiFetch, isAbortError, t, formatNumber, getScope }) {
    let requestController = null;
    let requestGeneration = 0;
    let loadedQuery = null;
    let pendingQuery = null;
    let lastPayload = null;
    let popover = null;

    function setState(state) {
        const status = document.getElementById('playAccountingStatus');
        const states = {
            loading: document.getElementById('playAccountingLoading'),
            content: document.getElementById('playAccountingContent'),
            empty: document.getElementById('playAccountingEmpty'),
            error: document.getElementById('playAccountingError'),
        };
        Object.entries(states).forEach(([name, element]) => {
            element.classList.toggle('hidden', name !== state);
        });
        status.setAttribute('aria-busy', state === 'loading' ? 'true' : 'false');
    }

    function render(payload) {
        lastPayload = payload;
        if (payload.attemptCount === 0) {
            setState('empty');
            return;
        }
        document.getElementById('playAccountingValue').textContent = t(
            'insight.shortPlaysValue',
            {
                short: formatNumber(payload.shortCount),
                rate: formatNumber(Math.round(payload.rate * 10) / 10),
            },
        );
        setState('content');
    }

    async function refresh({ force = false } = {}) {
        const query = buildStatsScopeQuery(getScope());
        if (!force && (query === loadedQuery || query === pendingQuery)) return;
        const generation = ++requestGeneration;
        if (requestController) requestController.abort();
        const controller = new AbortController();
        requestController = controller;
        pendingQuery = query;
        setState('loading');
        try {
            const response = await apiFetch(`/api/stats/short-plays?${query}`, {
                signal: controller.signal,
            });
            if (generation !== requestGeneration || controller.signal.aborted) return;
            if (!response.ok) throw new Error('playback accounting request failed');
            const payload = await response.json();
            if (generation !== requestGeneration || controller.signal.aborted) return;
            const shortCount = Number(payload.short_count);
            const attemptCount = Number(payload.attempt_count);
            const rate = Number(payload.short_play_rate_pct);
            if (
                !Number.isFinite(shortCount)
                || !Number.isFinite(attemptCount)
                || !Number.isFinite(rate)
                || shortCount < 0
                || attemptCount < shortCount
                || rate < 0
                || rate > 100
            ) {
                throw new Error('invalid playback accounting response');
            }
            loadedQuery = query;
            render({ shortCount, attemptCount, rate });
        } catch (error) {
            if (isAbortError(error) || generation !== requestGeneration) return;
            setState('error');
            console.error('Error fetching playback accounting:', error);
        } finally {
            if (generation === requestGeneration) {
                requestController = null;
                pendingQuery = null;
            }
        }
    }

    function cancel() {
        requestGeneration += 1;
        if (requestController) requestController.abort();
        requestController = null;
        pendingQuery = null;
    }

    function invalidate() {
        if (!popover?.open) loadedQuery = null;
    }

    function mount() {
        const trigger = document.getElementById('playAccountingButton');
        const panel = document.getElementById('playAccountingPanel');
        popover = attachPopover({ trigger, panel });
        trigger.addEventListener('click', () => {
            if (popover.open) refresh();
        });
        document.getElementById('playAccountingClose').addEventListener('click', () => {
            popover.setOpen(false, { restoreFocus: true });
        });
        document.getElementById('playAccountingRetry').addEventListener('click', () => {
            refresh({ force: true });
        });
    }

    function localize() {
        if (lastPayload) render(lastPayload);
    }

    return Object.freeze({
        mount,
        refresh,
        cancel,
        invalidate,
        localize,
        isOpen: () => Boolean(popover?.open),
    });
}
