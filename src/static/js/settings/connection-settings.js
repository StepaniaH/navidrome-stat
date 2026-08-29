import {
    connectionTestMessageKey,
    createConnectionDiagnostics,
} from './connection-diagnostics.js';

export function createConnectionSettings({
    t,
    apiFetch,
    confirmDelete = (message) => window.confirm(message),
}) {
    const state = {
        fallback: null,
        message: null,
        passwordConfigured: false,
        readiness: 'unknown',
        servers: [],
    };
    let mounted = false;

    const diagnostics = createConnectionDiagnostics({
        t,
        apiFetch,
        onConfigure: () => {
            const savedEdit = document.querySelector('[data-server-action="edit"]');
            if (savedEdit) {
                document.getElementById('savedConnectionsTitle').scrollIntoView({
                    behavior: 'smooth',
                    block: 'start',
                });
                savedEdit.focus({ preventScroll: true });
                return;
            }
            document.getElementById('connectionFormTitle').scrollIntoView({
                behavior: 'smooth',
                block: 'start',
            });
            document.getElementById('sourceName').focus({ preventScroll: true });
        },
    });

    function responseOk(response) {
        return response && response.ok;
    }

    function setMessage(key, kind = 'info', values = {}) {
        state.message = { key, kind, values };
        const element = document.getElementById('sourceMessage');
        element.dataset.kind = kind;
        element.textContent = t(key, values);
        element.hidden = false;
    }

    function clearMessage() {
        state.message = null;
        document.getElementById('sourceMessage').hidden = true;
    }

    function renderReadiness() {
        const keyByState = {
            ok: 'source.statusOk',
            error: 'source.statusError',
            degraded: 'source.statusDegraded',
            unknown: 'source.statusUnknown',
        };
        const value = document.getElementById('sourceReadinessValue');
        value.textContent = t(keyByState[state.readiness] || keyByState.unknown);
        value.dataset.state = state.readiness;
        value.closest('.status-line').dataset.state = state.readiness;
    }

    function renderFormState() {
        const editing = Boolean(document.getElementById('sourceForm').dataset.editingId);
        const password = document.getElementById('sourcePass');
        document.getElementById('saveSourceBtn').textContent = t(
            editing ? 'source.update' : 'source.save',
        );
        document.getElementById('cancelSourceEditBtn').hidden = !editing;
        password.required = !editing;
        password.placeholder = state.passwordConfigured
            ? t('source.passwordConfigured')
            : t('source.passwordPlaceholder');
    }

    function resetForm() {
        const form = document.getElementById('sourceForm');
        form.reset();
        form.removeAttribute('data-editing-id');
        state.passwordConfigured = false;
        renderFormState();
    }

    function renderFallback() {
        const fallback = state.fallback;
        document.getElementById('sourceFallbackSummary').textContent = (
            fallback?.url && fallback?.username && fallback?.password_configured
                ? t('source.fallbackConfigured', {
                    username: fallback.username,
                    url: fallback.url,
                })
                : t('source.fallbackMissing')
        );
    }

    async function testSavedServer(server, button, target) {
        button.disabled = true;
        target.hidden = false;
        target.dataset.kind = 'info';
        target.textContent = t('source.testing');
        try {
            const response = await apiFetch(`/api/servers/${encodeURIComponent(server.id)}/test`, {
                method: 'POST',
            });
            if (!responseOk(response)) throw new Error('server test failed');
            const result = await response.json();
            target.dataset.kind = result.ok ? 'success' : 'error';
            target.textContent = t(connectionTestMessageKey(result.category, result.ok));
            await diagnostics.load().catch(() => {});
        } catch (error) {
            if (error.message === 'unauthorized') target.hidden = true;
            else {
                target.dataset.kind = 'error';
                target.textContent = t('source.testFailed');
            }
        } finally {
            button.disabled = false;
        }
    }

    function editServer(server) {
        document.getElementById('sourceName').value = server.display_name;
        document.getElementById('sourceUrl').value = server.url;
        document.getElementById('sourceUser').value = server.username;
        document.getElementById('sourcePass').value = '';
        document.getElementById('sourceBackfillPlaylist').value = server.backfill_playlist_id || '';
        document.getElementById('sourceEnabled').checked = Boolean(server.enabled);
        document.getElementById('sourceForm').dataset.editingId = server.id;
        state.passwordConfigured = Boolean(server.password_configured);
        renderFormState();
        document.getElementById('sourceName').focus();
    }

    async function deleteServer(server) {
        if (!confirmDelete(t('source.deleteConfirm', { name: server.display_name }))) return;
        try {
            const response = await apiFetch(`/api/servers/${encodeURIComponent(server.id)}`, {
                method: 'DELETE',
            });
            if (!responseOk(response)) {
                setMessage('source.saveFailed', 'error');
                return;
            }
            if (document.getElementById('sourceForm').dataset.editingId === server.id) resetForm();
            await Promise.allSettled([loadServers(), diagnostics.load()]);
        } catch (error) {
            if (error.message !== 'unauthorized') setMessage('source.saveFailed', 'error');
        }
    }

    function renderServers() {
        const list = document.getElementById('serverList');
        list.replaceChildren();
        document.getElementById('serverEmpty').hidden = state.servers.length !== 0;
        document.getElementById('privacyFirstRun').hidden = state.servers.length !== 0;
        for (const server of state.servers) {
            const row = document.createElement('div');
            row.className = 'server-row';
            const identity = document.createElement('div');
            identity.className = 'server-identity';
            const name = document.createElement('strong');
            name.textContent = server.display_name;
            const url = document.createElement('span');
            url.className = 'server-url';
            url.textContent = server.url;
            const status = document.createElement('span');
            status.className = 'server-status';
            status.dataset.enabled = String(Boolean(server.enabled));
            status.textContent = t(server.enabled ? 'source.enabledStatus' : 'source.disabledStatus');
            const detail = document.createElement('div');
            detail.className = 'server-detail-line';
            detail.append(url, status);
            if (server.backfill_playlist_id) {
                const backfill = document.createElement('span');
                backfill.className = 'server-backfill-status';
                const summary = server.backfill_summary || {};
                backfill.textContent = t('source.backfillStatus', {
                    runs: summary.run_count || 0,
                    imported: summary.imported_total || 0,
                    errors: summary.error_count || 0,
                });
                detail.appendChild(backfill);
            }
            const testStatus = document.createElement('span');
            testStatus.className = 'server-test-status';
            testStatus.hidden = true;
            identity.append(name, detail, testStatus);

            const actions = document.createElement('div');
            actions.className = 'row-actions';
            const testButton = document.createElement('button');
            testButton.type = 'button';
            testButton.className = 'text-button';
            testButton.textContent = t('common.test');
            testButton.addEventListener('click', () => testSavedServer(server, testButton, testStatus));
            const editButton = document.createElement('button');
            editButton.type = 'button';
            editButton.className = 'text-button';
            editButton.dataset.serverAction = 'edit';
            editButton.textContent = t('common.edit');
            editButton.addEventListener('click', () => editServer(server));
            const deleteButton = document.createElement('button');
            deleteButton.type = 'button';
            deleteButton.className = 'text-button danger';
            deleteButton.textContent = t('common.delete');
            deleteButton.addEventListener('click', () => deleteServer(server));
            actions.append(testButton, editButton, deleteButton);
            row.append(identity, actions);
            list.appendChild(row);
        }
    }

    async function loadServers() {
        try {
            const response = await apiFetch('/api/servers');
            if (!responseOk(response)) throw new Error('servers failed');
            state.servers = await response.json();
            const editingId = document.getElementById('sourceForm').dataset.editingId;
            if (editingId && !state.servers.some((server) => server.id === editingId)) resetForm();
            renderServers();
        } catch (error) {
            if (error.message !== 'unauthorized') setMessage('source.loadFailed', 'error');
            throw error;
        }
    }

    async function loadFallback() {
        try {
            const response = await apiFetch('/api/source/config');
            if (!responseOk(response)) throw new Error('source config failed');
            state.fallback = await response.json();
            renderFallback();
        } catch (error) {
            if (error.message !== 'unauthorized') setMessage('source.configFailed', 'error');
            throw error;
        }
    }

    async function refreshStatus() {
        try {
            const response = await apiFetch('/health/ready');
            if (!responseOk(response)) state.readiness = 'degraded';
            else {
                const data = await response.json();
                const upstream = data.checks && data.checks.upstream;
                if (upstream === 'ok') state.readiness = 'ok';
                else if (upstream === 'error') state.readiness = 'error';
                else if (data.status === 'degraded') state.readiness = 'degraded';
                else state.readiness = 'unknown';
            }
        } catch (_error) {
            state.readiness = 'unknown';
        }
        renderReadiness();
    }

    async function saveForm(event) {
        event.preventDefault();
        const form = event.currentTarget;
        const saveButton = document.getElementById('saveSourceBtn');
        const displayName = document.getElementById('sourceName').value.trim();
        const url = document.getElementById('sourceUrl').value.trim();
        const username = document.getElementById('sourceUser').value.trim();
        const password = document.getElementById('sourcePass').value;
        const enabled = document.getElementById('sourceEnabled').checked;
        const backfillPlaylistId = document.getElementById('sourceBackfillPlaylist').value.trim() || null;
        const editingId = form.dataset.editingId;
        if (!displayName) return setMessage('source.nameRequired', 'error');
        if (!url) return setMessage('source.urlRequired', 'error');
        if (!username) return setMessage('source.userRequired', 'error');
        if (!editingId && !password) return setMessage('source.passwordRequired', 'error');
        saveButton.disabled = true;
        try {
            const response = await apiFetch(
                editingId ? `/api/servers/${encodeURIComponent(editingId)}` : '/api/servers',
                {
                    method: editingId ? 'PUT' : 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        display_name: displayName,
                        url,
                        username,
                        password,
                        enabled,
                        backfill_playlist_id: backfillPlaylistId,
                    }),
                },
            );
            if (!responseOk(response)) throw new Error('save failed');
            resetForm();
            setMessage('source.saved', 'success');
            await Promise.allSettled([loadServers(), refreshStatus(), diagnostics.load()]);
        } catch (error) {
            if (error.message !== 'unauthorized') setMessage('source.saveFailed', 'error');
        } finally {
            saveButton.disabled = false;
        }
    }

    async function testForm() {
        const button = document.getElementById('testSourceBtn');
        const form = document.getElementById('sourceForm');
        setMessage('source.testing');
        const displayName = document.getElementById('sourceName').value.trim();
        const url = document.getElementById('sourceUrl').value.trim();
        const username = document.getElementById('sourceUser').value.trim();
        const password = document.getElementById('sourcePass').value;
        const enabled = document.getElementById('sourceEnabled').checked;
        const editingId = form.dataset.editingId;
        if (!url) return setMessage('source.urlRequired', 'error');
        if (!username) return setMessage('source.userRequired', 'error');
        if (!editingId && !password) return setMessage('source.passwordRequired', 'error');
        const payload = editingId
            ? { display_name: displayName || 'Navidrome', url, username, password, enabled }
            : { url, username, password };
        button.disabled = true;
        try {
            const endpoint = editingId
                ? `/api/servers/${encodeURIComponent(editingId)}/test`
                : '/api/source/test';
            const response = await apiFetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!responseOk(response)) throw new Error('test failed');
            const result = await response.json();
            setMessage(
                connectionTestMessageKey(result.category, result.ok),
                result.ok ? 'success' : 'error',
            );
            await diagnostics.load().catch(() => {});
        } catch (error) {
            if (error.message !== 'unauthorized') setMessage('source.testFailed', 'error');
        } finally {
            button.disabled = false;
        }
    }

    function mount() {
        if (mounted) return;
        mounted = true;
        diagnostics.mount();
        document.getElementById('refreshSourceStatus').addEventListener('click', () => {
            Promise.allSettled([refreshStatus(), diagnostics.load()]);
        });
        document.getElementById('cancelSourceEditBtn').addEventListener('click', () => {
            resetForm();
            clearMessage();
            document.getElementById('sourceName').focus();
        });
        document.getElementById('sourceForm').addEventListener('submit', saveForm);
        document.getElementById('testSourceBtn').addEventListener('click', testForm);
    }

    function localize() {
        diagnostics.localize();
        renderReadiness();
        renderFormState();
        renderFallback();
        renderServers();
        if (state.message) setMessage(state.message.key, state.message.kind, state.message.values);
    }

    async function load() {
        const results = await Promise.allSettled([
            loadFallback(),
            loadServers(),
            refreshStatus(),
            diagnostics.load(),
        ]);
        const failure = results.find((result) => (
            result.status === 'rejected' && result.reason?.message !== 'unauthorized'
        ));
        if (failure) throw failure.reason;
        const unauthorized = results.find((result) => (
            result.status === 'rejected' && result.reason?.message === 'unauthorized'
        ));
        if (unauthorized) throw unauthorized.reason;
    }

    return {
        load,
        localize,
        mount,
        refreshStatus,
    };
}
