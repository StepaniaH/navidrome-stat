import { coverArtUrl } from '../format.js';
import { attachPopover } from '../listbox.js';
import { onPreferenceChange, readPreference, writePreference } from '../prefs.js';

const HISTORY_COLUMNS_KEY = 'navidrome-history-columns';
const HISTORY_COLUMNS = Object.freeze([
    { id: 'user', label: 'history.user', cell: 'history-cell-user', col: 'history-col-user' },
    { id: 'track', label: 'history.track', cell: 'history-cell-title', col: 'history-col-track' },
    { id: 'artist', label: 'history.artist', cell: 'history-cell-artist', col: 'history-col-artist' },
    { id: 'album', label: 'history.album', cell: 'history-cell-album', col: 'history-col-album' },
    { id: 'played', label: 'history.lastPlayed', cell: 'history-cell-played', col: 'history-col-played' },
    { id: 'count', label: 'history.plays', cell: 'history-cell-count', col: 'history-col-count' },
]);

/** Own history rendering, column preferences, and first-use presentation. */
export function createHistory({
    t,
    formatNumber,
    getLocale,
    isFiltered,
    beginArrayPanel,
    setPanelSummary,
}) {
    let columns = readColumns();
    let updateColumnPanel = () => {};

    function allColumns() {
        return new Set(HISTORY_COLUMNS.map((column) => column.id));
    }

    function readColumns() {
        const raw = readPreference(HISTORY_COLUMNS_KEY, '');
        if (!raw) return allColumns();
        const saved = new Set(raw.split(',').filter(
            (id) => HISTORY_COLUMNS.some((column) => column.id === id),
        ));
        return saved.size ? saved : allColumns();
    }

    function applyColumns() {
        for (const column of HISTORY_COLUMNS) {
            const visible = columns.has(column.id);
            document.querySelectorAll(
                `.history-table .${column.cell}, .history-table col.${column.col}`,
            ).forEach((element) => element.classList.toggle('column-hidden', !visible));
        }
    }

    function mount() {
        const button = document.getElementById('historyColumnsButton');
        const panel = document.getElementById('historyColumnsPanel');
        attachPopover({ trigger: button, panel });
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
                if (columns.has(column.id)) columns.delete(column.id);
                else columns.add(column.id);
                writePreference(HISTORY_COLUMNS_KEY, [...columns].join(','));
                columns = readColumns();
                updateColumnPanel();
                applyColumns();
            });
            list.appendChild(option);
        }
        panel.replaceChildren(list);
        updateColumnPanel = () => {
            panel.querySelectorAll('.column-option').forEach((option) => {
                const column = HISTORY_COLUMNS.find(({ id }) => id === option.dataset.columnId);
                if (!column) return;
                const active = columns.has(column.id);
                option.querySelector('.column-option-label').textContent = t(column.label);
                option.setAttribute('aria-pressed', active ? 'true' : 'false');
                option.classList.toggle('column-option-off', !active);
                option.disabled = active && columns.size === 1;
            });
        };
        updateColumnPanel();
        applyColumns();
        onPreferenceChange(HISTORY_COLUMNS_KEY, () => {
            columns = readColumns();
            updateColumnPanel();
            applyColumns();
        });
    }

    function formatPlayedAt(isoString) {
        if (!isoString) return '—';
        const date = new Date(isoString);
        if (Number.isNaN(date.getTime())) return '—';
        return date.toLocaleString(getLocale(), {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    function createSourceLabel(item) {
        const sourceName = item && (item.source_name || item.source_id);
        if (!sourceName) return null;
        const label = document.createElement('span');
        label.className = 'history-user-source';
        label.textContent = String(sourceName);
        label.title = t('label.source', { name: sourceName });
        return label;
    }

    function createTrackCover(item) {
        if (!item.source_id || !item.track_id) return null;
        const image = document.createElement('img');
        image.className = 'history-cover';
        image.loading = 'lazy';
        image.decoding = 'async';
        image.alt = '';
        image.src = coverArtUrl({ sourceId: item.source_id, id: item.track_id, size: 300 });
        image.addEventListener('error', () => image.remove());
        return image;
    }

    function render(data, { showSources = true } = {}) {
        const tbody = document.getElementById('historyTable');
        tbody.replaceChildren();
        const filteredEmpty = isFiltered();
        const emptyLines = document.getElementById('historyEmpty').querySelectorAll('p');
        if (emptyLines[0]) {
            emptyLines[0].textContent = t(
                filteredEmpty ? 'history.filterEmpty' : 'history.empty',
            );
        }
        if (emptyLines[1]) {
            emptyLines[1].textContent = t(
                filteredEmpty ? 'history.filterEmptyHint' : 'history.emptyHint',
            );
        }
        const rows = beginArrayPanel(
            'history',
            data,
            (items) => items.length > 0,
            t(filteredEmpty ? 'history.filterEmpty' : 'history.empty'),
        );
        if (!rows) return;

        rows.forEach((item) => {
            const row = document.createElement('tr');
            row.className = 'history-row';
            const userCell = document.createElement('td');
            userCell.className = 'history-cell history-cell-user';
            const userWrap = document.createElement('span');
            userWrap.className = 'history-user-wrap';
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
            userWrap.append(avatar, userMeta);
            userCell.appendChild(userWrap);

            const titleCell = document.createElement('td');
            titleCell.className = 'history-cell history-cell-title';
            const titleWrap = document.createElement('div');
            titleWrap.className = 'history-title-wrap';
            const cover = createTrackCover(item);
            if (cover) titleWrap.appendChild(cover);
            const title = document.createElement('div');
            title.className = 'history-primary';
            title.textContent = item.title || '-';
            title.title = item.title || '';
            titleWrap.appendChild(title);
            titleCell.appendChild(titleWrap);

            const artistCell = document.createElement('td');
            artistCell.className = 'history-cell history-cell-artist';
            artistCell.textContent = item.artist || '-';
            artistCell.title = item.artist || '';
            const albumCell = document.createElement('td');
            albumCell.className = 'history-cell history-cell-album';
            albumCell.textContent = item.album || '-';
            albumCell.title = item.album || '';
            const playedCell = document.createElement('td');
            playedCell.className = 'history-cell history-cell-played';
            playedCell.textContent = formatPlayedAt(item.last_played_at);
            const countCell = document.createElement('td');
            countCell.className = 'history-cell history-cell-count';
            const count = document.createElement('span');
            count.className = 'history-count-badge stat-value';
            count.textContent = String(item.play_count ?? 0);
            countCell.appendChild(count);
            row.append(userCell, titleCell, artistCell, albumCell, playedCell, countCell);
            tbody.appendChild(row);
        });
        setPanelSummary('history', t('aria.historySummary', {
            count: formatNumber(rows.length),
        }));
        applyColumns();
    }

    function updateFirstUse(snapshot) {
        const summary = snapshot && snapshot.summary;
        const noPlays = summary && Number(summary.total_plays) === 0;
        const noHistory = Array.isArray(snapshot && snapshot.history)
            && snapshot.history.length === 0;
        const firstUse = noPlays && noHistory && !isFiltered();
        document.getElementById('newUserGuide').classList.toggle('hidden', !firstUse);
        document.querySelectorAll('[data-history-analysis]').forEach((section) => {
            section.classList.toggle('hidden', firstUse);
        });
    }

    function localize() {
        updateColumnPanel();
    }

    return Object.freeze({ mount, render, updateFirstUse, localize });
}
