const IMPORT_MAX_BYTES = 5 * 1024 * 1024;

/**
 * Own the privacy tab's retention and per-user data lifecycle.
 *
 * The page shell only needs mount(), load(), and localize(); request
 * cancellation, destructive previews, and draft state stay inside.
 */
export function createPrivacySettings({
    t,
    formatNumber,
    apiFetch,
    isAbortError,
    registerListbox,
    showBanner,
    confirmAction = (message) => window.confirm(message),
}) {
    const state = {
        privacyStatus: 'loading',
        privacySettings: null,
        storageSnapshot: null,
        users: [],
        usersStatus: 'loading',
    };
    let userSelect = null;
    let previewTimer = null;
    let retentionPreviewController = null;
    let userPreviewController = null;

    function localizedCount(value) {
        return formatNumber(value);
    }

    function formatBytes(bytes) {
        const value = Number(bytes) || 0;
        if (value < 1024) return `${value} B`;
        if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
        if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(2)} MB`;
        return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    }

    function getRetentionDaysFromUi() {
        if (document.getElementById('modePermanent').checked) return null;
        return Number(document.getElementById('retentionSlider').value);
    }

    function renderPolicySummary() {
        const summary = document.getElementById('policySummary');
        const retry = document.getElementById('policyRetry');
        summary.dataset.state = state.privacyStatus;
        summary.closest('.status-line').dataset.state = state.privacyStatus;
        retry.hidden = state.privacyStatus !== 'error';
        if (state.privacyStatus === 'loading') {
            summary.textContent = t('privacy.policyLoading');
            return;
        }
        if (state.privacyStatus === 'error') {
            summary.textContent = t('privacy.policyLoadError');
            return;
        }
        const persistedDays = state.privacySettings?.retention_days ?? null;
        summary.textContent = persistedDays === null
            ? t('privacy.summaryPermanent')
            : t('privacy.summaryFinite', { days: persistedDays });
    }

    function retentionDraftIsDirty() {
        if (state.privacyStatus !== 'ready' || !state.privacySettings) return false;
        const persisted = state.privacySettings.retention_days ?? null;
        return getRetentionDaysFromUi() !== persisted;
    }

    function renderRetentionActions() {
        const ready = state.privacyStatus === 'ready' && Boolean(state.privacySettings);
        const dirty = ready && retentionDraftIsDirty();
        const persistedFinite = ready && state.privacySettings.retention_days !== null;
        document.getElementById('saveRetentionBtn').disabled = !ready || !dirty;
        document.getElementById('applyRetentionBtn').disabled = !persistedFinite || dirty;
    }

    function updateStorageDisplay(preview) {
        if (!preview) {
            document.getElementById('storageEstimatedDetail').textContent = t('privacy.storagePending');
            return;
        }
        document.getElementById('storageCurrentSize').textContent = formatBytes(preview.database_bytes);
        document.getElementById('storageCurrentRecords').textContent = t('common.records', {
            count: localizedCount(preview.total_records),
        });
        document.getElementById('storageEstimatedSize').textContent = formatBytes(preview.database_bytes);
        if (document.getElementById('modePermanent').checked) {
            document.getElementById('storageEstimatedDetail').textContent = t('privacy.storagePermanent');
            return;
        }
        const deletedPayload = Math.max(Number(preview.bytes_to_delete) || 0, 0);
        document.getElementById('storageEstimatedDetail').textContent = t('privacy.storageRelease', {
            bytes: formatBytes(deletedPayload),
            count: localizedCount(preview.records_to_delete),
        });
    }

    function retentionPreviewText(preview) {
        if (!preview) return t('privacy.storagePending');
        if (preview.retention_days === null) return t('privacy.previewPermanent');
        const deletedPayload = Math.max(Number(preview.bytes_to_delete) || 0, 0);
        return t('privacy.previewFinite', {
            label: t('common.days', { count: preview.retention_days }),
            count: localizedCount(preview.records_to_delete),
            bytes: formatBytes(deletedPayload),
        });
    }

    function updateRetentionPreviewText(preview) {
        document.getElementById('retentionPreview').textContent = retentionPreviewText(preview);
    }

    function renderUserOptions() {
        if (!userSelect) return;
        if (state.usersStatus === 'loading') {
            userSelect.setOptions([], { preserveValue: false, placeholder: 'privacy.userLoading' });
            userSelect.setDisabled(true);
            return;
        }
        const options = state.users.map((user) => ({
            value: user.username,
            label: () => t('privacy.userOption', {
                username: user.username,
                count: localizedCount(user.record_count),
            }),
        }));
        userSelect.setDisabled(options.length === 0);
        userSelect.setOptions(options, {
            preserveValue: true,
            selectFirst: true,
            placeholder: 'privacy.noUsers',
        });
    }

    function updateRetentionModeVisuals() {
        document.querySelectorAll('.retention-choice').forEach((choice) => {
            const radio = choice.querySelector('input[type="radio"]');
            choice.dataset.selected = radio && radio.checked ? 'true' : 'false';
        });
    }

    function applyRetentionUi(permanent, days) {
        document.getElementById('modePermanent').checked = Boolean(permanent);
        document.getElementById('modeFinite').checked = !permanent;
        const effectiveDays = Number(days) || 90;
        document.getElementById('retentionSlider').value = String(effectiveDays);
        document.getElementById('retentionValue').textContent = t('common.days', { count: effectiveDays });
        document.getElementById('retentionSliderWrap').hidden = Boolean(permanent);
        updateRetentionModeVisuals();
        renderPolicySummary();
        renderRetentionActions();
    }

    async function refreshRetentionPreview(days = getRetentionDaysFromUi()) {
        if (retentionPreviewController) retentionPreviewController.abort();
        const controller = new AbortController();
        retentionPreviewController = controller;
        const endpoint = days === null
            ? '/api/privacy/storage'
            : `/api/privacy/retention/preview?days=${encodeURIComponent(days)}`;
        const response = await apiFetch(endpoint, { signal: controller.signal });
        if (!response.ok) throw new Error('preview failed');
        const payload = await response.json();
        const data = days === null
            ? {
                ...payload,
                retention_days: null,
                records_to_delete: 0,
                history_records_to_delete: 0,
                attempt_records_to_delete: 0,
                bytes_to_delete: 0,
                estimated_database_bytes_after: payload.database_bytes,
            }
            : payload;
        if (retentionPreviewController !== controller) return null;
        state.storageSnapshot = data;
        updateStorageDisplay(data);
        updateRetentionPreviewText(data);
        retentionPreviewController = null;
        return data;
    }

    function scheduleRetentionPreview() {
        if (previewTimer) window.clearTimeout(previewTimer);
        previewTimer = window.setTimeout(() => {
            refreshRetentionPreview().catch((error) => {
                if (!isAbortError(error)) showBanner('error', t('error.generic'));
            });
        }, 160);
    }

    async function loadPrivacySettings() {
        state.privacyStatus = 'loading';
        renderPolicySummary();
        try {
            const response = await apiFetch('/api/privacy/settings');
            if (!response.ok) throw new Error('privacy settings failed');
            const data = await response.json();
            state.privacySettings = data;
            state.privacyStatus = 'ready';
            applyRetentionUi(Boolean(data.permanent), data.retention_days);
            try {
                await refreshRetentionPreview();
            } catch (previewError) {
                if (previewError.message === 'unauthorized') throw previewError;
                if (isAbortError(previewError)) return;
                state.storageSnapshot = null;
                updateStorageDisplay(null);
                updateRetentionPreviewText(null);
            }
        } catch (error) {
            if (error.message === 'unauthorized') throw error;
            state.privacyStatus = 'error';
            renderPolicySummary();
            renderRetentionActions();
            throw error;
        }
    }

    async function refreshUserPreview() {
        const username = userSelect?.getValue();
        const preview = document.getElementById('userPreview');
        if (userPreviewController) userPreviewController.abort();
        if (!username) {
            preview.textContent = t('privacy.userPreview', { count: 0 });
            userPreviewController = null;
            return null;
        }
        const controller = new AbortController();
        userPreviewController = controller;
        const response = await apiFetch(
            `/api/privacy/users/${encodeURIComponent(username)}/delete/preview`,
            { signal: controller.signal },
        );
        if (!response.ok) throw new Error('user preview failed');
        const data = await response.json();
        if (userPreviewController !== controller || userSelect?.getValue() !== username) return null;
        const text = t('privacy.userPreview', {
            count: localizedCount(data.records_to_delete),
        });
        preview.textContent = text;
        userPreviewController = null;
        return { username, count: data.records_to_delete, text };
    }

    async function loadUsers() {
        state.usersStatus = 'loading';
        renderUserOptions();
        try {
            const response = await apiFetch('/api/privacy/users');
            if (!response.ok) throw new Error('users failed');
            state.users = await response.json();
            state.usersStatus = 'ready';
            renderUserOptions();
            await refreshUserPreview();
        } catch (error) {
            if (isAbortError(error)) return;
            if (error.message === 'unauthorized') throw error;
            state.users = [];
            state.usersStatus = 'error';
            renderUserOptions();
            throw error;
        }
    }

    function bindRetentionControls() {
        document.getElementById('policyRetry').addEventListener('click', () => {
            loadPrivacySettings().catch(() => showBanner('error', t('error.settingsLoad')));
        });
        document.querySelectorAll('input[name="retentionMode"]').forEach((radio) => {
            radio.addEventListener('change', () => {
                updateRetentionModeVisuals();
                const permanent = document.getElementById('modePermanent').checked;
                document.getElementById('retentionSliderWrap').hidden = permanent;
                renderPolicySummary();
                renderRetentionActions();
                refreshRetentionPreview().catch((error) => {
                    if (!isAbortError(error)) showBanner('error', t('error.generic'));
                });
            });
        });
        document.getElementById('retentionSlider').addEventListener('input', (event) => {
            document.getElementById('retentionValue').textContent = t('common.days', {
                count: event.target.value,
            });
            renderPolicySummary();
            renderRetentionActions();
            scheduleRetentionPreview();
        });
        document.getElementById('saveRetentionBtn').addEventListener('click', async () => {
            const button = document.getElementById('saveRetentionBtn');
            const draftDays = getRetentionDaysFromUi();
            if (previewTimer) window.clearTimeout(previewTimer);
            previewTimer = null;
            button.disabled = true;
            try {
                const preview = await refreshRetentionPreview(draftDays);
                if (!preview) return;
                if (draftDays !== null && !confirmAction(t('privacy.retentionSaveConfirm', {
                    preview: retentionPreviewText(preview),
                }))) return;
                const response = await apiFetch('/api/privacy/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ retention_days: draftDays }),
                });
                if (!response.ok) throw new Error('save failed');
                state.privacySettings = await response.json();
                state.privacyStatus = 'ready';
                renderPolicySummary();
                renderRetentionActions();
                showBanner('success', t('privacy.retentionSaved'));
                await refreshRetentionPreview(state.privacySettings.retention_days ?? null);
            } catch (error) {
                if (error.message !== 'unauthorized' && !isAbortError(error)) {
                    showBanner('error', t('error.generic'));
                }
            } finally {
                renderRetentionActions();
            }
        });
        document.getElementById('applyRetentionBtn').addEventListener('click', async () => {
            const button = document.getElementById('applyRetentionBtn');
            const persistedDays = state.privacySettings?.retention_days ?? null;
            if (previewTimer) window.clearTimeout(previewTimer);
            previewTimer = null;
            if (retentionDraftIsDirty()) {
                showBanner('error', t('privacy.saveFirst'));
                return;
            }
            if (persistedDays === null) {
                showBanner('error', t('privacy.noCleanup'));
                return;
            }
            button.disabled = true;
            try {
                const preview = await refreshRetentionPreview(persistedDays);
                if (!preview) return;
                if (!confirmAction(t('privacy.cleanupConfirm', {
                    preview: retentionPreviewText(preview),
                }))) return;
                const response = await apiFetch('/api/privacy/retention/apply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        confirm: true,
                        expected_retention_days: persistedDays,
                    }),
                });
                if (response.status === 409) {
                    await loadPrivacySettings();
                    showBanner('error', t('privacy.policyChanged'));
                    return;
                }
                if (!response.ok) throw new Error('cleanup failed');
                const data = await response.json();
                showBanner('success', t('privacy.cleanupSuccess', {
                    count: localizedCount(data.deleted),
                }));
                await Promise.all([loadUsers(), refreshRetentionPreview(persistedDays)]);
            } catch (error) {
                if (error.message !== 'unauthorized' && !isAbortError(error)) {
                    showBanner('error', t('privacy.cleanupFailed'));
                }
            } finally {
                renderRetentionActions();
            }
        });
    }

    function bindUserDataControls() {
        document.getElementById('exportBtn').addEventListener('click', async () => {
            const username = userSelect.getValue();
            if (!username) {
                showBanner('error', t('privacy.selectUserFirst'));
                return;
            }
            try {
                const response = await apiFetch(`/api/privacy/users/${encodeURIComponent(username)}/export`);
                if (!response.ok) throw new Error('export failed');
                const blob = await response.blob();
                const objectUrl = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = objectUrl;
                link.download = 'navidrome-stat-export.json';
                link.click();
                window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
                showBanner('success', t('privacy.exportSuccess', { username }));
            } catch (error) {
                if (error.message !== 'unauthorized') showBanner('error', t('privacy.exportFailed'));
            }
        });
        document.getElementById('importBtn').addEventListener('click', () => {
            document.getElementById('importFile').click();
        });
        document.getElementById('importFile').addEventListener('change', async (event) => {
            const username = userSelect.getValue();
            const file = event.target.files[0];
            event.target.value = '';
            if (!username || !file) return;
            if (file.size > IMPORT_MAX_BYTES) {
                showBanner('error', t('privacy.importTooLarge'));
                return;
            }
            try {
                const payload = JSON.parse(await file.text());
                const records = Array.isArray(payload.records) ? payload.records.length : 0;
                const attempts = Array.isArray(payload.attempts) ? payload.attempts.length : 0;
                if (!confirmAction(t('privacy.importConfirm', {
                    username,
                    records: localizedCount(records),
                    attempts: localizedCount(attempts),
                }))) return;
                const response = await apiFetch(`/api/privacy/users/${encodeURIComponent(username)}/import`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        payload,
                        merge: document.getElementById('mergeImport').checked,
                    }),
                });
                if (!response.ok) throw new Error('import failed');
                const data = await response.json();
                showBanner('success', t('privacy.importSuccess', {
                    records: localizedCount(data.imported),
                    attempts: localizedCount(data.attempts_imported),
                    skipped: localizedCount(data.skipped),
                    conflicts: localizedCount(data.conflicts),
                }));
                await Promise.all([loadUsers(), refreshRetentionPreview()]);
            } catch (error) {
                if (error.message !== 'unauthorized') showBanner('error', t('privacy.importFailed'));
            }
        });
        document.getElementById('deleteUserBtn').addEventListener('click', async () => {
            const username = userSelect.getValue();
            if (!username) {
                showBanner('error', t('privacy.selectUserFirst'));
                return;
            }
            try {
                const preview = await refreshUserPreview();
                if (!preview || preview.username !== username) return;
                if (!confirmAction(t('privacy.deleteConfirm', {
                    preview: preview.text,
                    username,
                }))) return;
                const response = await apiFetch(`/api/privacy/users/${encodeURIComponent(username)}/delete`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirm: true }),
                });
                if (!response.ok) throw new Error('delete failed');
                const data = await response.json();
                showBanner('success', t('privacy.deleteSuccess', {
                    count: localizedCount(data.deleted),
                }));
                await Promise.all([loadUsers(), refreshRetentionPreview()]);
            } catch (error) {
                if (error.message !== 'unauthorized') showBanner('error', t('privacy.deleteFailed'));
            }
        });
    }

    function mount() {
        userSelect = registerListbox('userSelect', {
            placeholderKey: 'privacy.userLoading',
            onChange: () => refreshUserPreview().catch((error) => {
                if (!isAbortError(error)) showBanner('error', t('error.generic'));
            }),
        });
        bindRetentionControls();
        bindUserDataControls();
    }

    async function load() {
        await Promise.all([loadPrivacySettings(), loadUsers()]);
    }

    function localize() {
        renderPolicySummary();
        renderRetentionActions();
        updateStorageDisplay(state.storageSnapshot);
        updateRetentionPreviewText(state.storageSnapshot);
        renderUserOptions();
        refreshUserPreview().catch(() => {});
    }

    return Object.freeze({ mount, load, localize });
}
