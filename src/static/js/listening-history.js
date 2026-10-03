import { apiFetch, isAbortError, UnauthorizedError, UNAUTHORIZED_EVENT } from './http.js';
import { createLoginController } from './auth.js';
import { getFilters } from './filters.js';
import { readPreference } from './prefs.js';
import { buildStatsScopeQuery, entityDetailUrl, formatRecordedDuration } from './format.js';
import { createI18n } from '../localization.js';
import { pageMessages } from './i18n/index.js';

const i18n = createI18n({ messages: pageMessages('dashboard', 'review'), fallbackLocale: 'en' });
const t = (key, values) => i18n.t(key, values);
const scope = getFilters();
if (!new URLSearchParams(window.location.search).has('timezone')) {
    scope.timezone = readPreference('navidrome-timezone', 'browser');
}
if (scope.timezone === 'browser') {
    scope.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

let items = [];
let nextCursor = null;
let search = '';
let controller = null;
let generation = 0;
let failedAppend = false;
const records = document.getElementById('listeningRecords');
const moreButton = document.getElementById('listeningMore');
const retryButton = document.getElementById('listeningRetry');
const state = document.getElementById('listeningState');

function renderScope(auth = {}) {
    const windowLabel = scope.startDate && scope.endDate
        ? `${scope.startDate} – ${scope.endDate}`
        : scope.days === 0 ? t('window.all') : t('listens.days', { count: scope.days });
    document.getElementById('listeningScope').textContent = [
        windowLabel,
        `${t('history.user')}: ${auth.username || scope.username || t('user.all')}`,
        `${t('dashboard.serverFilter')}: ${auth.source_id || scope.sourceId || t('dashboard.allServers')}`,
        scope.timezone,
    ].join(' · ');
    document.getElementById('historyBackLink').href = `/?${buildStatsScopeQuery(scope)}`;
}

function appendIdentity(parent, text, identity) {
    const url = entityDetailUrl(identity, scope);
    const element = document.createElement(url ? 'a' : 'span');
    if (url) element.href = url;
    element.textContent = text;
    parent.appendChild(element);
}

function renderRecords() {
    const fragment = document.createDocumentFragment();
    for (const item of items) {
        const row = document.createElement('li');
        row.className = 'listening-record';
        const copy = document.createElement('div');
        copy.className = 'listening-record-copy';
        const title = document.createElement('div');
        title.className = 'listening-record-title';
        title.textContent = item.title || t('entity.unknownTrack');
        const context = document.createElement('div');
        context.className = 'listening-record-context';
        if (item.artist) appendIdentity(context, item.artist, { type: 'artist', name: item.artist });
        if (item.artist && item.album) context.append(' · ');
        if (item.album) appendIdentity(context, item.album, {
            type: 'album', name: item.album, id: item.album_id || '',
            sourceId: item.source_id || 'legacy', artist: item.artist || '',
        });
        const meta = document.createElement('div');
        meta.className = 'listening-record-meta';
        const time = new Date(item.played_at);
        const timestamp = Number.isNaN(time.getTime()) ? item.played_at || '—'
            : time.toLocaleString(i18n.getLocale(), { timeZone: scope.timezone });
        meta.textContent = [timestamp, item.username, item.client_name,
            item.source_name || item.source_id].filter(Boolean).join(' · ');
        copy.append(title, context, meta);
        const duration = document.createElement('span');
        duration.className = 'listening-record-duration';
        const quality = item.duration_quality;
        duration.textContent = quality === 'unknown' || item.listen_duration_sec == null ? '—'
            : `${quality === 'lower_bound' ? '≥ ' : quality === 'estimated' ? '≈ ' : ''}`
                + formatRecordedDuration(item.listen_duration_sec, t);
        const qualityKey = { lower_bound: 'entity.durationLowerBound', estimated: 'entity.durationEstimated', unknown: 'entity.durationUnknown' }[quality];
        if (qualityKey) duration.title = t(qualityKey);
        row.append(copy, duration);
        fragment.appendChild(row);
    }
    records.replaceChildren(fragment);
}

async function loadHistory({ append = false } = {}) {
    controller?.abort();
    controller = new AbortController();
    const currentController = controller;
    const currentGeneration = ++generation;
    failedAppend = append;
    if (!append) {
        items = [];
        nextCursor = null;
        renderRecords();
    }
    records.setAttribute('aria-busy', 'true');
    moreButton.disabled = true;
    retryButton.hidden = true;
    state.textContent = t('listens.loading');
    const params = new URLSearchParams(buildStatsScopeQuery(scope));
    if (search) params.set('search', search);
    if (append && nextCursor) params.set('cursor', nextCursor);
    try {
        const response = await apiFetch(`/api/stats/listens?${params}`, { signal: currentController.signal });
        if (!response.ok) throw new Error('history unavailable');
        const page = await response.json();
        if (currentGeneration !== generation || currentController.signal.aborted) return;
        items = append ? [...items, ...page.items] : page.items;
        nextCursor = page.next_cursor;
        renderRecords();
        moreButton.hidden = !nextCursor;
        state.textContent = items.length ? t('listens.loaded', { count: i18n.formatNumber(items.length) })
            : t('listens.empty');
    } catch (error) {
        if (isAbortError(error) || error instanceof UnauthorizedError || currentGeneration !== generation) return;
        state.textContent = t('listens.error');
        retryButton.hidden = false;
    } finally {
        if (currentGeneration === generation) {
            records.setAttribute('aria-busy', 'false');
            moreButton.disabled = false;
            if (!items.length) moreButton.hidden = true;
        }
    }
}

const login = createLoginController({
    overlayId: 'loginOverlay', tokenId: 'loginToken', inertSelector: '#listeningHistoryApp',
    useHiddenClass: true,
    onAuthenticated: async (auth) => { renderScope(auth); await loadHistory(); },
    onShow: () => { controller?.abort(); items = []; renderRecords(); },
});
window.addEventListener(UNAUTHORIZED_EVENT, () => login.show());
login.bind();
document.getElementById('loginForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const input = document.getElementById('loginToken');
    try { await login.submit(input.value); input.value = ''; }
    catch (_error) {
        const error = document.getElementById('loginError');
        error.textContent = t('auth.invalid'); error.classList.remove('hidden');
    }
});
document.getElementById('listeningSearchForm').addEventListener('submit', (event) => {
    event.preventDefault(); search = document.getElementById('listeningSearch').value.trim(); loadHistory();
});
document.getElementById('listeningClear').addEventListener('click', () => {
    document.getElementById('listeningSearch').value = ''; search = ''; loadHistory();
});
moreButton.addEventListener('click', () => loadHistory({ append: true }));
retryButton.addEventListener('click', () => loadHistory({ append: failedAppend }));

async function bootstrap() {
    i18n.setLocale(readPreference('navidrome-language', 'en'), { persist: false });
    i18n.translate();
    document.title = `${t('listens.title')} · Navidrome Stat`;
    renderScope();
    try {
        const response = await apiFetch('/api/auth/status');
        if (!response.ok) throw new Error('authentication status unavailable');
        const auth = await response.json();
        renderScope(auth);
        if (auth.auth_required && !auth.access_level) login.show();
        else await loadHistory();
    } catch (error) {
        if (!(error instanceof UnauthorizedError)) {
            state.textContent = t('listens.error');
            retryButton.hidden = false;
        }
    }
}

bootstrap();
